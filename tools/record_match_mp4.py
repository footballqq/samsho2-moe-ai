"""
record_match_mp4.py - Automated MAME video capture and MP4 rendering pipeline.
Executes an MoE match against an opponent, captures 60 FPS gameplay, and converts
it to a compressed, high-definition MP4 video file using MAME -aviwrite and FFmpeg.
"""
from __future__ import annotations

import os
import sys
import time
import json
import shutil
import argparse
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from mame_client import BridgeSession
from mame_gym import SS2RoundEnv
from mame_moe import MoEAgent
from mame_hitbox import normalize_char_name
from bo3_controller import Bo3MatchController
from demo_logger import DemoLogger
from moe_roster import ROSTER, ACT_NAMES


def record_opponent_match(
    target_key: str = "charlotte",
    mode: str = "bo3",
    speed: int = 1,
    output_dir: Path | None = None,
    require_win: bool = True,
    max_retries: int = 3,
) -> Path | None:
    if str(target_key).isdigit():
        idx = int(target_key)
        if 1 <= idx <= len(ROSTER):
            target_key = ROSTER[idx - 1]["key"]
    canon = normalize_char_name(target_key)
    inst = "rl_record_demo"

    # Distribute states for this instance
    from train_rl import distribute_states
    distribute_states(inst, [canon])

    v_dir = output_dir or (PROJECT / "videos")
    v_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        temp_avi = v_dir / f"temp_{canon}_{timestamp}.avi"

        log_dir = PROJECT / "logs" / "demos"
        logger = DemoLogger(
            log_dir=log_dir,
            p1_name="haohmaru",
            p2_name=canon,
            mode=mode,
            speed=float(speed),
        )
        timeout = 700  # Generous intermission timeout across all characters for complete Bo3 transitions
        ctrl = Bo3MatchController(p1_name="haohmaru", p2_name=canon, intermission_timeout=timeout)

        print("======================================================================")
        print(f"       [侍魂2 MoE 自动化视频录制流水线 (MAME + FFmpeg)] ")
        print(f"  出战主角: 霸王丸 (Haohmaru) vs 对手: {canon.upper()} (第 {attempt}/{max_retries} 次尝试)")
        print(f"  对战模式: {'三局两胜 (Bo3)' if mode == 'bo3' else '单局速胜 (Single)'}")
        print("======================================================================")

        experts_dir = PROJECT / "models" / "experts"
        default_zip = PROJECT / "data" / "rl" / "ppo_smoke_20261120_174036" / "best_det.zip"
        if not default_zip.exists():
            default_zip = PROJECT / "data" / "rl" / "r3_init_64d.zip"

        agent = MoEAgent(
            experts_dir=experts_dir,
            default_model_path=default_zip,
            device="cpu",
            lazy_load=True,
        )
        agent.set_opponent(canon)

        # Launch MAME with -aviwrite and -video gdi for reliable headless/windowed capture
        extra_record_args = ["-video", "gdi", "-aviwrite", str(temp_avi)]
        sess = BridgeSession(mode="1p", instance=inst, windowed=True, extra_args=extra_record_args)
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
            skip_scenes=False,
            allow_spam=False,
            repeat_penalty=0.0,
            whiff_penalty=0.0,
            time_penalty=0.0,
        )

        print("\n[录制中] MAME 仿真与视频流捕获已启动，执行实机斩杀...\n")

        try:
            obs, info = env.reset()
            agent.reset()
            done = False
            steps = 0
            max_steps = 4000 if mode == "bo3" else 600
            recorded_events = []

            while not done and steps < max_steps:
                p1_bar = env._prev[0]
                p2_bar = env._prev[1]
                p1_hp = info.get("p1_hp", int(p1_bar * 128))
                p2_hp = info.get("p2_hp", int(p2_bar * 164))

                if mode == "bo3":
                    act_override = ctrl.update(p1_hp=p1_hp, p2_hp=p2_hp, p1_hp_ratio=p1_bar, p2_hp_ratio=p2_bar, rounds=info.get("rounds"))
                    if ctrl.round_just_started:
                        agent.set_round(ctrl.current_round)

                    if act_override is not None:
                        act_int = act_override
                        act_label = "局间等待"
                    else:
                        act, _ = agent.predict(obs, deterministic=True)
                        act_int = int(act)
                        act_label = ACT_NAMES.get(act_int, f"ACT_{act_int}")
                else:
                    act, _ = agent.predict(obs, episode_start=(steps == 0), deterministic=True)
                    act_int = int(act)
                    act_label = ACT_NAMES.get(act_int, f"ACT_{act_int}")

                obs, reward, terminated, truncated, info = env.step(act_int)
                steps += 1

                recorded_events.append({
                    "step": steps,
                    "act_id": act_int,
                    "act_name": act_label,
                    "p1_hp": p1_hp,
                    "p2_hp": p2_hp,
                    "round": ctrl.current_round if mode == "bo3" else 1,
                })

                logger.log_step(
                    step=steps,
                    act_id=act_int,
                    act_name=act_label,
                    p1_hp=p1_hp,
                    p2_hp=p2_hp,
                    round_no=ctrl.current_round if mode == "bo3" else 1,
                )

                if steps % 40 == 0 or terminated:
                    r_prefix = f"R{ctrl.current_round} " if mode == "bo3" else ""
                    print(f"   [录像进度] {r_prefix}步数: {steps:03d} | 动作: {act_label:18s} | 霸王丸HP: {p1_hp:02d} | {canon}HP: {p2_hp:02d}")

                if mode == "bo3":
                    done = ctrl.is_match_done
                else:
                    done = terminated or truncated

            # Post-match celebration & settlement screens (18 seconds full capture)
            print("\n[录像捕获] 决胜达成！继续录制战后收刀、胜利特写、台词及最终分数结算画面 (18秒)...")
            try:
                env.sess.call("set", "throttle_rate", "1")
            except Exception:
                pass
            start_hold = time.time()
            while time.time() - start_hold < 18.0:
                try:
                    env.sess.call("action", dir_mask=0, btn_mask=0, press_frames=0, step_frames=2, want_pixels=False)
                    time.sleep(2.0 / 60.0)
                except Exception:
                    break

            if mode == "bo3":
                # Strict: Must have reached at least 2 round wins to be declared VICTORY
                won = bool(ctrl.is_match_done and ctrl.score[0] >= 2 and (ctrl.winner or "").lower() == "haohmaru")
                final_winner = "haohmaru" if won else (ctrl.winner or canon)
                score = ctrl.score
            else:
                final_p1_hp = info.get("p1_hp", int(env._prev[0] * 128))
                final_p2_hp = info.get("p2_hp", int(env._prev[1] * 164))
                won = bool((final_p2_hp <= 0 and final_p1_hp > 0) or (env._prev[1] <= 0.05 and env._prev[0] > 0.05))
                final_winner = "haohmaru" if won else canon
                score = (1, 0) if won else (0, 1)

            logger.finish(final_winner=final_winner, score=score, total_steps=steps)

        finally:
            env.close()

        if require_win and not won:
            print(f"⚠️ 对局未斩获胜利 (比分: {score})，清除临时视频并进行第 {attempt+1} 次重试录制...")
            if temp_avi.exists():
                temp_avi.unlink()
            continue

        outcome_tag = "VICTORY" if won else "DEFEAT"
        final_mp4 = v_dir / f"{timestamp}_haohmaru_vs_{canon}_{outcome_tag}.mp4"

        # Step 2: Convert AVI to high-definition MP4 using FFmpeg
        if not temp_avi.exists() or temp_avi.stat().st_size == 0:
            print(f"❌ 录制失败: 未找到临时视频文件 {temp_avi}")
            return None

        print(f"\n[FFmpeg 转码] 正在将原始流 ({temp_avi.stat().st_size / (1024*1024):.1f} MB) 编码为 MP4 高清视频...")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(temp_avi),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "128k",
            str(final_mp4),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Clean up large AVI
        if temp_avi.exists():
            temp_avi.unlink()

        if final_mp4.exists() and final_mp4.stat().st_size > 0:
            size_mb = final_mp4.stat().st_size / (1024 * 1024)
            print("======================================================================")
            print(f"  ★ ★ ★  MP4 对局录像生成完毕！  ★ ★ ★")
            print(f"  录像视频: {final_mp4.resolve()} ({size_mb:.2f} MB)")

            # Generate Synchronized Commentary JSON and Subtitles (Bilingual CN/EN)
            from commentary_engine import generate_and_save_commentary_files
            json_path, srt_zh_path, srt_en_path = generate_and_save_commentary_files(
                match_id=f"{timestamp}_haohmaru_vs_{canon}",
                video_path=final_mp4,
                p1_key="haohmaru",
                p2_key=canon,
                events=recorded_events,
                total_steps=steps,
                hold_duration_sec=18.0,
                winner=final_winner,
                score=score,
            )
            print(f"  双语解说: {json_path.resolve()} (结构化JSON)")
            print(f"  中文字幕: {srt_zh_path.resolve()} (标准SRT字幕)")
            print(f"  英文字幕: {srt_en_path.resolve()} (标准SRT字幕)")
            print("======================================================================\n")
            return final_mp4
        else:
            print(f"❌ 转码失败: {res.stderr}")
            return None

    return None


