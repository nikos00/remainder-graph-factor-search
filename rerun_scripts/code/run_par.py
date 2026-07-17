#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_par.py

Thin wrapper that selects experiment number(s) and calls run_par_exp.py with the
corresponding parameter/primes files.

Supports:
  --stop-on-root [K]   (optional int; default 0=disabled; bare flag => K=1)

Also ALWAYS enables --hard-timelimit when invoking run_par_exp.py (per project policy).
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys


def _nonneg_int(v: str) -> int:
    try:
        x = int(v)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    if x < 0:
        raise argparse.ArgumentTypeError("Expected a non-negative integer")
    return x


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run experiment(s) by number via run_par_exp.py (parallel over (s,p) pairs)."
    )
    parser.add_argument(
        "--exp",
        required=True,
        type=int,
        nargs="+",
        help="Experiment number(s). For each N, uses param_dig.N.txt and s_p.N.txt",
    )
    parser.add_argument(
        "--stop-on-root",
        nargs="?",
        const=1,
        type=_nonneg_int,
        default=0,
        metavar="K",
        help="Stop after K roots are found. If provided with no value, K=1. Default: 0 (disabled).",
    )
    parser.add_argument(
        "--no-zero-row",
        action="store_true",
        help="Do not emit a zero row on TIMEOUT_NO_ROOTS",
    )
    parser.add_argument(
        "--format",
        type=int,
        default=1,
        help="Output format version (default: 1)",
    )
    parser.add_argument(
        "--id",
        type=int,
        default=None,
        help="Run only the Nth experiment line (1-based) inside the parameter file. If omitted, run all.",
    )
    parser.add_argument(
        "--streaming-bfs",
        action="store_true",
        help="Use streaming BFS traversal (level-by-level). Default mode.",
    )
    parser.add_argument(
        "--level-only",
        type=int,
        default=None,
        metavar="L",
        help="Enumerate and test only level L using O(L) memory.",
    )
    parser.add_argument(
        "--strict-level-only",
        dest="strict_level_only",
        action="store_true",
        default=True,
        help="Default: when --level-only is omitted, use depth as the exact level to enumerate/test.",
    )
    parser.add_argument(
        "--no-strict-level-only",
        dest="strict_level_only",
        action="store_false",
        help="Disable strict level-only behavior and run levels 1..depth.",
    )
    parser.add_argument(
        "--heartbeat-every",
        type=_nonneg_int,
        default=0,
        metavar="N",
        help="Emit heartbeat every N tested fractions (0=off).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command(s) and exit without running them",
    )

    args = parser.parse_args(argv[1:])

    for exp in args.exp:
        par_path = f"param_dig.{exp}.txt"
        sp_path = f"s_p.{exp}.txt"
        out_dir = f"./exp_{exp}"

        cmd = [
            sys.executable,
            "run_par_exp.py",
            "--par", par_path,
            "--sp", sp_path,
            "--out", out_dir,
            "--format", str(args.format),
            "--hard-timelimit",  # ALWAYS ON
        ]

        if args.streaming_bfs:
            cmd.append("--streaming-bfs")

        if args.id is not None:
            cmd.extend(["--id", str(args.id)])

        if args.level_only is not None:
            if args.level_only < 1:
                raise ValueError("--level-only must be >= 1")
            cmd.extend(["--level-only", str(args.level_only)])

        if args.strict_level_only:
            cmd.append("--strict-level-only")

        if args.heartbeat_every > 0:
            cmd.extend(["--heartbeat-every", str(args.heartbeat_every)])

        if args.stop_on_root > 0:
            cmd.extend(["--stop-on-root", str(args.stop_on_root)])

        if args.no_zero_row:
            cmd.append("--no-zero-row")

        if args.dry_run:
            print(shlex.join(cmd))
            continue

        print("Running:", shlex.join(cmd), flush=True)
        subprocess.run(cmd, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
