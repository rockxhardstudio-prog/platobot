# BlueStacks Plato UI diagnostic

This is the laptop-first, read-only diagnostic for the existing bridge. It uses
BlueStacks' bundled `HD-Adb.exe` and Android's UIAutomator surface; it does not
intercept Plato traffic, use a private API, type messages, or alter the account.

1. Open BlueStacks and log the bot account into Plato.
2. Open the target group chat, leaving it visible.
3. From the project root run:

```powershell
python bridge/diagnostics/bluestacks_probe.py --output plato-ui.json --print-tree
```

The output JSON records the current foreground activity, detected Plato package
names, ADB errors, and every exposed UI node: text, description, resource ID,
clickable/focusable/scrollable state, bounds, and parent/child links.

Repeat the same command after opening the group online-members screen. Compare
the two JSON files to identify title, message, sender, input/send, and online-list
nodes. Do not copy guessed selectors into the Android accessibility service.

If `UI nodes captured` is zero, use the ADB diagnostics embedded in the JSON to
identify whether BlueStacks has temporarily disconnected. The next safe step is
to reopen Plato visibly and rerun the tool. Do not fall back to OCR polling.
