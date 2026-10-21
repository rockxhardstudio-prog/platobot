import importlib
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest


@pytest.fixture
def bot(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("BOT_DB_PATH", db_path)
    monkeypatch.setenv("MAIN_GROUP_ID", "main")
    monkeypatch.setenv("STORAGE_GROUP_ID", "storage")
    monkeypatch.setenv("ADMIN_IDS", "admin")
    monkeypatch.setenv("MAX_SPAM_REPETITIONS", "3")
    monkeypatch.setenv("SPAM_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("BOT_TIMEZONE", "Asia/Kolkata")
    for name in list(sys.modules):
        if name.startswith("bot."):
            del sys.modules[name]
    db = importlib.import_module("bot.database.db")
    db.init_db()
    router = importlib.import_module("bot.commands.router")
    message = importlib.import_module("bot.models.message").IncomingMessage
    yield router, message, db
    db.get_conn().close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except FileNotFoundError:
            pass


def send(router, message, ident, group, user, text, timestamp=None, self_message=False):
    return router.handle_message(message(ident, group, user, user.title(), text, self_message, timestamp))


def test_spam_accepts_spacing_variants_and_queues_messages(bot):
    router, message, _ = bot
    assert send(router, message, "s1", "storage", "admin", "/spamset 1 hello") == "Saved spam message 1."
    assert send(router, message, "m1", "main", "user", "/spam : 1 + 2") == "Queued message 1 2 times."
    pending = router.plato_client.pending("main", 10)
    assert [item["text"] for item in pending] == ["hello", "hello", "Queued message 1 2 times."]
    assert send(router, message, "m2", "main", "user2", "/spam:1+1") == "Queued message 1 1 time."
    assert send(router, message, "m3", "main", "user3", "/spam 1 + 1") == "Queued message 1 1 time."


def test_spam_rejects_bad_count_and_wrong_group(bot):
    router, message, _ = bot
    send(router, message, "s1", "storage", "admin", "/spamset 1 hello")
    assert "1 to 3" in send(router, message, "m1", "main", "user", "/spam:1+4")
    assert "Usage" in send(router, message, "m2", "main", "user", "/spam:bad")
    assert "Main Group" in send(router, message, "s2", "storage", "admin", "/spam:1+1")


def test_spam_requires_existing_entry_and_enforces_cooldown(bot):
    router, message, _ = bot
    assert "No stored" in send(router, message, "m0", "main", "other-user", "/spam:99+1")
    send(router, message, "s1", "storage", "admin", "/spamset 1 hello")
    router.config.spam_cooldown_seconds = 60
    assert send(router, message, "m1", "main", "user", "/spam:1+1").startswith("Queued")
    assert "Please wait" in send(router, message, "m2", "main", "user", "/spam:1+1")


def test_storage_updates_require_admin_and_invite_is_returned(bot):
    router, message, _ = bot
    assert "Only a bot admin" in send(router, message, "s1", "storage", "person", "/inviteset https://plato.example/invite")
    assert "valid http" in send(router, message, "s2", "storage", "admin", "/inviteset not-a-link")
    assert send(router, message, "s3", "storage", "admin", "/inviteset https://plato.example/invite") == "Invite link saved."
    assert send(router, message, "m1", "main", "person", "/invite") == "https://plato.example/invite"


def test_add_creates_and_updates_mapping(bot):
    router, message, db = bot
    assert send(router, message, "s1", "storage", "admin", "/add Yuvraj:1") == "Saved ID 1 for Yuvraj."
    assert send(router, message, "s2", "storage", "admin", "/add Alex:1") == "Saved ID 1 for Alex."
    row = db.get_conn().execute("SELECT username FROM user_id_map WHERE id=1").fetchone()
    assert row["username"] == "Alex"
    assert "Storage Group" in send(router, message, "m1", "main", "admin", "/add Other:2")


def test_summary_counts_main_messages_once_and_ranks_users(bot):
    router, message, _ = bot
    today = datetime.now(timezone.utc).isoformat()
    send(router, message, "m1", "main", "alice", "hello", today)
    send(router, message, "m2", "main", "alice", "again", today)
    send(router, message, "m3", "main", "bob", "hi", today)
    send(router, message, "other", "storage", "admin", "not counted", today)
    send(router, message, "m1", "main", "alice", "duplicate", today)
    # Regular user in Main GC should be told /summary is staff-only
    main_try = send(router, message, "summary_main", "main", "bob", "/summary", today)
    assert "staff-only" in main_try
    # Staff in Staff GC gets the Main GC summary
    response = send(router, message, "summary_staff", "storage", "admin", "/summary", today)
    assert "Active members: 2" in response
    assert "Total messages: 4" in response  # m1, m2, m3, summary_main
    assert "1. Alice — 2 messages" in response
    assert "2. Bob — 2 messages" in response


def test_summary_honors_kolkata_day_boundary_and_yesterday(bot):
    _, _, db = bot
    from bot.services.mvp import activity_summary

    conn = db.get_conn()
    conn.executemany(
        "INSERT INTO messages (message_id, group_id, user_id, username, text, created_at) VALUES (?, 'main', ?, ?, 'x', ?)",
        [
            ("before", "a", "Alice", "2026-09-04T18:29:59+00:00"),
            ("start", "a", "Alice", "2026-09-04T18:30:00+00:00"),
            ("later", "b", "Bob", "2026-09-05T10:00:00+00:00"),
        ],
    )
    conn.commit()
    ref_now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    total, active, ranked, _ = activity_summary("main", ref_now, period="today")
    assert (total, active, ranked) == (2, 2, [("Alice", 1), ("Bob", 1)])
    y_total, y_active, y_ranked, _ = activity_summary("main", ref_now, period="yesterday")
    assert (y_total, y_active, y_ranked) == (1, 1, [("Alice", 1)])


def test_self_messages_and_duplicates_are_not_recorded(bot):
    router, message, db = bot
    send(router, message, "self", "main", "bot", "I sent this", self_message=True)
    send(router, message, "d1", "main", "alice", "hello")
    send(router, message, "d1", "main", "alice", "hello again")
    assert db.get_conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_phase1_socials_setinsta_setdc_setinvite(bot):
    router, message, _ = bot
    assert "No social links" in send(router, message, "soc0", "main", "alice", "/socials")
    assert "Instagram link updated." == send(
        router, message, "si1", "storage", "admin", "/setinsta https://instagram.com/order"
    )
    assert "Discord link updated." == send(
        router, message, "sd1", "storage", "admin", "/setdc https://discord.gg/order"
    )
    assert "Invite link saved." == send(
        router, message, "sinv1", "storage", "admin", "/setinvite https://platoapp.com/link/order"
    )
    res = send(router, message, "soc1", "main", "bob", "/socials")
    assert "https://instagram.com/order" in res
    assert "https://discord.gg/order" in res
    assert "https://platoapp.com/link/order" in res


def test_phase1_staff_hierarchy_and_config(bot):
    router, message, _ = bot
    # Non-owner cannot add staff
    assert "Only a bot owner" in send(router, message, "st1", "storage", "bob", "/staffadd mod_user mod")
    # Seed owner ('admin') can add mod and admin
    assert "Assigned role 'mod' to mod_user." == send(
        router, message, "st2", "storage", "admin", "/staffadd @mod_user mod"
    )
    assert "Assigned role 'admin' to sub_admin." == send(
        router, message, "st3", "storage", "admin", "/staffadd sub_admin admin"
    )
    roster = send(router, message, "st4", "storage", "mod_user", "/stafflist")
    assert "admin [OWNER]" in roster
    assert "sub_admin [ADMIN]" in roster
    assert "mod_user [MOD]" in roster

    # Mod can run /summary and /warn in Staff GC, but not /setinfo
    assert "DAILY SUMMARY" in send(router, message, "st5", "storage", "mod_user", "/summary")
    assert "Warned troublemaker" in send(router, message, "st6", "storage", "mod_user", "/warn troublemaker spam")
    assert "Only a bot admin" in send(router, message, "st7", "storage", "mod_user", "/setinfo New info")
    # Promoted admin can run /setinfo, but cannot run /staffadd
    assert "Community info updated." == send(router, message, "st8", "storage", "sub_admin", "/setinfo New info")
    assert "Only a bot owner" in send(router, message, "st9", "storage", "sub_admin", "/staffadd someone mod")

    # Seed owner cannot be removed
    assert "Cannot remove a seed owner" in send(router, message, "st10", "storage", "admin", "/staffremove admin")
    assert "Removed staff role from mod_user." == send(
        router, message, "st11", "storage", "admin", "/staffremove mod_user"
    )

    # Config read by admin/mod, write by owner
    assert "Updated config summon_timeout_seconds = 180" == send(
        router, message, "cfg1", "storage", "admin", "/config summon_timeout_seconds 180"
    )
    assert "180" in send(router, message, "cfg2", "storage", "sub_admin", "/config summon_timeout_seconds")


def test_phase1_summon_return_status_and_tourneyinfo(bot):
    router, message, _ = bot
    # /tourneyinfo works in Main GC
    assert "No tournament is currently active." == send(
        router, message, "ti1", "main", "alice", "/tourneyinfo"
    )
    # /summon from Main GC by admin switches target group to storage
    res_sum = send(router, message, "sum1", "main", "admin", "/summon 5")
    assert "Summoned to Staff GC for 5 min" in res_sum

    status_res = send(router, message, "stat1", "storage", "admin", "/status")
    assert "SYSTEM STATUS" in status_res
    assert "Summon timer:" in status_res

    res_ret = send(router, message, "ret1", "storage", "admin", "/return")
    assert "Returning bot focus to Main GC" in res_ret


def test_phase2_sentinel_links_domains_and_staff_exemption(bot):
    router, message, _ = bot
    from bot.services import moderation
    moderation.reset_runtime_state()

    # Promote a mod so we can verify staff exemption
    send(router, message, "p2_s0", "storage", "admin", "/staffadd trusted_mod mod")

    # Staff member posting unapproved link and Hinglish in Main GC -> NOT warned
    assert send(router, message, "p2_m0", "main", "trusted_mod", "check https://sketchy.io/abc") is None
    assert send(router, message, "p2_m1", "main", "trusted_mod", "bhai kya kar raha hai") is None

    # Regular member posting unapproved link -> warned (1/5)
    w1 = send(router, message, "p2_u1", "main", "regular_joe", "join https://sketchy.io/abc now")
    assert w1 is not None and "Warning (1/5)" in w1 and "sketchy.io" in w1

    # Allow youtube.com via Staff GC
    assert "Allowed link domain: youtube.com" == send(
        router, message, "p2_ad1", "storage", "admin", "/allowdomain https://www.youtube.com"
    )
    assert "youtube.com" in send(router, message, "p2_dom1", "storage", "trusted_mod", "/domains")

    # Regular member posting allowed youtube link -> NOT warned
    moderation.reset_runtime_state()
    assert send(
        router, message, "p2_u2", "main", "regular_joe", "watch https://m.youtube.com/watch?v=123"
    ) is None


def test_phase2_sentinel_strict_english_hinglish_and_five_warning_notice_list(bot):
    router, message, _ = bot
    from bot.services import moderation
    moderation.reset_runtime_state()

    # Short English slang & mentions must NOT trigger false positives
    assert send(router, message, "p2_e1", "main", "culprit", "ok lol gg @Alex nice match!") is None

    # 1st warning: Hinglish
    w1 = send(router, message, "p2_w1", "main", "culprit", "bhai kya kar raha hai tu")
    assert w1 is not None and "Warning (1/5)" in w1 and "Hinglish" in w1

    # 2nd warning: Non-Latin script (Devanagari) after cooldown reset
    moderation.reset_runtime_state()
    w2 = send(router, message, "p2_w2", "main", "culprit", "नमस्ते भाई")
    assert w2 is not None and "Warning (2/5)" in w2

    # 3rd warning: Character flood spam
    moderation.reset_runtime_state()
    w3 = send(router, message, "p2_w3", "main", "culprit", "heyyyyyyyyyyyyyyyyyyyyyyyy")
    assert w3 is not None and "Warning (3/5)" in w3

    # 4th & 5th warnings via Staff GC /warn -> triggers 5-Warning Notice List escalation!
    w4 = send(router, message, "p2_w4", "storage", "admin", "/warn culprit Fourth strike")
    assert "(4/5)" in w4
    w5 = send(router, message, "p2_w5", "storage", "admin", "/warn culprit Fifth strike")
    assert "(5/5)" in w5 and "Staff Notice List" in w5

    # Check /noticelist and /summary in Staff GC
    nlist = send(router, message, "p2_nl1", "storage", "admin", "/noticelist")
    assert "culprit" in nlist and "5 warns" in nlist

    summary = send(router, message, "p2_sum1", "storage", "admin", "/summary")
    assert "Warnings issued: 5" in summary
    assert "5-Warn Notice: culprit (5)" in summary

    # /unwarn drops culprit to 4/5 and resolves notice list entry
    unw = send(router, message, "p2_unw1", "storage", "admin", "/unwarn culprit")
    assert "4/5" in unw
    nlist_after = send(router, message, "p2_nl2", "storage", "admin", "/noticelist")
    assert "No members" in nlist_after

    # /setlang off disables language warnings; first Main GC message from culprit delivers queued manual warning #4
    assert "OFF" in send(router, message, "p2_lang0", "storage", "admin", "/setlang off")
    moderation.reset_runtime_state()
    queued_deliv = send(router, message, "p2_lang1", "main", "culprit", "bhai kya haal hai")
    assert queued_deliv is not None and "Warning (4/5): Fourth strike" in queued_deliv
    assert send(router, message, "p2_lang2", "main", "culprit", "bhai kya haal hai") is None
    assert "ON" in send(router, message, "p2_lang3", "storage", "admin", "/setlang on")


def test_phase3_identity_xp_ranks_leaderboard_and_summary(bot):
    router, message, _ = bot
    from bot.services import identity, moderation
    moderation.reset_runtime_state()
    identity.reset_runtime_state()

    # 1. Eligible chat message in Main GC awards +15 XP
    assert send(router, message, "p3_m1", "main", "ace_player", "Hey everyone, great tournament match today!") is None
    prof1 = send(router, message, "p3_p1", "main", "ace_player", "/profile")
    assert "Level: 1" in prof1 and "Recruit" in prof1 and "15/100" in prof1

    # 2. Immediate second message within 45s cooldown does NOT award additional XP
    assert send(router, message, "p3_m2", "main", "ace_player", "Ready for the next round now!") is None
    prof2 = send(router, message, "p3_p2", "main", "ace_player", "/rank")
    assert "15/100" in prof2

    # 3. Duplicate message even after cooldown reset does NOT award XP
    identity.reset_runtime_state()
    assert send(router, message, "p3_m3", "main", "ace_player", "Hey everyone, great tournament match today!") is None
    prof3 = send(router, message, "p3_p3", "main", "admin", "/profile ace_player")
    assert "15/100" in prof3

    # 4. Admin grants +90 XP via /xpgrant in Staff GC -> pushes ace_player to 105 XP (Lv.2)
    grant_res = send(router, message, "p3_g1", "storage", "admin", "/xpgrant ace_player 90")
    assert "Granted +90 XP" in grant_res and "Lv.2" in grant_res

    # 5. Next eligible chat message that crosses 200 XP triggers automatic level-up announcement in Main GC!
    send(router, message, "p3_g2", "storage", "admin", "/xpgrant ace_player 85")  # now 190 XP (Lv.2)
    moderation.reset_runtime_state()
    identity.reset_runtime_state()
    lvl_up_msg = send(router, message, "p3_m4", "main", "ace_player", "Winning this whole bracket for sure!")
    assert lvl_up_msg is not None
    assert "leveled up to Level 3 [Initiate]" in lvl_up_msg

    # 6. Check /leaderboard (/lb) and /xprevoke
    send(router, message, "p3_g3", "storage", "admin", "/xpgrant rookie_two 50")
    lb = send(router, message, "p3_lb1", "main", "ace_player", "/lb")
    assert "XP LEADERBOARD" in lb
    assert "1. Ace_Player — Lv.3 Initiate (205 XP)" in lb
    assert "2. rookie_two — Lv.1 Recruit (50 XP)" in lb

    rev_res = send(router, message, "p3_rev1", "storage", "admin", "/xprevoke rookie_two 20")
    assert "Revoked -20 XP" in rev_res and "30 XP" in rev_res

    # 7. Enhanced /summary in Staff GC includes XP & Level-up highlights and hides in Main GC
    main_sum = send(router, message, "p3_msum", "main", "ace_player", "/summary")
    assert "staff-only" in main_sum.lower()

    staff_sum = send(router, message, "p3_ssum", "storage", "admin", "/summary today")
    assert "DAILY SUMMARY" in staff_sum
    assert "XP awarded: 255" in staff_sum
    assert "Level-ups:" in staff_sum


def test_invalid_command_winners_trules_and_short_admin_commands(bot):
    router, message, _ = bot

    # 1. Invalid command replies with helpful message mentioning /help or /h
    inv = send(router, message, "u_inv1", "main", "alice", "/gg")
    assert "Invalid command '/gg'" in inv and "/help or /h" in inv

    # 2. Permanent owners (tuhin, hawtshot, zuriah, ad4rshh) have full owner privileges
    ah_res = send(router, message, "u_ah1", "storage", "tuhin", "/ah")
    assert "ADMIN HELP" in ah_res and "/adminhelp" not in ah_res

    # 3. Set giveaway/tourney rules via /strules and check /trules in Main GC
    assert "updated" in send(router, message, "u_tr1", "storage", "zuriah", "/strules Best of 1 Pool, no timeouts!").lower()
    tr_main = send(router, message, "u_tr2", "main", "alice", "/trules")
    assert "Best of 1 Pool" in tr_main

    # 4. /participants is restricted to Staff GC (blocked for normal users in Main GC)
    part_main = send(router, message, "u_pm1", "main", "alice", "/participants")
    assert "staff-only" in part_main.lower()

    # 5. Progressive winners list for multi-tab giveaways with exact user_id resolution
    # Suppose player_one (user_id='uid_p1', username='PlayerOne') chatted in Main GC
    router.handle_message(message("m_p1", "main", "uid_p1", "PlayerOne", "ready for tab 1", False, None))
    router.handle_message(message("m_p2", "main", "uid_p2", "PlayerTwo", "ready for tab 2", False, None))

    # Tab 1 finishes while Tabs 2-5 are still running -> staff adds PlayerOne
    w_res1 = send(router, message, "u_aw1", "storage", "ad4rshh", "/aw @PlayerOne Tab #1 (Pool)")
    assert "uid_p1" in w_res1 and "Tab #1 (Pool)" in w_res1

    # Tab 2 finishes -> staff adds PlayerTwo (auto-numbered or custom label)
    w_res2 = send(router, message, "u_aw2", "storage", "hawtshot", "/aw PlayerTwo")
    assert "uid_p2" in w_res2 and "Tab #2" in w_res2

    # Check /winners (/wl) in Main GC
    wl_main = send(router, message, "u_wl1", "main", "alice", "/wl")
    assert "1. Tab #1 (Pool): @PlayerOne [ID: uid_p1]" in wl_main
    assert "2. Tab #2: @PlayerTwo [ID: uid_p2]" in wl_main


def test_off_only_hawtshot_and_smart_tourney_and_giveaway(bot):
    router, message, _ = bot
    from bot.services import mvp, tournament

    # 1. /off restricted strictly to HawtShot
    denied = send(router, message, "off_1", "storage", "tuhin", "/off")
    assert "Only HawtShot" in denied
    assert mvp.get_bridge_state()["target_group_id"] != "off"

    allowed = send(router, message, "off_2", "main", "HawtShot", "/off")
    assert "Leaving group chat" in allowed
    assert mvp.get_bridge_state()["target_group_id"] == "off"

    # Return to main for remaining tests
    send(router, message, "ret_1", "storage", "HawtShot", "/return")
    assert mvp.get_bridge_state()["target_group_id"] == "main"

    # 2. Type 2 Giveaway: 40 online in Bingo (15 seats/tab) -> 2 tabs per wave
    ga40 = send(router, message, "ga_1", "storage", "hawtshot", "/createga 10 Bingo 40 | 1 win per person")
    assert "Creating 2 Bingo tab(s)" in ga40

    # Type 2 Giveaway: 45 online in Bingo (15 seats/tab) for 4 winners -> Wave 1 has 3 tabs, Wave 2 has 1 tab
    ga45 = send(router, message, "ga_2", "storage", "hawtshot", "/createga 4 Bingo 45 | Fast bingo")
    assert "Creating 3 Bingo tab(s)" in ga45

    w1 = send(router, message, "gaw_1", "storage", "hawtshot", "/addwinner @HawtShot")
    assert "Winners so far: Hawtshot" in w1
    w2 = send(router, message, "gaw_2", "storage", "hawtshot", "/addwinner @TUHIN")
    assert "Winners so far: Hawtshot, Tuhin" in w2
    w3 = send(router, message, "gaw_3", "storage", "hawtshot", "/addwinner @zuriah")
    assert "Winners so far: Hawtshot, Tuhin, zuriah" in w3
    assert "WAVE #2: Creating 1 Bingo tab(s)" in w3
    w4 = send(router, message, "gaw_4", "storage", "hawtshot", "/addwinner @AD4RSHH")
    assert "ALL 4/4 GIVEAWAY WINNERS CROWNED" in w4

    # 3. Type 1 Elimination Bracket Tournament (8 slots -> 4 matches; test AFK void + BYE handling + /iwon)
    ct = send(router, message, "tc_1", "storage", "hawtshot", "/createtourney 8 Ocho | No stacking +2")
    assert "Slots: 8" in ct

    for i in range(1, 9):
        reg = send(router, message, f"reg_{i}", "main", f"p{i}", "/register")
        assert "Registered" in reg

    st = send(router, message, "st_1", "storage", "hawtshot", "/starttourney")
    assert "ROUND 1" in st and "M1:" in st and "M4:" in st

    # Check /mymatch and /matches
    mm = send(router, message, "mm_1", "main", "p1", "/mymatch")
    assert "Match #1" in mm
    all_m = send(router, message, "am_1", "main", "p1", "/matches")
    assert "M4:" in all_m

    # Match 1: p1 declares win via /iwon -> progressive winners list starts with P1
    win1 = send(router, message, "w_1", "main", "p1", "/iwon")
    assert "Round 1 Winners (1/4): P1" in win1

    # Match 2: p3 declares win via /iwon -> progressive winners list shows P1, P3
    win2 = send(router, message, "w_2", "main", "p3", "/iwon")
    assert "Round 1 Winners (2/4): P1, P3" in win2

    # Match 3: p5 reports AFK opponent p6
    rep = send(router, message, "rep_1", "main", "p5", "/reportissue opponent p6 is offline")
    assert "Issue logged" in rep
    issues_txt = send(router, message, "iss_1", "storage", "hawtshot", "/issues")
    assert "R1 M3" in issues_txt

    # Simulate Match 4 double-AFK (both p7 and p8 inactive > 5 mins)
    from bot.database.db import get_conn
    conn = get_conn()
    conn.execute(
        "UPDATE tourney_matches SET p1_last_active='2020-01-01T00:00:00+00:00', p2_last_active='2020-01-01T00:00:00+00:00' WHERE match_number=4"
    )
    conn.commit()

    # Set custom game & rules for Round 2 before Round 1 finishes
    rr = send(router, message, "rr_1", "storage", "hawtshot", "/roundrules Pool | Best of 1, no guideline")
    assert "Pool" in rr

    win3 = send(router, message, "w_3", "main", "p5", "/iwon")
    assert "P1, P3, P5" in win3

    # Now resolve AFK on Match 4 (both AFK -> voided! Only 3 winners advance: P1, P3, P5 -> P1 gets auto-BYE, P3 vs P5 play Match #1!)
    afk_res = send(router, message, "afk_1", "storage", "hawtshot", "/checkafk 5")
    assert "Double AFK" in afk_res
    assert "ROUND 2" in afk_res
    assert "Pool" in afk_res
    assert "BYE" in afk_res

    # In Round 2, p3 wins Match #1 against p5 -> Finals (Round 3) automatically starts between P1 and P3!
    r2_win = send(router, message, "w_r2", "main", "p3", "/iwon")
    assert "ROUND 3" in r2_win

    # In Finals (Round 3), p1 wins -> P1 crowned Champion!
    r3_win = send(router, message, "w_r3", "main", "p1", "/iwon")
    assert "TOURNAMENT CHAMPION: @P1" in r3_win


def test_interactive_wizards_and_staff_controls(bot):
    router, message, _ = bot
    from bot.services import mvp, session, tournament

    # Clean sessions
    session.end_session("hawtshot")

    # 1. Test /createtour interactive wizard flow
    s1 = send(router, message, "tw_1", "storage", "hawtshot", "/createtour")
    assert "Tournament Title?" in s1
    s2 = send(router, message, "tw_2", "storage", "hawtshot", "Winter Ocho Cup")
    assert "Game?" in s2
    s3 = send(router, message, "tw_3", "storage", "hawtshot", "Ocho")
    assert "participant slots?" in s3
    s4 = send(router, message, "tw_4", "storage", "hawtshot", "8")
    assert "Tournament Rules?" in s4
    s5 = send(router, message, "tw_5", "storage", "hawtshot", "Standard fair play")
    assert "Round 1 Rules?" in s5
    s6 = send(router, message, "tw_6", "storage", "hawtshot", "same")
    assert "Prize / Description?" in s6
    s7 = send(router, message, "tw_7", "storage", "hawtshot", "50 Pips")
    assert "created as DRAFT" in s7 and "Winter Ocho Cup" in s7

    # Check /draft
    d_res = send(router, message, "dr_1", "storage", "hawtshot", "/draft")
    assert "Winter Ocho Cup" in d_res and "DRAFT" in d_res

    # Test /start opens registration
    start_res = send(router, message, "st_1", "storage", "hawtshot", "/start")
    assert "REGISTRATION NOW OPEN" in start_res

    # Test /pause pauses registration
    p_res = send(router, message, "pa_1", "storage", "hawtshot", "/pause")
    assert "PAUSED" in p_res

    reg_blocked = send(router, message, "reg_p", "main", "alice", "/register")
    assert "PAUSED" in reg_blocked

    # Test /resume
    res_out = send(router, message, "res_1", "storage", "hawtshot", "/resume")
    assert "RESUMED" in res_out

    reg_ok = send(router, message, "reg_ok", "main", "alice", "/register")
    assert "Registered successfully" in reg_ok

    # Test /end
    end_res = send(router, message, "end_1", "storage", "hawtshot", "/end")
    assert "ended" in end_res

    # 2. Test /createga interactive wizard flow
    g1 = send(router, message, "gw_1", "storage", "hawtshot", "/createga")
    assert "Giveaway Game?" in g1
    g2 = send(router, message, "gw_2", "storage", "hawtshot", "Bingo")
    assert "Total Winners?" in g2
    g3 = send(router, message, "gw_3", "storage", "hawtshot", "10")
    assert "members online?" in g3
    g4 = send(router, message, "gw_4", "storage", "hawtshot", "40")
    assert "Giveaway Info / Timing?" in g4
    g5 = send(router, message, "gw_5", "storage", "hawtshot", "Bingo Wave Event")
    assert "Giveaway Rules?" in g5
    g6 = send(router, message, "gw_6", "storage", "hawtshot", "1 win per member")
    assert "Giveaway draft ready" in g6 and "2 tabs" in g6

    # Test /start launches giveaway Wave #1
    ga_start = send(router, message, "ga_s", "storage", "hawtshot", "/start")
    assert "WAVE #1" in ga_start and "Creating 2 Bingo tab(s)" in ga_start

    # Test /pause on giveaway
    ga_pause = send(router, message, "ga_p", "storage", "hawtshot", "/hold")
    assert "PAUSED" in ga_pause

    win_blocked = send(router, message, "gaw_blk", "storage", "hawtshot", "/addwinner @alice")
    assert "PAUSED" in win_blocked

    # Test /resume on giveaway
    ga_res = send(router, message, "ga_r", "storage", "hawtshot", "/resume")
    assert "RESUMED" in ga_res

    # Test /on command
    on_res = send(router, message, "on_1", "storage", "hawtshot", "/on")
    assert "presence enabled" in on_res

    # Test resume_from_off
    mvp.turn_off_gc("hawtshot")
    assert mvp.get_bridge_state()["target_group_id"] == "off"
    mvp.resume_from_off("main", "-» NOVΛ ⟡ BLΛZΞ «-")
    assert mvp.get_bridge_state()["target_group_id"] == "main"





