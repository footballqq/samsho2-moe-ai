"""
demo_player.py - Interactive demonstration player for Samurai Shodown II MoE experts.
Launches MAME in visible windowed mode, allowing the user to watch the MoE agent fight
against their chosen opponent in real time with continuous Best-of-3 and full logging.
"""
from __future__ import annotations

import sys
import os
import time
import argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from mame_client import BridgeSession
from mame_gym import SS2RoundEnv
from mame_moe import MoEAgent
from mame_hitbox import normalize_char_name
from bo3_controller import Bo3MatchController
from demo_logger import DemoLogger

from moe_roster import ROSTER, load_manifest, ACT_NAMES


def play_demo(
    target_key: str = "earthquake",
    speed: int = 1,
    windowed: bool = True,
    mode: str = "bo3",
):
    # Support numeric target index if passed directly
    if str(target_key).isdigit():
        idx = int(target_key)
        if 1 <= idx <= len(ROSTER):
            target_key = ROSTER[idx - 1]["key"]
    canon = normalize_char_name(target_key)
    inst = "rl_moe_demo"

    # Distribute states for this instance
    from train_rl import distribute_states
    distribute_states(inst, [canon])

    # Initialize loggers and match controller
    log_dir = PROJECT / "logs" / "demos"
    logger = DemoLogger(
        log_dir=log_dir,
        p1_name="haohmaru",
        p2_name=canon,
        mode=mode,
        speed=float(speed),
    )
    timeout = 700
    ctrl = Bo3MatchController(p1_name="haohmaru", p2_name=canon, intermission_timeout=timeout)

    mode_title = "【三局两胜决战模式 (Best-of-3)】" if mode == "bo3" else "【单局速胜展示模式 (Single Round)】"

    print("======================================================================")
    print(f"       [侍魂2 MoE 专家对战系统 - 实机对局演示] ")
    print(f"  出战主角: 霸王丸 (Haohmaru) vs 对手: {canon.upper()}")
    print(f"  对战模式: {mode_title}")
    print(f"  运行速度: {speed}x 仿真速度 | 视窗模式: {'窗口可见观战' if windowed else '无头后台'}")
    print(f"  对局日志: 正在写入 -> {logger.active_path.name}")
    print("======================================================================")

    # Initialize MoE Router
    experts_dir = PROJECT / "models" / "experts"
    default_zip = PROJECT / "data" / "rl" / "ppo_smoke_20261120_174036" / "best_det.zip"
    if not default_zip.exists():
        default_zip = PROJECT / "data" / "rl" / "r3_init_64d.zip"

    agent = MoEAgent(
        experts_dir=experts_dir,
        default_model_path=default_zip,
        device="cpu",
        lazy_load=True
    )
    agent.set_opponent(canon)

    # Launch MAME session
    sess = BridgeSession(mode="1p", instance=inst, windowed=windowed)
    env = SS2RoundEnv(
        sess=sess,
        instance=inst,
        speed=speed,
        pool=[canon],
        entity_obs=True,
        intent_mode=True,
        n_intents=9,
        y_obs=False,
        hitbox_obs=False,
        match_episodes=(mode == "bo3"),
        skip_scenes=False,  # Essential: preserve exact frame timing on anchor load
        allow_spam=False,
        repeat_penalty=0.0,
        whiff_penalty=0.0,
        time_penalty=0.0
    )

    print("\n[MAME] 游戏已加载，对局正式开始！按 Ctrl+C 可提前退出...\n")

    try:
        obs, info = env.reset()
        agent.reset()
        done = False
        steps = 0
        max_steps = 4000 if mode == "bo3" else 600

        last_p1 = env._prev[0]
        last_p2 = env._prev[1]

        while not done and steps < max_steps:
            p1_bar = env._prev[0]
            p2_bar = env._prev[1]
            p1_hp = info.get("p1_hp", int(p1_bar * 128))
            p2_hp = info.get("p2_hp", int(p2_bar * 164))

            if mode == "bo3":
                act_override = ctrl.update(p1_hp=p1_hp, p2_hp=p2_hp, p1_hp_ratio=p1_bar, p2_hp_ratio=p2_bar)
                if ctrl.round_just_started:
                    print(f"\n" + "=" * 60)
                    print(f"  ★ ★ ★  ROUND {ctrl.current_round} 开打！双方血量重新拉满！当前比分: {ctrl.score[0]}-{ctrl.score[1]}  ★ ★ ★")
                    print("=" * 60 + "\n")
                    agent.set_round(ctrl.current_round)

                if act_override is not None:
                    act_int = act_override
                    act_label = "局间等待 (INTERMISSION)"
                else:
                    act, _ = agent.predict(obs, deterministic=True)
                    act_int = int(act)
                    act_label = ACT_NAMES.get(act_int, f"ACT_{act_int}")
            else:
                # Single round mode
                act, _ = agent.predict(obs, episode_start=(steps == 0), deterministic=True)
                act_int = int(act)
                act_label = ACT_NAMES.get(act_int, f"ACT_{act_int}")

            obs, reward, terminated, truncated, info = env.step(act_int)
            steps += 1

            logger.log_step(
                step=steps,
                act_id=act_int,
                act_name=act_label,
                p1_hp=p1_hp,
                p2_hp=p2_hp,
                round_no=ctrl.current_round if mode == "bo3" else 1,
            )

            # Console live feed on health changes or major intervals
            if abs(p1_bar - last_p1) > 0.01 or abs(p2_bar - last_p2) > 0.01 or steps % 30 == 0 or terminated:
                p1_pct = p1_bar * 100
                p2_pct = p2_bar * 100
                r_prefix = f"R{ctrl.current_round} " if mode == "bo3" else ""
                print(f"帧/步 {steps:03d} | {r_prefix}动作: {act_label:18s} | 霸王丸HP: {p1_hp:02d} ({p1_pct:5.1f}%) | {canon}HP: {p2_hp:02d} ({p2_pct:5.1f}%)")
                last_p1 = p1_bar
                last_p2 = p2_bar

            if mode == "bo3":
                done = ctrl.is_match_done
            else:
                done = terminated or truncated

        # Final match summary
        if mode == "bo3":
            final_winner = ctrl.winner or ("haohmaru" if ctrl.score[0] > ctrl.score[1] else canon)
            won = (final_winner.lower() == "haohmaru")
            score = ctrl.score
        else:
            final_p1_hp = info.get("p1_hp", int(env._prev[0] * 128))
            final_p2_hp = info.get("p2_hp", int(env._prev[1] * 164))
            won = bool((final_p2_hp <= 0 and final_p1_hp > 0) or (env._prev[1] <= 0.05 and env._prev[0] > 0.05))
            final_winner = "haohmaru" if won else canon
            score = (1, 0) if won else (0, 1)

        final_log = logger.finish(
            final_winner=final_winner,
            score=score,
            total_steps=steps,
        )

        print("\n======================================================================")
        if won:
            print(f"                 ★ ★ ★  对局结果: 大获全胜 (VICTORY)!  ★ ★ ★")
            print(f"  胜出主角: 霸王丸 (HAOHMARU) | 最终比分: {score[0]} - {score[1]} | 击溃对手: {canon.upper()}")
        else:
            print(f"                 × × ×  对局结果: 遗憾告负 (DEFEAT)  × × ×")
            print(f"  胜出方: {final_winner.upper()} | 最终比分: {score[0]} - {score[1]}")
        print(f"  耗费总步数: {steps} 步 (约 {steps * 2 / 60:.1f} 秒对局时长)")
        print(f"  完整对局记录已保存至: [ {final_log.resolve()} ]")
        print("======================================================================\n")

        # Post-match victory animation hold (keep window active for at least 10 seconds)
        if windowed:
            hold_sec = 10.0
            print(f"[观战] 决胜达成！保持画面演示胜利特写、收鞘动作与战后结算台词 (等待 {int(hold_sec)} 秒)...", flush=True)
            try:
                env.sess.call("set", "throttle_rate", "1")
            except Exception:
                pass
            start_hold = time.time()
            while time.time() - start_hold < hold_sec:
                try:
                    # Advance MAME emulation smoothly without input so victory pose and quotes play
                    env.sess.call("action", dir_mask=0, btn_mask=0, press_frames=0, step_frames=2, want_pixels=False)
                    time.sleep(2.0 / 60.0)
                except (KeyboardInterrupt, SystemExit):
                    print("\n[观战] 用户提前退出。")
                    break
                except Exception:
                    break
            print("[观战] 演示观战完毕，退出对局。\n")

    except KeyboardInterrupt:
        print("\n[观战] 用户手动中断对局演示 (Ctrl+C)。\n")
    finally:
        env.close()


