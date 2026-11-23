"""
moe_roster.py - Single Source of Truth for Opponent Roster, Action Semantics,
and Manifest Architecture in Samurai Shodown II MoE System.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Shared Canonical Action Intents across all MoE modules
INTENTS: Dict[int, str] = {
    0: "APPROACH",   # 前冲逼近 (突进压制)
    1: "RETREAT",    # 后撤拉开 (战术后撤)
    2: "POKE",       # 轻刺试探 (快拳快剑试探)
    3: "SLASH",      # 重斩砍杀 (核心输出大劈)
    4: "ANTI_AIR",   # 升龙弧月 (对空拦截绝技)
    5: "PUNISH",     # 确反重击 (抓破绽大伤害确反)
    6: "FIREBALL",   # 旋风烈斩 (烈风斩飞行道具牵制)
    7: "GUARD",      # 站立格挡 (格挡防御稳固架势)
    8: "JUMP",       # 起跳压制 (跳斩起跳下砸压制)
}

ACT_NAMES: Dict[int, str] = {
    0: "前冲逼近 (APPROACH)",
    1: "后撤拉开 (RETREAT)",
    2: "轻刺试探 (POKE)",
    3: "重斩砍杀 (SLASH)",
    4: "升龙弧月 (ANTI_AIR)",
    5: "确反重击 (PUNISH)",
    6: "旋风烈斩/发波 (FIREBALL)",
    7: "站立格挡 (GUARD)",
    8: "起跳压制 (JUMP)",
}

# Canonical 16-Opponent Roster in Samurai Shodown II (IDs aligned with SS2_CHAR_ID_MAP 0x00..0x0F)
ROSTER: List[Dict[str, Any]] = [
    {
        "key": "earthquake",
        "id": 0x08,
        "name": "地震 (Earthquake)",
        "sta": "earthquake.sta",
        "desc": "巨型忍者，开局瞬移与泰山压顶",
    },
    {
        "key": "genjuro",
        "id": 0x0D,
        "name": "牙神幻十郎 (Genjuro)",
        "sta": "genjuro.sta",
        "desc": "宿敌剑客，三连杀与光翼刃极度凶猛",
    },
    {
        "key": "galford",
        "id": 0x03,
        "name": "加尔福特 (Galford)",
        "sta": "galford.sta",
        "desc": "甲贺忍术与忍犬雷电突袭",
    },
    {
        "key": "nakoruru",
        "id": 0x01,
        "name": "娜可露露 (Nakoruru)",
        "sta": "nakoruru.sta",
        "desc": "巫女神鹰突刺与极速地空压制",
    },
    {
        "key": "chamcham",
        "id": 0x0A,
        "name": "查姆查姆 (Cham Cham)",
        "sta": "chamcham.sta",
        "desc": "野性少女，巨大回旋镖与空中抓击",
    },
    {
        "key": "wanfu",
        "id": 0x04,
        "name": "王虎 (Wan-fu)",
        "sta": "wanfu.sta",
        "desc": "巨柱猛劈与霸道肉弹冲撞",
    },
    {
        "key": "sieger",
        "id": 0x0B,
        "name": "莱因哈特 (Sieger)",
        "sta": "sieger.sta",
        "desc": "铁臂圣骑士，近身连续擒拿抱摔",
    },
    {
        "key": "kyoshiro",
        "id": 0x06,
        "name": "千两狂死郎 (Kyoshiro)",
        "sta": "kyoshiro.sta",
        "desc": "歌舞伎薙刀连段与狂乱火炎",
    },
    {
        "key": "hanzo",
        "id": 0x02,
        "name": "服部半藏 (Hanzo)",
        "sta": "hanzo.sta",
        "desc": "伊贺上忍，影分身与近身莫迦投",
    },
    {
        "key": "genan",
        "id": 0x07,
        "name": "不知火幻庵 (Gen-an)",
        "sta": "genan.sta",
        "desc": "魔界滑铲、毒吹息与爪击连斩",
    },
    {
        "key": "nicotine",
        "id": 0x0C,
        "name": "花讽院和仲 (Nicotine)",
        "sta": "nicotine.sta",
        "desc": "降魔高僧，封魔符咒与长杖乱击",
    },
    {
        "key": "mizuki",
        "id": 0x0E,
        "name": "罗将神水姬 (Mizuki-Boss)",
        "sta": "mizuki.sta",
        "desc": "最终终极Boss，神魔全屏邪法与变猪术",
    },
    {
        "key": "haowmaru",
        "id": 0x00,
        "name": "霸王丸 (Haohmaru-Mirror)",
        "sta": "haowmaru.sta",
        "desc": "自我镜像对决，孤剑破万法",
    },
    {
        "key": "ukyo",
        "id": 0x05,
        "name": "橘右京 (Ukyo)",
        "sta": "ukyo.sta",
        "desc": "神梦梦想流居合剑客，残像踏前斩与秘剑细雪",
    },
    {
        "key": "jubei",
        "id": 0x09,
        "name": "柳生十兵卫 (Jubei)",
        "sta": "jubei.sta",
        "desc": "新阴流双刀剑豪，八相发破与水月刀",
    },
    {
        "key": "charlotte",
        "id": 0x0F,
        "name": "夏洛特 (Charlotte)",
        "sta": "charlotte.sta",
        "desc": "凡尔赛西洋剑贵族，破空剑刺与三角跳跃",
    },
]

ROSTER_BY_KEY: Dict[str, Dict[str, Any]] = {c["key"]: c for c in ROSTER}


def get_manifest_path(experts_dir: Optional[Path] = None) -> Path:
    base = experts_dir or (PROJECT_ROOT / "models" / "experts")
    return base / "manifest.json"


def load_manifest(experts_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = get_manifest_path(experts_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_target_verified(key: str, experts_dir: Optional[Path] = None) -> bool:
    manifest = load_manifest(experts_dir)
    entry = manifest.get(key, {})
    return entry.get("status") == "VERIFIED"


def save_manifest_entry(
    key: str,
    status: str,
    score: tuple,
    steps: int,
    verified_runs: str = "3/3",
    strategy_summary: str = "",
    experts_dir: Optional[Path] = None,
) -> None:
    manifest_path = get_manifest_path(experts_dir)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(experts_dir)

    manifest[key] = {
        "target_key": key,
        "status": status,
        "verified_runs": verified_runs,
        "score": f"{score[0]}-{score[1]}",
        "steps": steps,
        "strategy": strategy_summary,
        "updated_at": Path(PROJECT_ROOT / "logs").stat().st_mtime if (PROJECT_ROOT / "logs").exists() else 0,
    }

    # Write atomically
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(manifest_path)
