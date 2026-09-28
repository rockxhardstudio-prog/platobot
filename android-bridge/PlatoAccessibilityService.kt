package com.example.platobridge

import android.accessibilityservice.AccessibilityService
import android.os.Bundle
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.URLEncoder
import java.util.UUID

/**
 * Bridge between the dedicated bot Plato account (running this app on its
 * own device) and the Python backend.
 *
 * WHAT THIS DOES AND DOES NOT DO:
 *  - It reads text that Plato itself renders on screen for a normally
 *    logged-in user, the same way TalkBack or any accessibility tool does.
 *  - It "sends" messages by setting text in the real input field and
 *    tapping the real send button, the same way a human's finger would.
 *  - It never touches Plato's network traffic, never decrypts anything,
 *    never calls an undocumented/private API, and never reverse-engineers
 *    the app package.
 *
 * BEFORE THIS WILL RUN, YOU MUST FILL IN:
 *  1. PLATO_PACKAGE_NAME — get it with:
 *       adb shell pm list packages | grep -i plato
 *  2. The four resource-ids below — get them with Plato open on a group
 *     chat screen and running:
 *       adb shell uiautomator dump && adb pull /sdcard/window_dump.xml
 *     (or use the "Accessibility Scanner" app from the bot phone itself).
 *     The placeholder ids WILL NOT MATCH your real app and this class
 *     will silently find nothing until you replace them.
 *  3. A way to resolve a message's sender username and a stable per-message
 *     id from the node tree — this depends entirely on how Plato lays out
 *     each chat bubble (walk parent/sibling nodes of MESSAGE_TEXT_ID to
 *     find the username label next to it). Not guessed here on purpose.
 *  4. A way to resolve the current group's id — e.g. from the toolbar
 *     title node, or a manual mapping if Plato doesn't expose one cleanly.
 */
class PlatoAccessibilityService : AccessibilityService() {

    companion object {
        const val PLATO_PACKAGE_NAME = "com.platoapp.REPLACE_ME"
        const val MESSAGE_LIST_ID = "$PLATO_PACKAGE_NAME:id/REPLACE_ME_message_list"
        const val MESSAGE_TEXT_ID = "$PLATO_PACKAGE_NAME:id/REPLACE_ME_message_text"
        const val INPUT_FIELD_ID = "$PLATO_PACKAGE_NAME:id/REPLACE_ME_input"
        const val SEND_BUTTON_ID = "$PLATO_PACKAGE_NAME:id/REPLACE_ME_send_button"
        const val GROUP_TITLE_ID = "$PLATO_PACKAGE_NAME:id/REPLACE_ME_group_title"

        const val BACKEND_BASE_URL = "http://YOUR_BACKEND_HOST:8000"
        const val OUTBOX_POLL_INTERVAL_MS = 2000L
    }

    private val httpClient = OkHttpClient()
    private val seenMessageHashes = mutableSetOf<Int>()
    private val handler = android.os.Handler(android.os.Looper.getMainLooper())

    private val outboxPoller = object : Runnable {
        override fun run() {
            pollOutbox()
            handler.postDelayed(this, OUTBOX_POLL_INTERVAL_MS)
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        handler.post(outboxPoller)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || event.packageName != PLATO_PACKAGE_NAME) return
        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED &&
            event.eventType != AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED
        ) return

        val root = rootInActiveWindow ?: return
        val messageNodes = root.findAccessibilityNodeInfosByViewId(MESSAGE_TEXT_ID)
        for (node in messageNodes) {
            val text = node.text?.toString() ?: continue
            val hash = text.hashCode()
            if (!seenMessageHashes.add(hash)) continue

            // Deliberately not guessing how to pull sender/group from the
            // node tree — see class doc. Fill this in against the real
            // layout before relying on user_id/group_id downstream.
            val messageId = UUID.nameUUIDFromBytes(text.toByteArray()).toString()
            forwardToBackend(
                messageId = messageId,
                groupId = resolveCurrentGroupId() ?: return,
                userId = "REPLACE_ME_sender_id",
                username = "REPLACE_ME_sender_name",
                text = text,
                isSelf = false,
            )
        }
    }

    private fun resolveCurrentGroupId(): String? {
        // Configure GROUP_TITLE_ID and map the visible title to the backend's
        // MAIN_GROUP_ID/STORAGE_GROUP_ID. Returning null is deliberately safe:
        // it prevents messages from an unknown conversation being forwarded.
        val root = rootInActiveWindow ?: return null
        val visibleTitle = root.findAccessibilityNodeInfosByViewId(GROUP_TITLE_ID)
            .firstOrNull()?.text?.toString()?.trim() ?: return null
        return groupIdForVisibleTitle(visibleTitle)
    }

    private fun groupIdForVisibleTitle(visibleTitle: String): String? {
        // REPLACE_ME: use only a local, explicit title -> configured group-ID map.
        // Never guess from arbitrary chat text.
        return null
    }

    private fun forwardToBackend(
        messageId: String,
        groupId: String,
        userId: String,
        username: String,
        text: String,
        isSelf: Boolean,
    ) {
        val json = JSONObject().apply {
            put("message_id", messageId)
            put("group_id", groupId)
            put("user_id", userId)
            put("username", username)
            put("text", text)
            put("is_self", isSelf)
        }
        val body = json.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url("$BACKEND_BASE_URL/inbox").post(body).build()
        httpClient.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("PlatoBridge", "inbox POST failed", e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.close()
            }
        })
    }

    private fun pollOutbox() {
        val groupId = resolveCurrentGroupId() ?: return
        val encodedGroupId = URLEncoder.encode(groupId, "UTF-8")
        val request = Request.Builder()
            .url("$BACKEND_BASE_URL/outbox?group_id=$encodedGroupId")
            .get()
            .build()
        httpClient.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("PlatoBridge", "outbox GET failed", e)
            }

            override fun onResponse(call: Call, response: Response) {
                val bodyStr = response.body?.string()
                response.close()
                if (bodyStr.isNullOrBlank()) return
                val arr = JSONArray(bodyStr)
                for (i in 0 until arr.length()) {
                    val item = arr.getJSONObject(i)
                    val id = item.getInt("id")
                    val text = item.getString("text")
                    handler.post {
                        // The outbox request is scoped to the currently open,
                        // confirmed group. A failed UI send must not be acked.
                        if (sendMessageViaUi(text)) ackOutbox(id)
                    }
                }
            }
        })
    }

    private fun sendMessageViaUi(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val input = root.findAccessibilityNodeInfosByViewId(INPUT_FIELD_ID).firstOrNull() ?: return false

        val args = Bundle()
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        if (!input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return false

        val sendButton = root.findAccessibilityNodeInfosByViewId(SEND_BUTTON_ID).firstOrNull()
            ?: return false
        return sendButton.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }

    private fun ackOutbox(outboxId: Int) {
        val body = "".toRequestBody(null)
        val request = Request.Builder()
            .url("$BACKEND_BASE_URL/outbox/$outboxId/ack")
            .post(body)
            .build()
        httpClient.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("PlatoBridge", "ack POST failed", e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.close()
            }
        })
    }

    override fun onInterrupt() {}
}