def _install_human_keybindings(inst: str, human_role: int) -> None:
    """Install default WASD + JKL/UIO MAME keybindings into the human-vs-AI instance cfg dir."""
    import shutil
    cfg_name = "samsho2_human_p1.cfg" if human_role == 1 else "samsho2_human_p2.cfg"
    src_cfg = PROJECT / "data" / "mame" / "cfg" / cfg_name
    if not src_cfg.exists():
        return
    dst_dir = PROJECT / "data" / "mame" / "instance" / inst / "cfg"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_cfg, dst_dir / "samsho2.cfg")


def play_vs_human(target_key: str = "genjuro", human_role: int = 2):
    """Real-time human player vs AI master match mode (zero input conflict).

    human_role=2 (Recommended / True 2P VS):
        Triggers arcade 2P challenger ('Here Comes a New Challenger') into the
        real 2P VS character-select screen. AI locks 1P Haohmaru (JOY1 only via
        bridge); Human freely picks ANY opponent as 2P using WASD + JKL/UIO
        (JOY2 only; 1P keyboard bindings are disabled). Once the match starts,
        WRAM reads P2's chosen character and routes MoEAgent automatically.
    human_role=1 (Free 1P Practice vs Arcade CPU):
        Human exclusively controls 1P Haohmaru (WASD + JKL/UIO) against the
        selected arcade CPU stage; AI sends zero inputs and never interferes.
    """
    if str(target_key).isdigit():
        idx = int(target_key)
        if 1 <= idx <= len(ROSTER):
            target_key = ROSTER[idx - 1]["key"]
    canon = normalize_char_name(target_key)
    inst = "rl_vs_human"

    from train_rl import distribute_states
    from mame_gym import _field_be, P1UID_LOC, P2UID_LOC, E_HEALTH, E_CHAR, entity_features
    from mame_hitbox import SS2_CHAR_ID_MAP

    distribute_states(inst, [canon])
    _install_human_keybindings(inst, human_role)

    print("\n" + "=" * 70)
    if human_role == 2:
        print("   【侍魂2 真·双人 VS 人机对决 (AI 1P 霸王丸 vs 真人 2P 自选角色)】")
        print("  ★ 1P (左侧): AI 霸王丸 (由 MoE 智能体独占控制，1P 键盘已屏蔽防抢键)")
        print("  ★ 2P (右侧): 真人玩家 (进入选人界面后，你可以随便挑选任意角色！)")
        print("-" * 70)
        print("  【2P 真人操控指南 (已自动加载 WASD + JKL/UIO 键位)】:")
        print("    • 选人/移动 : W (上/跳)  S (下/蹲)  A (左)  D (右)")
        print("    • 确认/斩击 : J (确认/轻斩 A)  K (中斩 B)  L (一键重斩 A+B)")
        print("    • 腿脚踢击  : U (轻踢 C)       I (中踢 D)  O (一键重踢 C+D)")
        print("    • 备用键位  : 同时支持 方向键 (↑↓←→) + 小键盘 (1/2/3/4/5/6)")
        print("-" * 70)
        print("  【开局流程】: 启动后自动触发「2P 乱入」进入双人选人画面；")
        print("               AI 会自动锁定 1P 霸王丸，你用 WASD + J 选好角色即刻开战！")
    else:
        print("   【侍魂2 真人 1P 自由练习 (我控 1P 霸王丸 vs 街机原版 CPU)】")
        print(f"  ★ 1P (左侧): 真人玩家 (霸王丸) — AI 已完全休眠，绝不抢键")
        print(f"  ★ 2P (右侧): 街机原版 CPU ({canon.upper()})")
        print("-" * 70)
        print("  【1P 真人操控指南 (已自动加载 WASD + JKL/UIO 键位)】:")
        print("    • 方向键 : W (上/跳)  S (下/蹲)  A (左)  D (右)")
        print("    • 刀剑斩 : J (轻斩 A)  K (中斩 B)  L (一键重斩 A+B)")
        print("    • 腿脚踢 : U (轻踢 C)  I (中踢 D)  O (一键重踢 C+D)")
    print("  【退出对局】: 随时在终端窗口按 Ctrl+C 即可安全退出")
    print("=" * 70 + "\n")

    sess = BridgeSession(mode="1p", instance=inst, windowed=True)
    env = SS2RoundEnv(
        sess=sess,
        instance=inst,
        speed=1,
        pool=[canon],
        entity_obs=True,
        intent_mode=True,
        n_intents=9,
        y_obs=False,
        hitbox_obs=False,
        match_episodes=True,
        skip_scenes=False,
        allow_spam=False,
        ai_role=0,
        want_pixels=False,
    )

    try:
        obs, info = env.reset()
        # Let MAME's native 59.19 Hz hardware throttle pace the game smoothly (no Python sleep!)
        env.sess.call("set", "throttle", "1")
        env.sess.call("set", "throttle_rate", "1")

        if human_role == 1:
            # Pure human 1P practice: AI sends NO inputs at all, MAME runs at native 60 FPS
            print("[自由练习] 舞台已就绪！1P 完全交给你操控，AI 不会发送任何按键...\n")
            while True:
                env.sess.call("action", dir_mask=0, btn_mask=0, press_frames=0, step_frames=4, want_pixels=False)

        # human_role == 2: True 2P VS Challenger mode!
        experts_dir = PROJECT / "models" / "experts"
        agent = MoEAgent(experts_dir=experts_dir, device="cpu", lazy_load=True)

        print("[2P 乱入] 正在触发街机「HERE COMES A NEW CHALLENGER」进入双人选人界面...")
        env.sess.call("set", "ai_role", "0")
        env.sess.call("set", "field", "DSW:64:1")
        # Trigger 2P START to enter 2P VS Character Select
        env.sess.call("press", role=2, mask=0x04, press_frames=12, wait_frames=20)

        # Wait through challenger banner & character select while human picks any 2P character
        print("[选人中] 请在 MAME 窗口用 W/A/S/D 选择你想玩的 2P 角色，按 J 确认！\n")
        p1_confirmed = False
        wait_ticks = 0
        chosen_p2_key = canon
        p1_uid = p2_uid = 0

        while True:
            v, _ = env.sess.call("action", dir_mask=0, btn_mask=0, press_frames=0, step_frames=2, want_pixels=False)
            wait_ticks += 1

            # After ~90 ticks (~3 seconds into character select), tap P1 A once to lock Haohmaru
            if not p1_confirmed and wait_ticks == 95:
                env.sess.call("press", role=0, mask=0x10, press_frames=6, wait_frames=4)
                p1_confirmed = True
                print("[选人中] AI 已锁定 1P 霸王丸，等待你确认 2P 角色并进入战场...")

            # Detect live 2P VS combat start (after banner clears, wait_ticks > 120)
            if wait_ticks > 120:
                u1 = _field_be(v, P1UID_LOC, 4)
                u2 = _field_be(v, P2UID_LOC, 4)
                if 0x100000 <= u1 <= 0x10F000 and 0x100000 <= u2 <= 0x10F000 and u1 != u2:
                    h1 = _field_be(v, u1 + E_HEALTH, 1)
                    h2 = _field_be(v, u2 + E_HEALTH, 1)
                    if h1 >= 100 and h2 >= 100:
                        p1_uid, p2_uid = u1, u2
                        c2_id = _field_be(v, u2 + E_CHAR, 1)
                        chosen_p2_key = SS2_CHAR_ID_MAP.get(c2_id, canon)
                        break

        print(f"\n[开战!] 检测到你选择了 2P 角色: {chosen_p2_key.upper()}！AI 霸王丸正在加载对应专家策略...")
        agent.set_opponent(chosen_p2_key)
        agent.reset()
        env._uids = (p1_uid, p2_uid)
        env._state_name = chosen_p2_key

        ctrl = Bo3MatchController(p1_name="haohmaru", p2_name=chosen_p2_key, intermission_timeout=700)
        steps = 0
        while not ctrl.is_match_done and steps < 6000:
            p1_bar = env._prev[0]
            p2_bar = env._prev[1]
            p1_hp = info.get("p1_hp", int(p1_bar * 128))
            p2_hp = info.get("p2_hp", int(p2_bar * 128))

            act_override = ctrl.update(p1_hp=p1_hp, p2_hp=p2_hp, p1_hp_ratio=p1_bar, p2_hp_ratio=p2_bar)
            if ctrl.round_just_started:
                agent.set_round(ctrl.current_round)

            if act_override is not None:
                act_int = act_override
            else:
                act, _ = agent.predict(obs, deterministic=True)
                act_int = int(act)

            obs, reward, terminated, truncated, info = env.step(act_int)
            steps += 1

            if steps % 60 == 0:
                print(f"帧/步 {steps:03d} | 比分: {ctrl.score[0]}-{ctrl.score[1]} | 1P(AI 霸王丸)HP: {p1_hp:03d} | 2P(真人 {chosen_p2_key})HP: {p2_hp:03d}")

        final_winner = ctrl.winner or ("haohmaru" if ctrl.score[0] > ctrl.score[1] else chosen_p2_key)
        winner_label = "AI 霸王丸" if final_winner == "haohmaru" else f"真人玩家 ({chosen_p2_key.upper()})"
        print("\n======================================================================")
        print(f"  ★ 双人 VS 决战结束！胜出方: {winner_label} | 最终比分: {ctrl.score[0]}-{ctrl.score[1]}")
        print("  正在展示战后收刀、胜利特写与结算画面 (停留 15 秒，按 Ctrl+C 可提前退出)...")
        print("======================================================================\n")

        hold_start = time.time()
        while time.time() - hold_start < 15.0:
            try:
                env.sess.call("action", dir_mask=0, btn_mask=0, press_frames=0, step_frames=4, want_pixels=False)
            except Exception:
                break

    except KeyboardInterrupt:
        print("\n[对决] 人机对抗提前结束。\n")
    finally:
        env.close()