def record_all_roster(mode: str = "bo3", speed: int = 1, skip_existing: bool = True):
    print("======================================================================")
    print(f"       【侍魂2 MoE 全员 16 位对手比赛录像自动化批量渲染】")
    print(f"  对战模式: {mode} (三局两胜Bo3) | 渲染加速: {speed}x | 跳过已有: {skip_existing}")
    print("======================================================================\n")
    results = []
    v_dir = PROJECT / "videos"
    v_dir.mkdir(parents=True, exist_ok=True)

    for idx, c in enumerate(ROSTER, 1):
        key = c["key"]
        if skip_existing:
            # Check if there is already a matching valid Bo3 video + commentary.json
            existing_mp4s = sorted(v_dir.glob(f"*_haohmaru_vs_{key}_*VICTORY.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            valid_existing = None
            for emp4 in existing_mp4s:
                j_path = v_dir / f"{emp4.stem}_commentary.json"
                if j_path.exists() and emp4.stat().st_size > 100000:
                    try:
                        with open(j_path, "r", encoding="utf-8") as jf:
                            jd = json.load(jf)
                        if mode == "bo3":
                            if jd.get("mode") == "bo3" and jd.get("final_score") in ("2-0", "2-1") and jd.get("hold_duration_sec", 0) >= 15.0:
                                valid_existing = emp4
                                break
                        else:
                            valid_existing = emp4
                            break
                    except Exception:
                        pass
            if valid_existing:
                print(f"⏩ [{idx:2d}/{len(ROSTER)}] {c['name']} 已存在完整Bo3录像与双语解说: {valid_existing.name}，跳过。")
                results.append((key, valid_existing))
                continue

        print(f"\n>>> 正在录制 [{idx:2d}/{len(ROSTER)}] {c['name']} 对决录像...")
        p = record_opponent_match(target_key=key, mode=mode, speed=speed, require_win=True)
        results.append((key, p))

    print("\n======================================================================")
    print("                  ★ 全员 16 位对手录像批量录制完成 ★")
    print("======================================================================")
    for key, p in results:
        status_str = f"已就绪 -> {p.name}" if p else "失败"
        print(f"   {key:14s} : {status_str}")
    print("======================================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samurai Shodown II MP4 Match Recorder")
    parser.add_argument("--target", type=str, default="charlotte", help="Opponent canonical name or index 1-16, or 'all'")
    parser.add_argument("--mode", type=str, default="bo3", choices=["bo3", "single"], help="Match mode: bo3 (default) or single")
    parser.add_argument("--speed", type=int, default=1, help="Simulation speed throttle (1 for normal 60fps, 2 or 4)")
    parser.add_argument("--all", action="store_true", help="Record all 16 opponents sequentially")
    parser.add_argument("--skip-existing", action="store_true", default=False, help="Skip opponents that already have mp4 and commentary")
    parser.add_argument("--force", action="store_true", help="Force overwrite even if existing")

    args = parser.parse_args()

    skip = not args.force if not args.force else False

    if args.all or args.target.lower() == "all":
        record_all_roster(mode=args.mode, speed=args.speed, skip_existing=skip)
    else:
        record_opponent_match(target_key=args.target, mode=args.mode, speed=args.speed)
