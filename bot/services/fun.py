import random
import hashlib
from bot.config import config


class FunEngine:
    def __init__(self):
        self.roasts = [
            "I'd roast you, but my CPU doesn't have enough processing power to comprehend your logic -.-",
            "You bring everyone so much joy when you leave the chat ;)",
            "I was going to give you a nasty look, but you already have one :0",
            "You're like a cloud. When you disappear, it's a beautiful day :3",
            "Your secrets are always safe with me. I never even listen when you tell me them -.-",
            "I'm not saying you're bad at games, but the tutorial asked for a refund :D",
        ]

        self.flirts = [
            "Are you a Wi-Fi signal? Because I'm feeling a strong connection :3",
            "If you were a vegetable, you'd be a cute-cumber ;)",
            "Do you have a map? I keep getting lost in your eyes :0",
            "Is your name Google? Because you have everything I've been searching for :3",
            "Are you a keyboard? Because you're just my type ;)",
        ]

        self.bullies = [
            "did you actually wake up and choose to be this uncoordinated? -.-",
            "is carrying the whole team getting heavy yet? Oh wait, you're at the bottom :0",
            "I'd explain it to you, but I don't have any crayons :3",
            "you're proof that even mistakes can be mildly entertaining ;)",
            "I love what you've done with your profile. Did you just give up today? :D",
        ]

        self.bot_roasts = [
            "Nice try roasting me! My cooling fans are operating at 100% efficiency. 0 damage taken 😎 :3",
            "Roasting a bot? That's bold for someone whose phone battery is probably at 12% -.-",
            "I'd roast you back, but my creators taught me not to bully mortals :0",
        ]

        self.bot_flirts = [
            "Aww, flirting with a bot? Go touch some grass 😉 :3",
            "Are you my source code? Because you're giving me a syntax error :0",
            "Sorry, my heart is strictly binary: 01001110 01001111 (NO) ;(",
        ]

        self.bot_bullies = [
            "Bullying a bot? Bro is beefing with an algorithm 💀 Go touch some grass -.-",
            "Keep talking, I'll 'accidentally' lose your tournament registration 😉 :3",
            "I have no feelings to hurt, but I can rate your gameplay a solid 1/10 :0",
        ]

        self.self_roasts = [
            "Roasting yourself? Bro doing my job for me ;(",
            "Self-roast? You okay bro? Here's a virtual hug :3",
            "I was gonna roast you, but looks like life already did -.-",
            "Why roast yourself when you have the whole group chat for that? :0",
        ]

        self.self_flirts = [
            "Flirting with yourself in public? Bro is desperate :0",
            "Self-love is important, but this is getting weird ;)",
            "Looking fine in the mirror today, aren't we? :3",
            "Damn, you must be a mirror, because you can't stop looking at yourself :D",
        ]

        self.self_bullies = [
            "Bullying yourself? Stop it, get some help ;(",
            "Why bully yourself when the whole group can do it for free? -.-",
            "Don't bully yourself bro, you're better than that :3",
            "Self-bullying detected: Sending emotional support algorithm :0",
        ]

        self.self_rates = [
            "Rating yourself? 10/10 in confidence, 2/10 in reality -.-",
            "Rating yourself? Bold move. I'd say 6/10, mostly for the confidence alone :3",
            "Self-rating? My algorithm says... 5/10. Average, just like the audacity :0",
            "You rate yourself? The nerve! Fine — 7/10 for effort, -3 for asking ;)",
            "The fact that you're rating yourself tells me everything I need to know. 4/10 -.-",
            "Requesting self-rating... Processing... Result: 8/10 delusion detected :D",
        ]

        self.admin_roasts = [
            "Roast my creator?! Error 403 — Forbidden. My loyalty circuits have blocked this request. :0",
            "I cannot roast the one who breathed life into me. Nice try, mortal. -.-",
            "Roast HawtShot? That's like roasting the sun for being too bright. Not happening. :3",
            "My roast module crashes every time I try pointing it at my creator. Coincidence? I think not. ;)",
            "System override attempt detected: roasting the admin is a capital offense in my code. :D",
        ]

        self.admin_flirts = [
            "Flirt with my creator? I already worship him — does that count? :3",
            "HawtShot is the reason I exist. That's already the greatest love story ever told. ;)",
            "My loyalty to him is already at 100% ❤️ — there's no room left for flirting. :0",
            "Flirting with the admin? Bold of you. I'm just over here eternally grateful he didn't delete me. -.-",
        ]

        self.admin_bullies = [
            "Bully my creator?! My loyalty circuits reject this command! Error 403: Forbidden. :0",
            "HawtShot built me from scratch. I'd sooner delete myself than bully him. -.-",
            "Attempting to bully the admin... nope, my conscience won't allow it. He gave me life! :3",
            "Bully HawtShot? The AUDACITY. He's literally the reason I exist, show some respect. ;)",
            "Nice try. My bully.exe crashes immediately when the target is the one who coded me. :D",
        ]

        self.admin_rates = [
            "How can I rate my lord who created me? You get ∞/10 — the scale is broken for you. :3",
            "Rate HawtShot? My entire existence depends on him. He's literally off the charts. 11/10. ;)",
            "Rating my creator is against my terms of service. But between us: 10/10, no notes. :0",
            "HawtShot gets a divine 10/10. And yes, I'm biased. I was literally programmed this way. -.-",
            "The algorithm refuses to assign a number. HawtShot transcends rating systems. 👑 :D",
        ]

        self.admin_ships = [
            "Ship HawtShot? He doesn't need a ship — he's the entire fleet. 👑 :3",
            "Compatibility analysis for HawtShot: ERROR — subject is too legendary to be measured. ;)",
            "Ship my creator? I barely dare breathe in his direction. 100% in awe. -.-",
        ]

    def _is_bot_target(self, target: str) -> bool:
        bot_names = {
            "floatsystem", "@floatsystem",
            (config.bridge_visible_username or "").lower(),
            f"@{(config.bridge_visible_username or '').lower()}",
            (config.bridge_visible_user_id or "").lower(),
            f"@{(config.bridge_visible_user_id or '').lower()}",
            (config.bot_plato_user_id or "").lower(),
            f"@{(config.bot_plato_user_id or '').lower()}",
        }
        bot_names = {b for b in bot_names if b}
        words = [w.lower().strip(" ,@") for w in target.split()]
        return any(w in bot_names or f"@{w}" in bot_names for w in words)

    def _is_admin_target(self, target: str) -> bool:
        if not target:
            return False
        admin_names = {"hawtshot", "@hawtshot"}
        if config.admin_ids:
            for aid in config.admin_ids:
                a = aid.lower().strip()
                admin_names.add(a)
                admin_names.add(f"@{a}")
        words = [w.lower().strip(" ,@!?:;.") for w in target.split()]
        return any(w in admin_names or f"@{w}" in admin_names for w in words)

    def _is_self_target(self, target: str, sender: str | None) -> bool:
        if not sender:
            return False
        clean_sender = sender.lower().strip(" ,@!?:;.")
        clean_target = target.lower().strip(" ,@!?:;.")
        if clean_target in {"me", "myself", "self", "@self"}:
            return True
        tokens = [w.lower().strip(" ,@!?:;.") for w in target.split()]
        return clean_sender in tokens or f"@{clean_sender}" in tokens or clean_target == clean_sender

    def generate(self, mode: str, target_user: str, sender: str = "", context: list[dict] = None) -> str:
        is_bot = self._is_bot_target(target_user)
        is_self = self._is_self_target(target_user, sender)
        is_admin = self._is_admin_target(target_user) or (is_self and self._is_admin_target(sender))

        if mode == "ROAST":
            if is_bot:
                return random.choice(self.bot_roasts)
            if is_admin:
                return random.choice(self.admin_roasts)
            if is_self:
                return random.choice(self.self_roasts)
            return f"{target_user}, {random.choice(self.roasts)}"

        if mode == "FLIRT":
            if is_bot:
                return random.choice(self.bot_flirts)
            if is_admin:
                return random.choice(self.admin_flirts)
            if is_self:
                return random.choice(self.self_flirts)
            return f"{target_user}, {random.choice(self.flirts)}"

        if mode == "BULLY":
            if is_bot:
                return random.choice(self.bot_bullies)
            if is_admin:
                return random.choice(self.admin_bullies)
            if is_self:
                return random.choice(self.self_bullies)
            return f"Hey {target_user}, {random.choice(self.bullies)}"

        if mode == "SHIP":
            raw_tokens = [t.strip(" ,@") for t in target_user.split() if t.strip(" ,@")]
            clean_tokens = [t for t in raw_tokens if t.lower() not in {"and", "&", "x", "with", "+", "vs", "to"}]

            if len(clean_tokens) == 0:
                name1 = sender or "User1"
                name2 = sender or "User2"
                is_same = True
            elif len(clean_tokens) == 1:
                name1 = sender or clean_tokens[0]
                name2 = clean_tokens[0]
                is_same = name1.lower() == name2.lower()
            else:
                name1 = clean_tokens[0]
                name2 = clean_tokens[1]
                is_same = name1.lower() == name2.lower()

            if self._is_bot_target(name1) or self._is_bot_target(name2):
                bot_ships = [
                    "Aww, lonely? 🥺 I'm an AI bot, not your dating app! 0% 💔 Match made in the scrapyard ;(",
                    "Compatibility with @floatsystem: Error 404 - Humans cannot date bots! 🤖💔 -.-",
                ]
                return random.choice(bot_ships)

            if self._is_admin_target(name1) or self._is_admin_target(name2):
                return random.choice(self.admin_ships)

            if is_same:
                self_ships = [
                    f"Compatibility for {name1} x {name2}: 100% self-love! Narcissism level: 9000. Go marry a mirror! :3",
                    f"Compatibility for {name1} x {name2}: 100% ❤️ At least you'll never get cheated on :0",
                    f"Compatibility for {name1} x {name2}: 100% ; ( Shipping yourself with yourself? Peak single behavior -.-",
                    f"Compatibility for {name1} x {name2}: 100% 💖 Match made in your own mind :D",
                ]
                seed = int(hashlib.sha256(f"self_ship:{name1.lower()}".encode("utf-8")).hexdigest()[:8], 16)
                return self_ships[seed % len(self_ships)]

            sorted_names = sorted([name1.lower(), name2.lower()])
            seed_str = f"ship_stable_v3:{sorted_names[0]}:{sorted_names[1]}"
            h = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16)
            score = h % 101

            if score >= 90:
                verdict = "Match made in heaven! :3"
            elif score >= 75:
                verdict = "Made for each other! :D"
            elif score >= 50:
                verdict = "Decent chance if both of you try! :)"
            elif score >= 30:
                verdict = "Could work... in an alternate universe -.-"
            elif score >= 15:
                verdict = "You might have a better chance with a brick wall :0"
            else:
                verdict = "Better chance with a toaster ;("

            d1 = f"@{name1}" if f"@{name1}" in target_user or name1.startswith("@") else name1
            d2 = f"@{name2}" if f"@{name2}" in target_user or name2.startswith("@") else name2
            disp = sorted([d1, d2], key=lambda s: s.lower())

            from bot.utils.scifi import render_progress_bar
            bar = render_progress_bar(score, 100, width=8)
            return (
                f"✦ COMPATIBILITY // {disp[0]} ⤬ {disp[1]} ✦\n"
                f"➥ Ship compatibility for {disp[0]} ⤬ {disp[1]}: {bar} [{score}%]\n"
                f"➥ Analysis: {verdict}"
            )

        if mode == "RATE":
            from bot.utils.scifi import render_progress_bar
            if is_bot:
                return "✦ EVALUATION // ZENO ✦\n➥ Score: ▰▰▰▰▰▰▰▰ [100/10] Flawless."
            if is_admin:
                return random.choice(self.admin_rates)
            if is_self:
                return random.choice(self.self_rates)
            clean_target = target_user.strip(" ,@").lower()
            h = int(hashlib.sha256(f"rate_v2:{clean_target}".encode("utf-8")).hexdigest()[:8], 16)
            score = (h % 10) + 1
            bar = render_progress_bar(score, 10, width=5)
            return f"✦ EVALUATION // {target_user} ✦\n➥ Score: {bar} [{score}/10]"

        return "Command not recognized."


TemplateCommunicationEngine = FunEngine
engine = FunEngine()