def interactive_menu():
    manifest = load_manifest()
    print("\n" + "=" * 68)
    print("        【侍魂2 MoE 专家系统 - 对战与对战演示程序】")
    print("=" * 68)
    print(" 请选择你想对战的对手：")
    for idx, c in enumerate(ROSTER, 1):
        m_entry = manifest.get(c["key"], {})
        if m_entry.get("status") == "VERIFIED":
            status_str = f"★ 已击破 (Bo3比分 {m_entry.get('score')} | 3/3实机复核通过)"
        elif m_entry.get("status") == "NEEDS_REVIEW":
            status_str = "⚠ 待人工复核 (已记录诊断日志)"
        else:
            status_str = "○ 待训练 (当前加载基准回退模型)"
        print(f"   [{idx:2d}] {c['name']:24s} -> {status_str}")
    print("=" * 68)

    while True:
        try:
            choice_str = input(f" 请输入对手序号 (1-{len(ROSTER)}) [默认 1: 地震]: ").strip()
            if not choice_str:
                choice = 1
                break
            choice = int(choice_str)
            if 1 <= choice <= len(ROSTER):
                break
            print(f" 输入无效，请输入 1-{len(ROSTER)} 之间的数字。")
        except (ValueError, EOFError):
            choice = 1
            break

    target_char = ROSTER[choice - 1]["key"]

    print("\n 请选择对决体验方式：")
    print("   [1] 电脑观战演示 (AI 1P 霸王丸 vs 街机 CPU 自动化观战 - 默认)")
    print("   [2] 实机人机对决 (AI 控 1P 霸王丸 vs 我控 2P 任意自选角色 - 推荐)")
    print("   [3] 真人自由练习 (我控 1P 霸王丸 vs 街机原版 CPU，AI 不干预)")
    print("   [4] 自动录制 MP4 视频 (生成 60FPS 高清对局录像文件)")
    exp_str = input(" 请输入选项 (1-4) [默认 1: 观战演示]: ").strip()

    if exp_str == "2":
        play_vs_human(target_key=target_char, human_role=2)
        return
    elif exp_str == "3":
        play_vs_human(target_key=target_char, human_role=1)
        return

    print("\n 请选择对局模式：")
    print("   [1] 完整三局两胜 (Best-of-3，打满整场直到 2:0 或 2:1，连打多局 - 推荐)")
    print("   [2] 单局速胜展示 (Single Round，266 步极限 KO 翻盘瞬间)")
    mode_str = input(" 请输入对局模式 (1-2) [默认 1: 三局两胜]: ").strip()
    mode = "single" if mode_str == "2" else "bo3"

    print("\n 请选择对局演示速度：")
    print("   [1] 1x  (正常街机 60FPS 观战体验 - 推荐)")
    print("   [2] 2x  (快速双倍速演示)")
    print("   [3] 4x  (极速跳过快速查看结果)")
    speed_str = input(" 请输入速度选项 (1-3) [默认 1: 正常速度]: ").strip()
    speed_map = {"1": 1, "2": 2, "3": 4}
    speed = speed_map.get(speed_str, 1)

    if exp_str == "4":
        tools_dir = str(PROJECT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from record_match_mp4 import record_opponent_match
        record_opponent_match(target_key=target_char, mode=mode, speed=speed)
    else:
        play_demo(target_key=target_char, speed=speed, windowed=True, mode=mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samurai Shodown II MoE Demo Player")
    parser.add_argument("--target", type=str, default=None, help="Opponent canonical name or index 1-16")
    parser.add_argument("--speed", type=int, default=1, help="Simulation speed throttle (1 for normal 60fps, 2 or 4)")
    parser.add_argument("--mode", type=str, default="bo3", choices=["bo3", "single"], help="Match mode: bo3 or single")
    parser.add_argument("--headless", action="store_true", help="Run without visible window")
    parser.add_argument("--human", action="store_true", help="Launch Human (1P) vs AI (2P) real-time battle mode")
    parser.add_argument("--human-p2", action="store_true", help="Launch Human (2P) vs AI (1P) reversed mode")
    parser.add_argument("--record", action="store_true", help="Record match to MP4 video file")

    args = parser.parse_args()

    if args.human:
        target = args.target or "genjuro"
        play_vs_human(target_key=target, human_role=2)
    elif args.human_p2:
        target = args.target or "genjuro"
        play_vs_human(target_key=target, human_role=2)
    elif args.record:
        tools_dir = str(PROJECT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from record_match_mp4 import record_opponent_match
        target = args.target or "charlotte"
        record_opponent_match(target_key=target, mode=args.mode, speed=args.speed)
    elif args.target:
        play_demo(
            target_key=args.target,
            speed=args.speed,
            windowed=not args.headless,
            mode=args.mode,
        )
    else:
        interactive_menu()
