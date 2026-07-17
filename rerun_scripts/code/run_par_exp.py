#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_par_exp.py

Parallel runner: for each parameters line (experiment), run all (s,p) pairs in parallel.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple

from run_experiments_cli_streaming_rootsN import (
    _iter_nonempty_lines,
    _parse_ints_from_line,
    run_one_experiment,
)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Parallel runner: each experiment line runs all (s,p) pairs in parallel"
    )
    parser.add_argument(
        "--par",
        required=True,
        help="Parameter file (lines: Nmin Mmax W depth timelimit_sec)",
    )
    parser.add_argument(
        "--sp",
        required=True,
        help="Prime pairs file (lines: s p)",
    )
    parser.add_argument(
        "--out",
        default="results",
        help="Output directory (default: results/)",
    )
    parser.add_argument(
        "--no-zero-row",
        action="store_true",
        help="Do not emit a zero row on TIMEOUT_NO_ROOTS",
    )
    parser.add_argument(
        "--stop-on-root",
        nargs="?",
        const=1,
        default=0,
        type=int,
        help=(
            "Stop after K roots are found. If provided with no value, K=1. "
            "If omitted, K=0 (do not stop early)."
        ),
    )
    tl = parser.add_mutually_exclusive_group()
    tl.add_argument(
        "--hard-timelimit",
        action="store_true",
        default=False,
        help="Enforce a hard timelimit (default: ON)",
    )
    tl.add_argument(
        "--soft-timelimit",
        action="store_true",
        default=False,
        help=(
            "Use soft timelimit semantics (i.e., allow finishing the current work)."
        ),
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
        help="Run only the Nth experiment line (1-based). If omitted, run all.",
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
        default=False,
        help="If --level-only is omitted, use depth as the exact level to enumerate/test.",
    )
    parser.add_argument(
        "--no-strict-level-only",
        dest="strict_level_only",
        action="store_false",
        help="Disable strict level-only behavior.",
    )
    parser.add_argument(
        "--heartbeat-every",
        type=int,
        default=0,
        metavar="N",
        help="Emit a lightweight heartbeat every N tested fractions (0=off).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Maximum number of prime-pair tasks to run concurrently "
            "(default: all pairs)."
        ),
    )

    args = parser.parse_args(argv[1:])

    params_path = args.par
    primes_path = args.sp
    out_dir = args.out

    os.makedirs(out_dir, exist_ok=True)

    primes: List[Tuple[int, int]] = []
    for ln, line in _iter_nonempty_lines(primes_path):
        s, p = _parse_ints_from_line(line, 2, f"{primes_path}:{ln}")
        if s <= 1 or p <= 1:
            raise ValueError(f"{primes_path}:{ln}: s and p must be > 1")
        primes.append((s, p))

    if not primes:
        raise ValueError("No prime pairs found")

    experiments: List[Tuple[int, Tuple[int, int, int, int, int]]] = []
    exp_id = 0
    for _, line in _iter_nonempty_lines(params_path):
        exp_id += 1
        Nmin, Mmax, W, depth, tlimit = _parse_ints_from_line(
            line, 5, f"{params_path}:exp#{exp_id}"
        )
        experiments.append((exp_id, (Nmin, Mmax, W, depth, tlimit)))

    if not experiments:
        raise ValueError("No experiments found")

    if args.id is not None:
        if args.id < 1 or args.id > len(experiments):
            raise ValueError(
                f"--id {args.id} is out of range (1..{len(experiments)})"
            )
        experiments = [experiments[args.id - 1]]

    hard_timelimit = not args.soft_timelimit
    traversal_mode = "streaming-bfs"
    if args.streaming_bfs:
        traversal_mode = "streaming-bfs"
    if args.level_only is not None and args.level_only < 1:
        raise ValueError("--level-only must be >= 1")
    if args.heartbeat_every < 0:
        raise ValueError("--heartbeat-every must be >= 0")
    if args.workers is not None and args.workers < 1:
        raise ValueError("--workers must be >= 1")

    for (id_line, params) in experiments:
        Nmin, Mmax, W, depth, tlimit = params
        max_workers = min(args.workers or len(primes), len(primes))
        print(
            f"Starting experiment id={id_line} "
            f"({len(primes)} pairs, at most {max_workers} concurrent) "
            f"params=Nmin:{Nmin} Mmax:{Mmax} W:{W} depth:{depth} timelimit_sec:{tlimit}",
            flush=True,
        )
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = []
            for (s, p) in primes:
                futures.append(
                    ex.submit(
                        run_one_experiment,
                        id_line=id_line,
                        params=params,
                        s=s,
                        p=p,
                        out_dir=out_dir,
                        emit_zero_row=not args.no_zero_row,
                        stop_after_roots=args.stop_on_root,
                        hard_timelimit=hard_timelimit,
                        fmt_version=args.format,
                        traversal_mode=traversal_mode,
                        level_only=args.level_only,
                        strict_level_only=args.strict_level_only,
                        heartbeat_every=args.heartbeat_every,
                    )
                )
            for fut in as_completed(futures):
                # Propagate any exceptions
                fut.result()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
