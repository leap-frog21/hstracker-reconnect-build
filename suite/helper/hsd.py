#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""炉石酒馆战棋“拔线”助手（macOS）

原理：
  1. 监听 /Applications/Hearthstone/Logs/Hearthstone_*/Power.log
  2. 检测酒馆战棋战斗阶段开始（STEP / NEXT_STEP = MAIN_COMBAT）
  3. 通过 Clash Verge 的本地 API 关闭炉石到游戏服务器（TCP 1119）的连接
  4. 在 cut_seconds 内持续关闭新连接，阻止客户端立刻重连
  5. 停止关闭后客户端自动重连，直接拿到战斗结算后的状态

默认 dry-run，只打印不动作；加 --live 才真正断线。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

HS_ROOT = Path("/Applications/Hearthstone")
LOG_CONFIGS = [
    HS_ROOT / "log.config",
    Path.home() / "Library/Preferences/Blizzard/Hearthstone/log.config",
]
DEFAULT_LOG_ROOT = HS_ROOT / "Logs"
CLASH_SOCK = Path(f"/var/run/clash-verge-service/users/{os.getuid()}/verge-mihomo.sock")
STATE_DIR = Path.home() / "Library/Logs/HSDisconnect"
CURL = "/usr/bin/curl"
PGREP = "/usr/bin/pgrep"

COMBAT_RE = re.compile(r"tag=(?:STEP|NEXT_STEP) value=MAIN_COMBAT\b")
SERVER_RE = re.compile(r"address=\s*(\d{1,3}(?:\.\d{1,3}){3}):1119")

DEFAULTS = {
    "cut_seconds": 2.0,
    "delay_ms": 150,
    "cooldown_seconds": 6.0,
    "only_battlegrounds": True,
    "log_root": str(DEFAULT_LOG_ROOT),
    "verbose": False,
}

log = logging.getLogger("hsd")


def setup_logging(verbose: bool = False) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = RotatingFileHandler(
        STATE_DIR / "hsd.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def load_config(path: str | None) -> dict:
    cfg = dict(DEFAULTS)
    candidates = [Path(path)] if path else [Path(__file__).with_name("config.json")]
    for p in candidates:
        if p and p.exists():
            try:
                cfg.update(json.loads(p.read_text(encoding="utf-8")))
            except Exception as e:
                log.warning("读取配置 %s 失败：%s", p, e)
    return cfg


# ---------------------------------------------------------------- Clash API

def clash_request(method: str, path: str, timeout: float = 2.0) -> str:
    if not CLASH_SOCK.exists():
        raise RuntimeError(f"Clash 控制 socket 不存在：{CLASH_SOCK}（Clash Verge 未运行？）")
    cmd = [
        CURL, "-sS", "--max-time", f"{timeout:.1f}",
        "--unix-socket", str(CLASH_SOCK),
        "-X", method, f"http://localhost{path}",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"curl 退出码 {r.returncode}")
    return r.stdout


def clash_connections() -> list[dict]:
    data = json.loads(clash_request("GET", "/connections") or "{}")
    return data.get("connections") or []


def tun_enabled() -> bool:
    data = json.loads(clash_request("GET", "/configs") or "{}")
    return bool((data.get("tun") or {}).get("enable"))


def hs_process_running() -> bool:
    r = subprocess.run(
        [PGREP, "-f", "/Hearthstone.app/Contents/MacOS/Hearthstone"],
        capture_output=True,
    )
    return r.returncode == 0


def tail_lines(path: Path, n: int) -> list[str]:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 128 * 1024))
            data = f.read()
        return data.decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []


def last_server_ip(power_log: Path | None) -> str | None:
    if not power_log:
        return None
    net_log = power_log.parent / "GameNetLogger.log"
    if not net_log.exists():
        return None
    for line in reversed(tail_lines(net_log, 300)):
        m = SERVER_RE.search(line)
        if m:
            return m.group(1)
    return None


def hs_connections(power_log: Path | None = None) -> list[dict]:
    """只返回“纯 IP”的游戏服连接，排除战网/BGS 的 1119 连接。

    战网登录连接（如 cn.actual.battlenet.com.cn:1119）host 非空，
    关闭它会导致 ERROR_SDK_SOCKET_CLOSED，重连后无法登录。
    游戏服连接是纯 IP：host 为空、destinationIP 非空。
    """
    server_ip = last_server_ip(power_log)
    candidates = []
    for c in clash_connections():
        m = c.get("metadata") or {}
        if m.get("network") != "tcp":
            continue
        try:
            dport = int(m.get("destinationPort"))
        except (TypeError, ValueError):
            continue
        if dport != 1119:
            continue
        proc = m.get("processPath") or ""
        if not (proc.endswith("/Hearthstone") or "Hearthstone.app/Contents/MacOS/Hearthstone" in proc):
            continue
        host = (m.get("host") or "").strip()
        ip = (m.get("destinationIP") or "").strip()
        if host or not ip:
            continue
        if server_ip:
            if ip == server_ip:
                return [c]
            continue
        candidates.append(c)
    if server_ip:
        return []
    if len(candidates) == 1:
        return candidates
    return []


