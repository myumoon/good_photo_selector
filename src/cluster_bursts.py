#!/usr/bin/env python3
"""
Cluster NEF files into "bursts" (same-scene groups) by capture time.

同一シーン(連写)からベスト1枚を選ぶには、シーン全体を一度に見比べる必要がある。
本スクリプトは撮影時刻(DateTimeOriginal + SubSecTimeOriginal)の間隔で連写を
グルーピングし、1連写=1バッチとして出力する。4枚固定バッチだと連写が分断され、
「シーン内ベスト1枚」を選べないため、この単位で評価する。

使い方:
    python3 src/cluster_bursts.py <DIR>            # <DIR>/*.NEF をクラスタリング
    python3 src/cluster_bursts.py a.NEF b.NEF ...  # 指定ファイルをクラスタリング

出力（1行=1連写、basename をスペース区切り）:
    # Burst 1 (17): DSC_8145 ... DSC_8161
    DSC_8145 DSC_8146 ... DSC_8161
    ...
"""

from __future__ import annotations

import configparser
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_DEFAULT_GAP_SECONDS = 2.0
_SETTINGS_DIR = Path(__file__).resolve().parent.parent / "settings"


def _load_gap_seconds() -> float:
    """settings/*.ini の [cluster] burst_gap_seconds を読む（なければデフォルト）。"""
    for ini in sorted(_SETTINGS_DIR.glob("*.ini")):
        parser = configparser.ConfigParser()
        try:
            parser.read(ini, encoding="utf-8")
        except (OSError, configparser.Error):
            continue
        if parser.has_option("cluster", "burst_gap_seconds"):
            try:
                return float(parser.get("cluster", "burst_gap_seconds"))
            except ValueError:
                pass
    return _DEFAULT_GAP_SECONDS


def _collect_nefs(args: list[str]) -> list[Path]:
    if len(args) == 1 and Path(args[0]).is_dir():
        return sorted(Path(args[0]).glob("*.NEF"))
    return [Path(a) for a in args]


def _capture_times(nefs: list[Path]) -> dict[Path, float]:
    """exiftool を1回だけ呼び、各NEFの撮影時刻(サブ秒込み epoch)を返す。"""
    if not nefs:
        return {}
    out = subprocess.run(
        [
            "exiftool", "-T", "-q",
            "-DateTimeOriginal", "-SubSecTimeOriginal", "-FileName",
            *[str(p) for p in nefs],
        ],
        capture_output=True, text=True, check=False,
    ).stdout

    by_name = {p.name: p for p in nefs}
    times: dict[Path, float] = {}
    for line in out.splitlines():
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        dto, subsec, name = cols[0], cols[1], cols[2]
        path = by_name.get(name)
        if path is None or dto in ("", "-"):
            continue
        try:
            epoch = datetime.strptime(dto, "%Y:%m:%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if subsec not in ("", "-"):
            try:
                epoch += float(f"0.{subsec}")
            except ValueError:
                pass
        times[path] = epoch
    return times


def cluster_bursts(
    nefs: list[Path], gap_seconds: float, times: dict[Path, float] | None = None,
) -> list[list[Path]]:
    if times is None:
        times = _capture_times(nefs)
    # 撮影時刻が取れたものは時刻順、取れないものはファイル名順で末尾に。
    ordered = sorted(nefs, key=lambda p: (p not in times, times.get(p, 0.0), p.name))

    bursts: list[list[Path]] = []
    prev_time: float | None = None
    for path in ordered:
        t = times.get(path)
        new_group = (
            not bursts
            or t is None
            or prev_time is None
            or (t - prev_time) > gap_seconds
        )
        if new_group:
            bursts.append([])
        bursts[-1].append(path)
        prev_time = t
    return bursts


def main(argv: list[str]) -> int:
    if not argv:
        print(f"Usage: {sys.argv[0]} <DIR | NEF...>", file=sys.stderr)
        return 1
    nefs = _collect_nefs(argv)
    if not nefs:
        print("No NEF files found.", file=sys.stderr)
        return 1

    gap = _load_gap_seconds()
    bursts = cluster_bursts(nefs, gap)
    for i, burst in enumerate(bursts, 1):
        names = [p.stem for p in burst]
        print(f"# Burst {i} ({len(names)}): {names[0]} .. {names[-1]}")
        print(" ".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
