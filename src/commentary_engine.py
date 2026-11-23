"""
commentary_engine.py - Automated Bilingual (CN/EN) Esports Commentary & Subtitle Generation Engine.
Analyzes battle frame logs, health delta events, and match transitions to generate
synchronized sports commentator scripts formatted as structured JSON and dual-language SRT subtitles.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Character-specific flavor texts and signature moves in both Chinese and English
CHAR_COMMENTARY_DATA: Dict[str, Dict[str, Any]] = {
    "earthquake": {
        "title_zh": "地震 (Earthquake)",
        "title_en": "Earthquake",
        "p2_style_zh": "百吨身躯与锁链重斩",
        "p2_style_en": "colossal 100-ton bulk and chain cleaves",
        "hit_reaction_zh": "地震庞大身躯被生生逼退，防线被劈开！",
        "hit_reaction_en": "driving the colossal giant back with crisp spacing!",
        "ko_finish_zh": "霸王丸双跃凌空大劈，百吨巨力被一刀斩落！",
        "ko_finish_en": "a thunderous overhead slash brings the giant crashing down!",
    },
    "genjuro": {
        "title_zh": "牙神幻十郎 (Genjuro)",
        "title_en": "Genjuro Kibagami",
        "p2_style_zh": "凶狠嗜血的樱华狂咲与三连杀",
        "p2_style_en": "vicious card slashes and ruthless offensive flair",
        "hit_reaction_zh": "牙神三连杀被精准格挡看破，刀光四溅！",
        "hit_reaction_en": "reading Genjuro's triple strike and finding the gap!",
        "ko_finish_zh": "宿命之敌露出大破绽！霸王丸确反绝杀，一刀分胜负！",
        "ko_finish_en": "the fatal counter-hit seals the rival's fate with pure steel!",
    },
    "galford": {
        "title_zh": "加尔福特 (Galford)",
        "title_en": "Galford",
        "p2_style_zh": "甲贺忍武与忍犬突袭",
        "p2_style_en": "swift Koga ninjutsu and Poppy hound rush",
        "hit_reaction_zh": "加尔福特忍犬撕咬落空，身形受挫！",
        "hit_reaction_en": "neutralizing the hound rush and forcing a retreat!",
        "ko_finish_zh": "弧月斩逆风拔刀凌空拦截，加尔福特应声倒地！",
        "ko_finish_en": "an anti-air crescent blade intercepts the diving ninja!",
    },
    "nakoruru": {
        "title_zh": "娜可露露 (Nakoruru)",
        "title_en": "Nakoruru",
        "p2_style_zh": "神鹰突刺与极速飞刃",
        "p2_style_en": "aerial eagle assaults and lightning-fast blade zoning",
        "hit_reaction_zh": "神鹰俯冲被前刺强行化解，身法受制！",
        "hit_reaction_en": "grounding the eagle rush with disciplined neutral play!",
        "ko_finish_zh": "霸王丸稳健控距，重刀精准劈中落地破绽！",
        "ko_finish_en": "punishing the recovery with a crushing heavy slash!",
    },
    "chamcham": {
        "title_zh": "查姆查姆 (Cham Cham)",
        "title_en": "Cham Cham",
        "p2_style_zh": "野性回旋镖与空中扑击",
        "p2_style_en": "feral acrobatics and massive boomerang zoning",
        "hit_reaction_zh": "巨大回旋镖暗影被反手封锁，压制全场！",
        "hit_reaction_en": "dodging the boomerang curve and closing the distance!",
        "ko_finish_zh": "野性少女跳跃落地的瞬间，致命重斩彻底终结！",
        "ko_finish_en": "catching the wild leap on landing with absolute precision!",
    },
    "wanfu": {
        "title_zh": "王虎 (Wan-fu)",
        "title_en": "Wan-fu",
        "p2_style_zh": "巨柱猛劈与霸道肉弹冲撞",
        "p2_style_en": "pillar slam power and brute cannonball charges",
        "hit_reaction_zh": "王虎石柱大开大合，被霸王丸连续削血！",
        "hit_reaction_en": "chipping down the powerhouse while deflecting the heavy blows!",
        "ko_finish_zh": "肉弹冲撞撞上刀芒！逆势重劈斩断狂澜！",
        "ko_finish_en": "a decisive cross-slash cuts straight through the charge!",
    },
    "sieger": {
        "title_zh": "莱因哈特 (Sieger)",
        "title_en": "Neinhalt Sieger",
        "p2_style_zh": "铁臂圣骑士连环抱摔",
        "p2_style_en": "armored gauntlet strikes and close-range command grabs",
        "hit_reaction_zh": "贴身擒拿被长刀死死拒之门外，无法近身！",
        "hit_reaction_en": "keeping the armored knight at bay with superior reach!",
        "ko_finish_zh": "铁臂铠甲碎裂！确反重斩直接击穿刚硬防线！",
        "ko_finish_en": "breaking the impenetrable armor with a merciless counter-strike!",
    },
    "kyoshiro": {
        "title_zh": "千两狂死郎 (Kyoshiro)",
        "title_en": "Senryo Kyoshiro",
        "p2_style_zh": "歌舞伎薙刀连段与狂乱火炎",
        "p2_style_en": "kabuki naginata reach and blazing flame tricks",
        "hit_reaction_zh": "薙刀修长刀芒露出内圈盲区，被贴身逼近！",
        "hit_reaction_en": "slipping inside the naginata arc and seizing the tempo!",
        "ko_finish_zh": "越过薙刀盲区双跃下砸，以绝对气势斩灭火炎！",
        "ko_finish_en": "vaulting over the flames to deliver the finishing blow!",
    },
    "hanzo": {
        "title_zh": "服部半藏 (Hanzo)",
        "title_en": "Hattori Hanzo",
        "p2_style_zh": "莫迦投禁术与影分身突袭",
        "p2_style_en": "shadow clones and devastating Mozu Otoshi grabs",
        "hit_reaction_zh": "半藏近身投掷瞬间被快刀连刺强行拦截！",
        "hit_reaction_en": "stuffing the teleports with fast pokes and vigilant defense!",
        "ko_finish_zh": "分身虚幻被一刀劈开，伊贺上忍折戟于阵前！",
        "ko_finish_en": "cutting through the shadow illusion to strike true!",
    },
    "genan": {
        "title_zh": "不知火幻庵 (Gen-an)",
        "title_en": "Gen-an Shiranui",
        "p2_style_zh": "魔界滑铲与剧毒吹息",
        "p2_style_en": "demonic slides, claw rips, and poisonous breath",
        "hit_reaction_zh": "毒雾封路落空，霸王丸蹲防如同磐石！",
        "hit_reaction_en": "crouch-guarding the poison cloud like an iron fortress!",
        "ko_finish_zh": "滑铲落空破绽致命！反手重劈横扫魔怪，直接绝杀！",
        "ko_finish_en": "whiff-punishing the slide with a clean lethal slash!",
    },
    "nicotine": {
        "title_zh": "花讽院和仲 (Nicotine)",
        "title_en": "Nicotine Caffeine",
        "p2_style_zh": "封魔符咒与长杖乱舞",
        "p2_style_en": "exorcism seal wards and erratic staff flurries",
        "hit_reaction_zh": "封魔符贴脸袭来被侧身避过，刀锋直指破绽！",
        "hit_reaction_en": "weaving past the sacred talismans with decisive footwork!",
        "ko_finish_zh": "大巧不工！狂暴重刀破尽降魔符法，和仲败北！",
        "ko_finish_en": "raw sword power overcomes the monk's mystical barriers!",
    },
    "mizuki": {
        "title_zh": "罗将神水姬 (Mizuki)",
        "title_en": "Mizuki Rashojin",
        "p2_style_zh": "全屏神魔邪法与变猪妖术",
        "p2_style_en": "screen-filling demonic sorcery and transformation curses",
        "hit_reaction_zh": "魔界邪法被正面破除，魔气溃散无法成势！",
        "hit_reaction_en": "breaking through the netherworld magic with indomitable will!",
        "ko_finish_zh": "神魔终有尽时！全身狂气巅峰重劈，斩裂邪神！",
        "ko_finish_en": "a legendary heavy cleave banishes the demon god!",
    },
    "haowmaru": {
        "title_zh": "霸王丸镜像 (Haohmaru)",
        "title_en": "Haohmaru (Mirror Match)",
        "p2_style_zh": "狂刀剑法与同门豪烈气魄",
        "p2_style_en": "identical raw swordcraft and fierce warrior spirit",
        "hit_reaction_zh": "同门相争刀剑轰鸣，招式同源胜在变频！",
        "hit_reaction_en": "swords clashing in a dead heat of master instincts!",
        "ko_finish_zh": "孤剑破自我！霸王丸以更坚毅果断的一击取胜！",
        "ko_finish_en": "outsmarting the mirror self with superior frame-tight timing!",
    },
    "ukyo": {
        "title_zh": "橘右京 (Ukyo)",
        "title_en": "Ukyo Tachibana",
        "p2_style_zh": "居合残像踏前斩与秘剑细雪",
        "p2_style_en": "phantom iaido dashes and lightning-quick Sasameyuki slashes",
        "hit_reaction_zh": "右京残像踏前斩刚起，被格挡架势稳稳接下！",
        "hit_reaction_en": "snapping into guard to absorb the phantom rush!",
        "ko_finish_zh": "细雪刀光尚未收鞘，霸王丸双跃凌空大劈终结！",
        "ko_finish_en": "striking between the blade sheaths for an emphatic win!",
    },
    "jubei": {
        "title_zh": "柳生十兵卫 (Jubei)",
        "title_en": "Jubei Yagyu",
        "p2_style_zh": "新阴流双刀与迅猛水月刀",
        "p2_style_en": "Yagyu dual-katana techniques and crisp ground waves",
        "hit_reaction_zh": "水月刀掠地而过，被下蹲前压稳稳防御化解！",
        "hit_reaction_en": "withstanding the eight-phase fury with patient spacing!",
        "ko_finish_zh": "双刀露出空隙，确反重击呼啸而至，终结对决！",
        "ko_finish_en": "punishing the recovery with an unstoppable master strike!",
    },
    "charlotte": {
        "title_zh": "夏洛特 (Charlotte)",
        "title_en": "Charlotte Christine de Colde",
        "p2_style_zh": "凡尔赛西洋剑刺击与三角跳跃",
        "p2_style_en": "Versailles rapier thrusts and elegant triangular leaps",
        "hit_reaction_zh": "西洋细剑连环点刺，被弧月斩封死进路！",
        "hit_reaction_en": "parrying the rapier flurries with measured aggression!",
        "ko_finish_zh": "绝对力量轰碎凡尔赛剑芒，二段重刀彻底绝杀！",
        "ko_finish_en": "an anti-air arc slices clean through the airborne noble!",
    },
}


def fit_text_zh(short_text: str, normal_text: str, long_text: str, duration: float) -> str:
    """Select the Chinese text variant closest to natural reading speed (~4.2 chars/sec)."""
    target = duration * 4.2
    candidates = [short_text, normal_text, long_text]
    return min(candidates, key=lambda s: abs(len(s) - target))


def fit_text_en(short_text: str, normal_text: str, long_text: str, duration: float) -> str:
    """Select the English text variant closest to natural esports speaking speed (~2.6 words/sec)."""
    target_words = duration * 2.6
    candidates = [short_text, normal_text, long_text]
    return min(candidates, key=lambda s: abs(len(s.split()) - target_words))


class CommentaryEngine:
    """Synchronized Dual-Language (CN/EN) Sports Commentary generator for SS2 battle recordings."""

    def __init__(self, fps: float = 59.1856):
        self.fps = fps

    def step_to_sec(self, step: int) -> float:
        return (step * 2) / self.fps

    def sec_to_frame(self, sec: float) -> int:
        return int(round(sec * self.fps))

    def format_srt_time(self, sec: float) -> str:
        millis = int(round((sec - int(sec)) * 1000))
        total_seconds = int(sec)
        s = total_seconds % 60
        m = (total_seconds // 60) % 60
        h = total_seconds // 3600
        return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"

    def generate_commentary(
        self,
        match_id: str,
        video_filename: str,
        p1_key: str,
        p2_key: str,
        events: List[Dict[str, Any]],
        total_steps: int,
        hold_duration_sec: float = 10.0,
        winner: str = "haohmaru",
        score: tuple = (1, 0),
        actual_video_duration_sec: float | None = None,
    ) -> Dict[str, Any]:
        p2_info = CHAR_COMMENTARY_DATA.get(p2_key, {
            "title_zh": f"对手 {p2_key.upper()}",
            "title_en": f"{p2_key.upper()}",
            "p2_style_zh": "凶狠的街机杀招",
            "p2_style_en": "aggressive arcade combat style",
            "hit_reaction_zh": "对手猛攻被霸王丸精妙化解！",
            "hit_reaction_en": "turning defense into offense with sharp spacing!",
            "ko_finish_zh": "霸王丸抓准最后破绽重斩终结！",
            "ko_finish_en": "finding the lethal punish to end the match!",
        })

        if actual_video_duration_sec is not None and actual_video_duration_sec > hold_duration_sec:
            total_video_sec = actual_video_duration_sec
            match_combat_sec = max(3.0, actual_video_duration_sec - hold_duration_sec)
            sec_per_step = match_combat_sec / max(1, total_steps)
            step_to_sec = lambda s: s * sec_per_step
        else:
            match_combat_sec = max(3.0, self.step_to_sec(total_steps))
            total_video_sec = match_combat_sec + hold_duration_sec
            step_to_sec = self.step_to_sec

        subtitles: List[Dict[str, Any]] = []
        idx = 1

        # Check if events contain multi-round Bo3 data
        rounds_present = sorted(list(set(e.get("round", 1) for e in events))) if events else [1]
        is_bo3 = (len(rounds_present) > 1) or (score[0] + score[1] >= 2)

        if not is_bo3:
            # Single-round commentary generation
            op_dur = min(2.4, match_combat_sec * 0.35)
            zh_text = fit_text_zh(
                f"比赛打响！霸王丸迎战{p2_info['title_zh']}！",
                f"决战正式开始！霸王丸手按名刀河豚毒，迎战{p2_info['title_zh']}！",
                f"各位观众欢迎来到巅峰赛场！霸王丸手按名刀河豚毒，全神贯注迎战强敌{p2_info['title_zh']}！",
                op_dur,
            )
            en_text = fit_text_en(
                f"Round 1, fight! Haohmaru vs {p2_info['title_en']}!",
                f"The battle begins! Haohmaru steps into the arena against {p2_info['title_en']}!",
                f"Welcome fight fans! Blade drawn, Haohmaru clashes with {p2_info['title_en']} in a high-stakes duel!",
                op_dur,
            )
            subtitles.append({
                "index": idx,
                "start_time_sec": 0.0,
                "end_time_sec": round(op_dur, 2),
                "start_frame": 0,
                "end_frame": self.sec_to_frame(op_dur),
                "speaker": "现场解说",
                "text": zh_text,
                "text_zh": zh_text,
                "text_en": en_text,
                "event_type": "MATCH_START",
            })
            idx += 1

            last_t = op_dur
            combat_remaining = match_combat_sec - op_dur
            if combat_remaining > 2.0:
                mid_end = op_dur + combat_remaining * 0.5
                mid_dur = mid_end - last_t
                zh_text = fit_text_zh(
                    "霸王丸沉稳试探，精准控距！",
                    f"双方展开激烈立回！霸王丸沉稳控距，寻找对手破绽！",
                    f"双方在场中保持极限立回！霸王丸以精准刺击压制，{p2_info['hit_reaction_zh']}",
                    mid_dur,
                )
                en_text = fit_text_en(
                    "Disciplined spacing and neutral control from Haohmaru!",
                    f"Intense neutral battle! Haohmaru stays patient, {p2_info['hit_reaction_en']}",
                    f"Blade to blade in high-tempo neutral! Haohmaru establishes range control, {p2_info['hit_reaction_en']}",
                    mid_dur,
                )
                subtitles.append({
                    "index": idx,
                    "start_time_sec": round(last_t, 2),
                    "end_time_sec": round(mid_end, 2),
                    "start_frame": self.sec_to_frame(last_t),
                    "end_frame": self.sec_to_frame(mid_end),
                    "speaker": "现场解说",
                    "text": zh_text,
                    "text_zh": zh_text,
                    "text_en": en_text,
                    "event_type": "MID_COMBAT",
                })
                idx += 1
                last_t = mid_end

            ko_end = match_combat_sec + 1.2
            ko_dur = ko_end - last_t
            zh_text = fit_text_zh(
                "决胜一击！重斩终结，一本！",
                f"斩！{p2_info['ko_finish_zh']} 裁判挥旗判定——一本！",
                f"大破绽出现！霸王丸核心重斩雷霆劈落！{p2_info['ko_finish_zh']} 裁判挥旗——一本！大胜！",
                ko_dur,
            )
            en_text = fit_text_en(
                "Decisive heavy strike! Ippon!",
                f"Clean hit! {p2_info['ko_finish_en']} The referee flags Ippon!",
                f"Huge whiff punish! A thunderous heavy slash connects! {p2_info['ko_finish_en']} Ippon!",
                ko_dur,
            )
            subtitles.append({
                "index": idx,
                "start_time_sec": round(last_t, 2),
                "end_time_sec": round(ko_end, 2),
                "start_frame": self.sec_to_frame(last_t),
                "end_frame": self.sec_to_frame(ko_end),
                "speaker": "现场解说",
                "text": zh_text,
                "text_zh": zh_text,
                "text_en": en_text,
                "event_type": "KO_FINISH",
            })
            idx += 1
            last_t = ko_end

        else:
            # Multi-round Bo3 commentary generation
            round_boundaries: Dict[int, Dict[str, int]] = {}
            for r in rounds_present:
                r_events = [e for e in events if e.get("round", 1) == r]
                if r_events:
                    round_boundaries[r] = {
                        "start_step": r_events[0]["step"],
                        "end_step": r_events[-1]["step"],
                    }

            current_score = [0, 0]
            last_t = 0.0

            for r_idx, r in enumerate(rounds_present, 1):
                bounds = round_boundaries.get(r, {"start_step": 0, "end_step": total_steps})
                r_start_sec = step_to_sec(bounds["start_step"])
                r_end_sec = step_to_sec(bounds["end_step"])
                r_dur = max(2.5, r_end_sec - r_start_sec)

                # Round Intro
                intro_dur = min(2.5, r_dur * 0.35)
                intro_end = r_start_sec + intro_dur
                if r == 1:
                    zh_text = fit_text_zh(
                        f"全场Bo3开战！霸王丸迎战{p2_info['title_zh']}！",
                        f"三局两胜决战正式打响！霸王丸按刀出鞘，首局迎战{p2_info['title_zh']}！",
                        f"观众朋友们欢迎来到三局两胜巅峰对决！霸王丸按刀肃立，首局迎战强敌{p2_info['title_zh']}！",
                        intro_dur,
                    )
                    en_text = fit_text_en(
                        f"Bo3 match underway! Haohmaru vs {p2_info['title_en']}!",
                        f"Best of 3 officially underway! Haohmaru draws his blade against {p2_info['title_en']} in Round 1!",
                        f"Welcome to this championship Best of 3! Haohmaru takes the stage in Round 1 against {p2_info['title_en']}!",
                        intro_dur,
                    )
                elif r == 2:
                    zh_text = fit_text_zh(
                        "第二局二本目！霸王丸手握赛点！",
                        "二本目开打！霸王丸手握赛点，对手背水一战疯狂反扑！",
                        "比赛进入第二局二本目！霸王丸手握赛点乘胜追击，对手背水一战展开疯狂反扑！",
                        intro_dur,
                    )
                    en_text = fit_text_en(
                        "Round 2! Haohmaru on match point!",
                        "Second round underway! Haohmaru sits on match point while his opponent fights for survival!",
                        "Moving into Round 2! Haohmaru commands match point, ready to close out against a desperate counter-attack!",
                        intro_dur,
                    )
                else:
                    zh_text = fit_text_zh(
                        "决胜局三本目！一战定乾坤！",
                        "比分一平进入决胜局！双方底牌尽出，一战分生死！",
                        "比赛进入残酷决胜局！双方比分一平，全场屏息凝神，最后一战分生死！",
                        intro_dur,
                    )
                    en_text = fit_text_en(
                        "Final round, Round 3! All on the line!",
                        "Tied at 1-1! Both warriors unleash everything in this decisive final round!",
                        "The ultimate tiebreaker! It all comes down to Round 3, pure survival on the line!",
                        intro_dur,
                    )

                subtitles.append({
                    "index": idx,
                    "start_time_sec": round(r_start_sec, 2),
                    "end_time_sec": round(intro_end, 2),
                    "start_frame": self.sec_to_frame(r_start_sec),
                    "end_frame": self.sec_to_frame(intro_end),
                    "speaker": "现场解说",
                    "text": zh_text,
                    "text_zh": zh_text,
                    "text_en": en_text,
                    "event_type": f"ROUND_{r}_START",
                })
                idx += 1

                # Round Mid Combat
                mid_end = r_start_sec + r_dur * 0.75
                mid_dur = max(1.5, mid_end - intro_end)
                zh_text = fit_text_zh(
                    f"双方激烈攻防！{p2_info['hit_reaction_zh']}",
                    f"刀光交错！霸王丸严阵以待，{p2_info['hit_reaction_zh']}",
                    f"场中刀光四溢！霸王丸以精湛走位连续确反，{p2_info['hit_reaction_zh']}",
                    mid_dur,
                )
                en_text = fit_text_en(
                    f"Fierce clashes! {p2_info['hit_reaction_en']}",
                    f"Trading blows! Haohmaru holds his ground, {p2_info['hit_reaction_en']}",
                    f"High-level spacing exchanges! Haohmaru converts the counter, {p2_info['hit_reaction_en']}",
                    mid_dur,
                )
                subtitles.append({
                    "index": idx,
                    "start_time_sec": round(intro_end, 2),
                    "end_time_sec": round(mid_end, 2),
                    "start_frame": self.sec_to_frame(intro_end),
                    "end_frame": self.sec_to_frame(mid_end),
                    "speaker": "现场解说",
                    "text": zh_text,
                    "text_zh": zh_text,
                    "text_en": en_text,
                    "event_type": f"ROUND_{r}_COMBAT",
                })
                idx += 1

                # Round KO Moment
                ko_dur = max(2.0, r_end_sec - mid_end + 1.0)
                ko_end = r_end_sec + 1.0
                if r_idx < len(rounds_present):
                    current_score[0] += 1
                    zh_text = fit_text_zh(
                        f"斩！重劈得手，第{r}局一本！",
                        f"好刀法！{p2_info['ko_finish_zh']} 裁判举旗——第{r}局一本！",
                        f"电光火石！大破绽确反致命！{p2_info['ko_finish_zh']} 裁判判定——一本！霸王丸先拔头筹！",
                        ko_dur,
                    )
                    en_text = fit_text_en(
                        f"Clean slash! Round {r} to Haohmaru, Ippon!",
                        f"Masterful timing! {p2_info['ko_finish_en']} The referee signals Ippon!",
                        f"Lightning reflex! A devastating heavy punish connects! {p2_info['ko_finish_en']} Haohmaru takes the lead!",
                        ko_dur,
                    )
                else:
                    current_score[0] = score[0]
                    current_score[1] = score[1]
                    zh_text = fit_text_zh(
                        f"决杀！终极重斩，比赛结束！",
                        f"雷霆一击！{p2_info['ko_finish_zh']} 裁判挥旗判定——终结胜出！",
                        f"狂气全开！霸王丸绝杀重劈斩断乾坤！{p2_info['ko_finish_zh']} 裁判挥旗——比赛结束！霸王丸获胜！",
                        ko_dur,
                    )
                    en_text = fit_text_en(
                        "Fatal slash! That's the match!",
                        f"Thunder strike! {p2_info['ko_finish_en']} The referee waves it off, VICTORY!",
                        f"Unstoppable power! Haohmaru delivers the ultimate heavy slash! {p2_info['ko_finish_en']} Match over!",
                        ko_dur,
                    )

                subtitles.append({
                    "index": idx,
                    "start_time_sec": round(mid_end, 2),
                    "end_time_sec": round(ko_end, 2),
                    "start_frame": self.sec_to_frame(mid_end),
                    "end_frame": self.sec_to_frame(ko_end),
                    "speaker": "现场解说",
                    "text": zh_text,
                    "text_zh": zh_text,
                    "text_en": en_text,
                    "event_type": f"ROUND_{r}_KO",
                })
                idx += 1
                last_t = ko_end

        # Post-match Celebration (10s hold divided into 3 natural cues)
        # Cue 4A: Slow-mo and Sheathing
        h_a_start = last_t
        h_a_end = last_t + 3.6
        h_a_dur = h_a_end - h_a_start
        zh_text = fit_text_zh(
            "霸王丸帅气收刀，宗师风范尽显！",
            "特写画面！霸王丸反手收刀入鞘，动作干净利落，宗师风范！",
            "慢动作特写给到全场！胜负已定，霸王丸反手收刀入鞘，神态自若，尽显一代剑豪风采！",
            h_a_dur,
        )
        en_text = fit_text_en(
            "Clean sheath! Pure samurai discipline!",
            "Camera pan on the winner! Haohmaru smoothly sheathes his blade with effortless master composure!",
            "Slow-motion replay across the arena! Dust settles as Haohmaru sheathes the blade, exhibiting the poise of a true swordmaster!",
            h_a_dur,
        )
        subtitles.append({
            "index": idx,
            "start_time_sec": round(h_a_start, 2),
            "end_time_sec": round(h_a_end, 2),
            "start_frame": self.sec_to_frame(h_a_start),
            "end_frame": self.sec_to_frame(h_a_end),
            "speaker": "现场解说",
            "text": zh_text,
            "text_zh": zh_text,
            "text_en": en_text,
            "event_type": "CELEBRATION_SHEATHE",
        })
        idx += 1

        # Cue 4B: Drinking Sake & Victory Quotes
        h_b_start = h_a_end
        h_b_end = min(h_b_start + 3.8, total_video_sec - 1.2)
        h_b_dur = h_b_end - h_b_start
        zh_text = fit_text_zh(
            "掏出美酒仰天畅饮，豪迈大笑！",
            "仰天长笑，掏出美酒开怀畅饮！经典胜出台词响彻赛场！",
            "仰天豪迈长笑，掏出酒壶畅饮烈酒！霸王丸霸气喊出胜利台词，整场压制行云流水！",
            h_b_dur,
        )
        en_text = fit_text_en(
            "Toasting with the victory sake jar and a hearty laugh!",
            "Drinking deeply from his sake bottle with that booming signature laugh! Classic victory quote delivers!",
            "A hearty laugh echoes across the stage! Haohmaru gulps his victory sake, shouting his iconic triumph line!",
            h_b_dur,
        )
        subtitles.append({
            "index": idx,
            "start_time_sec": round(h_b_start, 2),
            "end_time_sec": round(h_b_end, 2),
            "start_frame": self.sec_to_frame(h_b_start),
            "end_frame": self.sec_to_frame(h_b_end),
            "speaker": "现场解说",
            "text": zh_text,
            "text_zh": zh_text,
            "text_en": en_text,
            "event_type": "CELEBRATION_QUOTE",
        })
        idx += 1

        # Cue 4C & 4D: Match Wrap-up & Settlement Screen
        h_c_start = h_b_end
        rem_dur = total_video_sec - h_c_start
        if rem_dur > 6.0:
            # Split into Match Wrap-up and Final Score Settlement Screen
            h_c_end = h_c_start + 4.5
            h_c_dur = h_c_end - h_c_start
            zh_text = fit_text_zh(
                f"最终大比分 {score[0]}-{score[1]}，恭喜霸王丸斩获全胜！",
                f"最终大比分锁定在 {score[0]}-{score[1]}！恭喜霸王丸拿下三局两胜，全场压制！",
                f"全场大比分定格在 {score[0]}-{score[1]}！恭喜霸王丸斩获三局两胜最终总决胜，打出教科书级立回压制！",
                h_c_dur,
            )
            en_text = fit_text_en(
                f"Final score {score[0]}-{score[1]}! Congratulations to Haohmaru!",
                f"Final score locked in at {score[0]}-{score[1]}! Haohmaru takes the Bo3 victory in dominant fashion!",
                f"The series concludes {score[0]}-{score[1]}! A textbook spacing masterclass from Haohmaru secures the series win!",
                h_c_dur,
            )
            subtitles.append({
                "index": idx,
                "start_time_sec": round(h_c_start, 2),
                "end_time_sec": round(h_c_end, 2),
                "start_frame": self.sec_to_frame(h_c_start),
                "end_frame": self.sec_to_frame(h_c_end),
                "speaker": "现场解说",
                "text": zh_text,
                "text_zh": zh_text,
                "text_en": en_text,
                "event_type": "MATCH_WRAPUP",
            })
            idx += 1

            # Cue 4D: Arcade Bonus & Total Score Settlement Screen
            h_d_start = h_c_end
            h_d_end = total_video_sec
            h_d_dur = h_d_end - h_d_start
            zh_text = fit_text_zh(
                "进入战绩结算画面，总得分锁定！",
                "画面切入最终战绩结算！体力奖励与过关耗时清算完毕，锁定全胜！",
                "画面切入街机最终积分与战绩结算！生命残量加成与耗时得分全部清算，完美锁定本轮胜局！",
                h_d_dur,
            )
            en_text = fit_text_en(
                "Moving to the final score and bonus tally screen!",
                "Transitioning into the settlement screen! Life bonus and clear time calculated, match complete!",
                "Entering the official arcade bonus settlement! Remaining life and clear time tallied into a decisive high score!",
                h_d_dur,
            )
            subtitles.append({
                "index": idx,
                "start_time_sec": round(h_d_start, 2),
                "end_time_sec": round(h_d_end, 2),
                "start_frame": self.sec_to_frame(h_d_start),
                "end_frame": self.sec_to_frame(h_d_end),
                "speaker": "现场解说",
                "text": zh_text,
                "text_zh": zh_text,
                "text_en": en_text,
                "event_type": "SETTLEMENT_SCREEN",
            })
        else:
            h_c_end = total_video_sec
            h_c_dur = h_c_end - h_c_start
            zh_text = fit_text_zh(
                f"最终大比分 {score[0]}-{score[1]}，恭喜霸王丸斩获全胜！",
                f"最终大比分锁定在 {score[0]}-{score[1]}！恭喜霸王丸拿下三局两胜，感谢收看！",
                f"全场大比分定格在 {score[0]}-{score[1]}！恭喜霸王丸斩获三局两胜最终总决胜，感谢各位观众收看本场精彩绝杀！",
                h_c_dur,
            )
            en_text = fit_text_en(
                f"Final score {score[0]}-{score[1]}! Congratulations to Haohmaru!",
                f"Final score locked in at {score[0]}-{score[1]}! Haohmaru takes the Bo3 victory, thank you for watching!",
                f"The series concludes {score[0]}-{score[1]}! A stellar Bo3 showcase from Haohmaru, thanks to everyone for watching!",
                h_c_dur,
            )
            subtitles.append({
                "index": idx,
                "start_time_sec": round(h_c_start, 2),
                "end_time_sec": round(h_c_end, 2),
                "start_frame": self.sec_to_frame(h_c_start),
                "end_frame": self.sec_to_frame(h_c_end),
                "speaker": "现场解说",
                "text": zh_text,
                "text_zh": zh_text,
                "text_en": en_text,
                "event_type": "MATCH_WRAPUP",
            })

        # Ensure strictly monotonic non-overlapping subtitle intervals
        for i in range(len(subtitles) - 1):
            if subtitles[i]["end_time_sec"] > subtitles[i+1]["start_time_sec"]:
                subtitles[i]["end_time_sec"] = subtitles[i+1]["start_time_sec"]
                subtitles[i]["end_frame"] = self.sec_to_frame(subtitles[i]["end_time_sec"])

        # Calculate character and word statistics
        for s in subtitles:
            s["char_count_zh"] = len(s["text_zh"])
            s["word_count_en"] = len(s["text_en"].split())
            dur = max(0.1, s["end_time_sec"] - s["start_time_sec"])
            s["chars_per_sec_zh"] = round(s["char_count_zh"] / dur, 1)
            s["words_per_sec_en"] = round(s["word_count_en"] / dur, 1)

        result_json = {
            "match_id": match_id,
            "video_file": video_filename,
            "p1": {"key": p1_key, "name_zh": "霸王丸", "name_en": "Haohmaru"},
            "p2": {"key": p2_key, "name_zh": p2_info["title_zh"], "name_en": p2_info["title_en"]},
            "mode": "bo3" if is_bo3 else "single",
            "total_combat_steps": total_steps,
            "combat_duration_sec": round(match_combat_sec, 2),
            "hold_duration_sec": round(hold_duration_sec, 2),
            "total_video_duration_sec": round(total_video_sec, 2),
            "fps": round(self.fps, 2),
            "winner": winner,
            "final_score": f"{score[0]}-{score[1]}",
            "summary_zh": f"霸王丸迎战{p2_info['title_zh']}，以精湛的立回控距与致命重斩在{total_steps}步内完成终结斩杀，斩获胜利！",
            "summary_en": f"Haohmaru faces {p2_info['title_en']}, securing a decisive victory through superior spacing and lethal heavy punishes in {total_steps} steps!",
            "timeline": subtitles,
        }

        return result_json

    def export_srt(self, commentary_data: Dict[str, Any], output_srt_path: Path, lang: str = "zh"):
        """Export standard SubRip (.srt) subtitle file matching the MP4 timeline."""
        lines = []
        for s in commentary_data["timeline"]:
            idx = s["index"]
            t_start = self.format_srt_time(s["start_time_sec"])
            t_end = self.format_srt_time(s["end_time_sec"])
            txt = s["text_en"] if lang == "en" else s.get("text_zh", s.get("text", ""))
            lines.append(f"{idx}\n{t_start} --> {t_end}\n{txt}\n")
        output_srt_path.write_text("\n".join(lines), encoding="utf-8")


def probe_video_duration(video_path: Path) -> float | None:
    """Probes the exact duration of an MP4/AVI video file using ffprobe."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            info = json.loads(res.stdout)
            return float(info["format"]["duration"])
    except Exception:
        pass
    return None


