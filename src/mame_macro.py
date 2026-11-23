"""Macro engine: YAML movesets -> mirrored ACTION sequences (T6).

Authors face right; mirror_dir flips L/R when P1 is on the right side
(own_x > opp_x), so one action index always means "toward the opponent".
Pure functions — unit-testable without MAME.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # -I mode: user site-packages excluded
    yaml = None

from mame_types import DIR_MASKS

# button bits (neogeo ioport masks, T1 probe)
BTN_A, BTN_B, BTN_C, BTN_D = 0x10, 0x20, 0x40, 0x80

MIRROR = {"L": "R", "R": "L", "UL": "UR", "UR": "UL",
          "DL": "DR", "DR": "DL", "DF": "DL"}


def mirror_dir(d: str) -> str:
    if d in MIRROR:
        return MIRROR[d]
    return d


# mask-level mirror (single source of truth; string names for YAML tokens)
MIRROR_MASK = {DIR_MASKS[k]: DIR_MASKS[mirror_dir(k)] for k in DIR_MASKS}


@dataclass
class Step:
    dir_mask: int
    btn_mask: int
    frames: int


def parse_token(tok: str) -> tuple[int, int]:
    """'DR+A' -> (dir_mask, btn_mask); 'N' -> (0,0)."""
    d_part, btn_part = "", ""
    for ch in tok.split("+"):
        if ch in DIR_MASKS:
            d_part = ch
        elif ch in ("A", "B", "C", "D"):
            btn_part += ch
    dir_mask = DIR_MASKS.get(d_part, 0)
    btn_mask = 0
    for ch in btn_part:
        btn_mask |= {"A": BTN_A, "B": BTN_B, "C": BTN_C, "D": BTN_D}[ch]
    return dir_mask, btn_mask


@dataclass
class Macro:
    name: str
    steps: list[Step]
    requires_weapon: bool = True
    requires_rage: bool = False

    def mirrored(self, facing_right: bool) -> list[Step]:
        """Steps with directions flipped when facing LEFT."""
        if facing_right:
            return list(self.steps)
        out = []
        for s in self.steps:
            out.append(Step(MIRROR_MASK.get(s.dir_mask, s.dir_mask),
                            s.btn_mask, s.frames))
        return out

    def actions(self, facing_right: bool) -> list[tuple[int, int, int, int]]:
        """(dir_mask, btn_mask, press_frames, gap_frames) per step.

        gap MUST be >= press_frames: the bridge releases held inputs when
        the next command arrives, so wait_frames < press_frames truncates
        the hold (caused the crouch-slash fireball bug 2026-11-05).
        """
        out = []
        for s in self.mirrored(facing_right):
            gap = s.frames + 2
            out.append((s.dir_mask, s.btn_mask, s.frames, gap))
        return out


def _mini_yaml_load(text: str) -> dict:
    """Minimal loader for OUR moveset/spec YAML subset (no external deps).

    Handles:  mappings,  list items, inline flow
    lists , quoted strings, comments, blank lines.
    Barewords inside flow lists are quoted then literal_eval'd.
    """
    import ast
    import re as _re

    def conv(v: str):
        v = v.strip()
        if v.startswith("["):
            q = _re.sub(r"([A-Za-z_][A-Za-z0-9_+]*)", lambda _m: chr(39) + _m.group(1) + chr(39), v)
            return ast.literal_eval(q)
        if v.startswith(("'", '"')):
            return v[1:-1]
        try:
            return int(v)
        except ValueError:
            pass
        if v in ("true", "True"):
            return True
        if v in ("false", "False"):
            return False
        return v

    root: dict = {}
    stack = [(-1, root)]  # (indent, container)
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        if s.startswith("- "):
            item_indent = indent + 2
            key, _, val = s[2:].partition(":")
            while stack and stack[-1][0] > indent:
                stack.pop()
            parent = stack[-1][1]
            if not isinstance(parent, list):
                raise ValueError(f"list item outside list: {raw}")
            item: dict = {}
            parent.append(item)
            if val.strip():
                item[key.strip()] = conv(val)
            else:
                item[key.strip()] = {}
            stack.append((item_indent, item[key.strip()]
                          if isinstance(item[key.strip()], dict) else item))
            continue
        key, _, val = s.partition(":")
        key, val = key.strip(), val.strip()
        # attach to nearest container with indent < N; a LIST at the same
        # indent means the key ends the list (mapping sibling follows)
        while len(stack) > 1 and (
                stack[-1][0] > indent
                or (stack[-1][0] == indent and isinstance(stack[-1][1], list))):
            stack.pop()
        container = stack[-1][1]
        if val == "":
            container[key] = []
            stack.append((indent, container[key]))
        else:
            container[key] = conv(val)
    return root


class Moveset:
    def __init__(self, path: Path):
        text = path.read_text(encoding="utf-8")
        if yaml is not None:
            data = yaml.safe_load(text)
        else:
            data = _mini_yaml_load(text)
        self.character = data.get("character", "unknown")
        self.macros: dict[str, Macro] = {}
        for m in data.get("macros", []):
            steps = []
            for tok, frames in m["steps"]:
                dm, bm = parse_token(tok)
                steps.append(Step(dm, bm, frames))
            self.macros[m["name"]] = Macro(
                m["name"], steps,
                m.get("requires_weapon", True),
                m.get("requires_rage", False))
        self.unarmed = []
        for m in data.get("unarmed", []):
            steps = []
            for tok, frames in m["steps"]:
                dm, bm = parse_token(tok)
                steps.append(Step(dm, bm, frames))
            self.unarmed.append(Macro(m["name"], steps, False))

    def get(self, name: str, *, has_weapon: bool = True) -> Macro:
        if not has_weapon:
            for m in self.unarmed:
                if m.name == name:
                    return m
            raise KeyError(f"{name} unavailable unarmed")
        return self.macros[name]