def cut_once(wait_seconds: float, power_log: Path | None = None) -> int:
    """关闭当前炉石的 1119 连接一次，然后等待 wait_seconds 再返回。"""
    try:
        conns = hs_connections(power_log)
    except Exception as e:
        log.warning("查询连接失败：%s", e)
        return 0
    closed = 0
    for c in conns:
        try:
            clash_request("DELETE", f"/connections/{c['id']}")
            closed += 1
        except Exception as e:
            log.warning("关闭连接失败：%s", e)
    if closed and wait_seconds > 0:
        time.sleep(wait_seconds)
    return closed


# ---------------------------------------------------------------- 日志跟踪

def newest_power_log(root: str | Path) -> Path | None:
    root = Path(root)
    if not root.exists():
        return None
    dirs = [d for d in root.glob("Hearthstone_*") if d.is_dir()]
    if not dirs:
        return None
    d = max(dirs, key=lambda p: p.stat().st_mtime)
    p = d / "Power.log"
    return p if p.exists() else None


class Detector:
    """从 Power.log 行中维护对局/模式状态，并产出 combat 事件。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.in_game = False
        self.bg = False
        self.last_cut = 0.0
        self.combats = 0

    def feed(self, line: str) -> str | None:
        if "CREATE_GAME" in line:
            self.in_game = True
            self.bg = False
            return None
        if ("GT_BATTLEGROUNDS" in line or "Bacon" in line
                or "BATTLEGROUNDS" in line or "BG_" in line):
            self.bg = True
        if COMBAT_RE.search(line):
            self.combats += 1
            return "combat"
        return None


def handle_combat(det: Detector, cfg: dict, live: bool, power_log: Path) -> None:
    if not det.in_game:
        log.info("检测到 MAIN_COMBAT，但当前不在对局中，跳过")
        return
    if cfg.get("only_battlegrounds", True) and not det.bg:
        log.info("检测到 MAIN_COMBAT，但未识别为酒馆战棋，跳过（dry-run 可看日志校准）")
        return
    now = time.monotonic()
    if now - det.last_cut < float(cfg.get("cooldown_seconds", 6)):
        log.info("冷却中，跳过本次 MAIN_COMBAT")
        return
    det.last_cut = now

    if not live:
        log.info("MAIN_COMBAT（bg=%s）→ DRY-RUN：本应断线 %.1fs", det.bg, cfg["cut_seconds"])
        return

    if not hs_process_running():
        log.warning("炉石进程不在，跳过")
        return
    try:
        if not tun_enabled():
            log.error("Clash TUN 未启用，无法断线；请在 Clash Verge 打开 TUN 模式")
            return
    except Exception as e:
        log.error("读取 Clash 状态失败：%s", e)
        return

    delay = float(cfg.get("delay_ms", 150)) / 1000.0
    if delay > 0:
        time.sleep(delay)
    try:
        n = cut_once(float(cfg["cut_seconds"]), power_log)
    except Exception as e:
        log.error("断线失败：%s", e)
        return
    if n:
        log.info("MAIN_COMBAT（bg=%s）→ 已关闭 %d 条连接，断线 %.1fs", det.bg, n, cfg["cut_seconds"])
    else:
        log.warning("MAIN_COMBAT（bg=%s）→ 没有找到可关闭的 1119 连接", det.bg)


def watch(cfg: dict, live: bool) -> None:
    log_root = Path(cfg.get("log_root") or DEFAULT_LOG_ROOT)
    log.info("开始监听 %s（%s）", log_root, "LIVE" if live else "DRY-RUN")
    if not any(p.exists() and "[Power]" in p.read_text(errors="replace") for p in LOG_CONFIGS):
        log.warning("Power 日志可能未启用：以下文件都不含 [Power]：%s", LOG_CONFIGS)

    current: Path | None = None
    offset = 0
    buf = b""
    det = Detector(cfg)

    while True:
        path = newest_power_log(log_root)
        if path != current:
            current = path
            buf = b""
            det = Detector(cfg)
            if path:
                size = path.stat().st_size
                start = max(0, size - 2_000_000)
                with path.open("rb") as f:
                    f.seek(start)
                    data = f.read()
                    offset = f.tell()
                for raw in data.split(b"\n")[:-1]:
                    det.feed(raw.decode("utf-8", "replace"))
                log.info("接入日志 %s（%d 字节，已预读状态）", path, size)

        if path:
            try:
                size = path.stat().st_size
                if size < offset:
                    offset = 0
                    buf = b""
                    det = Detector(cfg)
                    log.info("日志被截断，重新读取")
                with path.open("rb") as f:
                    f.seek(offset)
                    chunk = f.read()
                    offset = f.tell()
                if chunk:
                    buf += chunk
                    parts = buf.split(b"\n")
                    buf = parts.pop()
                    for raw in parts:
                        line = raw.decode("utf-8", "replace")
                        if cfg.get("verbose") and ("STEP" in line or "MAIN_COMBAT" in line):
                            log.debug("%s", line.strip()[:220])
                        ev = det.feed(line)
                        if ev == "combat":
                            handle_combat(det, cfg, live, path)
            except OSError as e:
                log.debug("读日志失败：%s", e)
        time.sleep(0.25)


# ---------------------------------------------------------------- 子命令

def cmd_status(cfg: dict) -> None:
    print(f"Clash socket : {CLASH_SOCK}  {'存在' if CLASH_SOCK.exists() else '不存在'}")
    if CLASH_SOCK.exists():
        try:
            print(f"TUN 模式     : {tun_enabled()}")
        except Exception as e:
            print(f"TUN 模式     : 读取失败 {e}")
    print(f"炉石进程     : {'运行中' if hs_process_running() else '未运行'}")
    path = newest_power_log(cfg.get("log_root") or DEFAULT_LOG_ROOT)
    print(f"最新 Power.log: {path}")
    if path:
        print(f"日志大小     : {path.stat().st_size} 字节")
        print(f"服务器 IP    : {last_server_ip(path)}")
    for p in LOG_CONFIGS:
        print(f"log.config   : {p}  {'存在' if p.exists() else '缺失'}")
    if CLASH_SOCK.exists():
        try:
            conns = hs_connections(path)
            print(f"炉石 1119 连接: {len(conns)}")
            for c in conns:
                m = c.get("metadata") or {}
                print(f"  {c.get('id')}  {m.get('destinationIP')}:{m.get('destinationPort')}")
        except Exception as e:
            print(f"连接列表     : 读取失败 {e}")


def cmd_cut(cfg: dict, seconds: float) -> None:
    if not tun_enabled():
        print("Clash TUN 未启用，无法断线")
        return
    path = newest_power_log(cfg.get("log_root") or DEFAULT_LOG_ROOT)
    n = cut_once(seconds, path)
    if n:
        if seconds > 0:
            print(f"已关闭 {n} 条连接（等待 {seconds:.1f}s）")
        else:
            print(f"已关闭 {n} 条连接")
    else:
        print("未找到唯一的游戏服连接，已取消（不会碰战网连接）")


def cmd_parse(path: str) -> None:
    p = Path(path)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"文件: {p}")
    print(f"总行数: {len(lines)}")
    print(f"CREATE_GAME: {sum(1 for l in lines if 'CREATE_GAME' in l)}")
    print(f"MAIN_COMBAT: {sum(1 for l in lines if 'MAIN_COMBAT' in l)}")
    print(f"BG 标记: {sum(1 for l in lines if 'GT_BATTLEGROUNDS' in l or 'Bacon' in l or 'BG_' in l)}")
    for kw in ("GT_BATTLEGROUNDS", "GAME_TYPE", "MAIN_COMBAT"):
        hits = [l for l in lines if kw in l]
        if hits:
            print(f"\n[{kw}] 前 3 条:")
            for l in hits[:3]:
                print(" ", l[:220])
    step = [l for l in lines if "tag=STEP" in l]
    if step:
        print(f"\nSTEP 行共 {len(step)} 条，最后 5 条:")
        for l in step[-5:]:
            print(" ", l[:220])


def main() -> None:
    ap = argparse.ArgumentParser(description="炉石酒馆战棋拔线助手（macOS / Clash Verge）")
    ap.add_argument("--config", help="配置文件路径")
    ap.add_argument("--log-root", help="炉石 Logs 目录（默认 /Applications/Hearthstone/Logs）")
    ap.add_argument("--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("watch", help="监听 Power.log（默认 dry-run）")
    w.add_argument("--live", action="store_true", help="真正执行断线")
    w.add_argument("--no-bg-gate", action="store_true", help="不限制酒馆战棋")

    sub.add_parser("status", help="自检")
    c = sub.add_parser("cut", help="手动断线一次")
    c.add_argument("--seconds", type=float, default=2.0)
    pa = sub.add_parser("parse", help="解析一份 Power.log，用于校准")
    pa.add_argument("path")

    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.log_root:
        cfg["log_root"] = args.log_root
    if args.verbose:
        cfg["verbose"] = True
    setup_logging(cfg.get("verbose", False))

    if args.cmd == "watch":
        if args.no_bg_gate:
            cfg["only_battlegrounds"] = False
        try:
            watch(cfg, args.live)
        except KeyboardInterrupt:
            log.info("退出")
    elif args.cmd == "status":
        cmd_status(cfg)
    elif args.cmd == "cut":
        cmd_cut(cfg, args.seconds)
    elif args.cmd == "parse":
        cmd_parse(args.path)


if __name__ == "__main__":
    main()