def generate_and_save_commentary_files(
    match_id: str,
    video_path: Path,
    p1_key: str,
    p2_key: str,
    events: List[Dict[str, Any]],
    total_steps: int,
    hold_duration_sec: float = 10.0,
    winner: str = "haohmaru",
    score: tuple = (1, 0),
) -> Tuple[Path, Path, Path]:
    """Generates and writes <video_stem>_commentary.json, <video_stem>_zh.srt, and <video_stem>_en.srt."""
    engine = CommentaryEngine()
    actual_dur = probe_video_duration(video_path) if video_path.exists() else None
    data = engine.generate_commentary(
        match_id=match_id,
        video_filename=video_path.name,
        p1_key=p1_key,
        p2_key=p2_key,
        events=events,
        total_steps=total_steps,
        hold_duration_sec=hold_duration_sec,
        winner=winner,
        score=score,
        actual_video_duration_sec=actual_dur,
    )

    base_stem = video_path.stem
    json_path = video_path.parent / f"{base_stem}_commentary.json"
    srt_zh_path = video_path.parent / f"{base_stem}_zh.srt"
    srt_en_path = video_path.parent / f"{base_stem}_en.srt"
    srt_default_path = video_path.parent / f"{base_stem}.srt"

    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    engine.export_srt(data, srt_zh_path, lang="zh")
    engine.export_srt(data, srt_en_path, lang="en")
    engine.export_srt(data, srt_default_path, lang="zh")

    return json_path, srt_zh_path, srt_en_path
