"""Run profiles for the SS2 MAME bridge (T3; docs/mame/T3_后台运行与加速.md).

watch: visible window + sound, 1x — human acceptance / viewing only.
train: no window (-video none), no sound, throttled 1x-4x — daily automation.
fast:  no window, no sound, unthrottled — RL / bulk collection.

Speed changes at runtime go through the bridge SET command
(machine.video.throttled / throttle_rate) — no restart needed (T3-T08).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    windowed: bool
    extra: tuple[str, ...]
    note: str


PROFILES: dict[str, Profile] = {
    "watch": Profile("watch", True, (), "visible window + sound, 1x"),
    "train": Profile("train", False, ("-sound", "none"),
                     "headless, throttled (runtime throttle_rate 1-4x)"),
    "fast": Profile("fast", False,
                    ("-sound", "none", "-nothrottle", "-frameskip", "0"),
                    "headless, unthrottled max speed"),
}


def resolve(name: str) -> Profile:
    if name not in PROFILES:
        raise ValueError(f"unknown profile {name!r}; choices: {sorted(PROFILES)}")
    return PROFILES[name]
