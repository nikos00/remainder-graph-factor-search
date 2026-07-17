#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_experiments_cli.py

Batch CLI runner for Nikos Fractions inverted tree + dummy root search.

Inputs (2 files):
  1) parameters.exp.txt
     Each non-empty, non-comment line:
        Nmin  Mmax  W  depth  timelimit_sec

     Line number (1-based) is "id" used in output filenames.

  2) primes.exp.txt
     Each non-empty, non-comment line:
        s  p

For each parameters line (id) and for each (s,p) pair:
  - Stream inverted Nikos Fractions intervals in BFS order (levels 1..depth)
    without building a static full tree in memory.
  - Collect unique reduced fractions + provenance rows (level/sub_interval/parent interval)
  - Optional level-only mode enumerates a single level with O(level) memory.
  - Search roots using dummy_optimized_v5.dummy_check_An_x0_fraction(N, x0, n, d)
  - Timeout rule (default):
      If elapsed wall-clock time > timelimit_sec AND roots_found == 0:
        stop this run immediately, write TIMEOUT_NO_ROOTS output (with a single zero row), continue.
    With --hard-timelimit:
      If elapsed wall-clock time > timelimit_sec:
        stop this run immediately; if roots_found > 0, write TIMEOUT_WITH_ROOTS with partial rows.

Output:
  One file per run:
    result_<s>_<p>_<id>.out.txt
  One live progress sidecar per run (updated while running):
    result_<s>_<p>_<id>.progress.txt

Format:
  Header (# key=value)
  COLUMNS line
  Data rows (one per root)
  Includes examined_pct after interval_examined_L interval_examined_R
"""

from __future__ import annotations
import argparse

import os
import sys
import time
import math
from dataclasses import dataclass
import multiprocessing as mp
from typing import List, Tuple, Optional, Iterable

# --- local modules (must be in same dir or PYTHONPATH) ---
try:
    import nikos_fractions_core as core
except Exception as e:
    raise RuntimeError(
        "Cannot import nikos_fractions_core.py. Put run_experiments_cli.py next to it."
    ) from e

try:
    import dummy_optimized_v5 as dummy_backend
except Exception:
    try:
        import dummy_optimized_v4 as dummy_backend
    except Exception:
        try:
            import dummy_optimized_v3 as dummy_backend
        except Exception as e:
            raise RuntimeError(
                "Cannot import dummy_optimized_v5, dummy_optimized_v4, or dummy_optimized_v3. Put them next to run_experiments_cli_streaming_rootsN.py."
            ) from e


Frac = Tuple[int, int]  # (num, den)


# -------------------------
# Utilities: parsing
# -------------------------
def _iter_nonempty_lines(path: str) -> Iterable[Tuple[int, str]]:
    """Yield (lineno_1based, stripped_line) for non-empty, non-comment lines."""
    with open(path, "r", encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            yield i, line


def _parse_ints_from_line(line: str, expected: int, ctx: str) -> List[int]:
    parts = line.split()
    if len(parts) != expected:
        raise ValueError(f"{ctx}: expected {expected} integers, got {len(parts)}: {line!r}")
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            raise ValueError(f"{ctx}: invalid integer token {p!r} in line {line!r}")
    return out


# -------------------------
# Fractions helpers
# -------------------------
def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)


def reduce_frac(f: Frac) -> Frac:
    n, d = f
    if d == 0:
        raise ValueError("Zero denominator.")
    if d < 0:
        n, d = -n, -d
    g = gcd(abs(n), d)
    return (n // g, d // g)


def frac_str(f: Frac) -> str:
    return f"{f[0]}/{f[1]}"


def root_str(x) -> str:
    """Stringify root values returned by dummy backend (may be int or Fraction-like)."""
    try:
        # fractions.Fraction has numerator/denominator
        num = getattr(x, "numerator", None)
        den = getattr(x, "denominator", None)
        if num is not None and den is not None:
            if int(den) == 1:
                return str(int(num))
            return f"{int(num)}/{int(den)}"
    except Exception:
        pass
    # fallback
    try:
        return str(int(x))
    except Exception:
        return str(x)


def examined_pct(interval_examined: Tuple[Optional[int], Optional[int]], sqrtN: int) -> float:
    """Percent of [1..sqrtN] covered by examined interval (integer-point measure), clamped."""
    L, R = interval_examined
    if L is None or R is None or sqrtN <= 0:
        return 0.0
    try:
        L = int(L)
        R = int(R)
    except Exception:
        return 0.0
    if L > R:
        L, R = R, L
    # clamp to [1, sqrtN]
    a = max(1, L)
    b = min(sqrtN, R)
    if a > b:
        return 0.0
    pts = (b - a + 1)
    return 100.0 * (pts / float(sqrtN))


# -------------------------
# Tree building + provenance
# -------------------------
@dataclass(frozen=True)
class IntervalProv:
    level: int
    left: Frac
    right: Frac
    median: Frac
    parent_left: Frac
    parent_right: Frac
    # a compact path token (optional; kept small)
    path: str


@dataclass(frozen=True)
class FractionProv:
    frac: Frac            # reduced
    level: int
    interval_left: Frac   # reduced
    interval_right: Frac  # reduced
    parent_left: Frac     # reduced (or 0/0 for level 1 if you prefer; here: same as parent interval)
    parent_right: Frac    # reduced
    path: str             # string token


def _validate_tree_params(Nmin: int, Mmax: int, W: int, depth: int) -> None:
    if Nmin < 1:
        raise ValueError("Nmin must be >= 1.")
    if Mmax < 2:
        raise ValueError("Mmax must be >= 2.")
    if Nmin >= Mmax:
        raise ValueError("Need Nmin < Mmax.")
    if W < 0:
        raise ValueError("W must be >= 0.")
    if depth < 1:
        raise ValueError("depth must be >= 1.")


def iter_intervals_inverted_bfs_with_prov(
    Nmin: int, Mmax: int, W: int, depth: int, include_paths: bool = True
) -> Iterable[IntervalProv]:
    """
    Streaming BFS generator (level-by-level) for inverted intervals.

    Memory behavior:
      - Only current level and next level are stored.
      - No static tree and no all-level structure is allocated.
    """
    _validate_tree_params(Nmin=Nmin, Mmax=Mmax, W=W, depth=depth)

    current_level: List[Tuple[Frac, Frac, Frac, Frac, str]] = []
    for m in range(Nmin, Mmax):
        left = (1, m + 1)
        right = (1, m)
        path = f"{frac_str(reduce_frac(left))}>{frac_str(reduce_frac(right))}" if include_paths else ""
        current_level.append((left, right, left, right, path))

    for lvl in range(1, depth + 1):
        next_level: List[Tuple[Frac, Frac, Frac, Frac, str]] = []
        for left, right, parent_left, parent_right, path in current_level:
            median = core.mediant(left, right)
            yield IntervalProv(
                level=lvl,
                left=left,
                right=right,
                median=median,
                parent_left=parent_left,
                parent_right=parent_right,
                path=path,
            )
            if lvl >= depth:
                continue
            pts = core.refine_interval(left, right, W=W)
            for i in range(len(pts) - 1):
                c_left = pts[i]
                c_right = pts[i + 1]
                if include_paths:
                    cpath = f"{path}|{frac_str(reduce_frac(c_left))}>{frac_str(reduce_frac(c_right))}"
                else:
                    cpath = ""
                next_level.append((c_left, c_right, left, right, cpath))
        current_level = next_level


def iter_level(
    level: int, Nmin: int, Mmax: int, W: int, include_paths: bool = True
) -> Iterable[IntervalProv]:
    """
    Enumerate a single requested level using O(level) path state.
    No recursion, no BFS queue, no full-level storage.
    """
    _validate_tree_params(Nmin=Nmin, Mmax=Mmax, W=W, depth=max(1, level))
    if level < 1:
        raise ValueError("level must be >= 1")

    for m in range(Nmin, Mmax):
        root_left = (1, m + 1)
        root_right = (1, m)
        root_path = f"{frac_str(reduce_frac(root_left))}>{frac_str(reduce_frac(root_right))}" if include_paths else ""

        if level == 1:
            yield IntervalProv(
                level=1,
                left=root_left,
                right=root_right,
                median=core.mediant(root_left, root_right),
                parent_left=root_left,
                parent_right=root_right,
                path=root_path,
            )
            continue

        lefts: List[Optional[Frac]] = [None] * (level + 1)
        rights: List[Optional[Frac]] = [None] * (level + 1)
        parent_lefts: List[Optional[Frac]] = [None] * (level + 1)
        parent_rights: List[Optional[Frac]] = [None] * (level + 1)
        paths: List[str] = [""] * (level + 1)
        child_points: List[Optional[List[Frac]]] = [None] * (level + 1)
        child_idx: List[int] = [0] * (level + 1)

        lefts[1] = root_left
        rights[1] = root_right
        parent_lefts[1] = root_left
        parent_rights[1] = root_right
        paths[1] = root_path

        cur_level = 1
        while cur_level >= 1:
            if cur_level == level:
                c_left = lefts[cur_level]
                c_right = rights[cur_level]
                p_left = parent_lefts[cur_level]
                p_right = parent_rights[cur_level]
                if c_left is None or c_right is None or p_left is None or p_right is None:
                    raise RuntimeError("Internal level enumerator state corrupted.")
                yield IntervalProv(
                    level=cur_level,
                    left=c_left,
                    right=c_right,
                    median=core.mediant(c_left, c_right),
                    parent_left=p_left,
                    parent_right=p_right,
                    path=paths[cur_level],
                )
                cur_level -= 1
                continue

            pts = child_points[cur_level]
            if pts is None:
                c_left = lefts[cur_level]
                c_right = rights[cur_level]
                if c_left is None or c_right is None:
                    raise RuntimeError("Internal level enumerator state corrupted.")
                pts = core.refine_interval(c_left, c_right, W=W)
                child_points[cur_level] = pts
                child_idx[cur_level] = 0

            i = child_idx[cur_level]
            if i >= len(pts) - 1:
                child_points[cur_level] = None
                child_idx[cur_level] = 0
                cur_level -= 1
                continue

            child_idx[cur_level] += 1
            nxt = cur_level + 1
            c_left = pts[i]
            c_right = pts[i + 1]
            p_left = lefts[cur_level]
            p_right = rights[cur_level]
            if p_left is None or p_right is None:
                raise RuntimeError("Internal level enumerator state corrupted.")
            lefts[nxt] = c_left
            rights[nxt] = c_right
            parent_lefts[nxt] = p_left
            parent_rights[nxt] = p_right
            if include_paths:
                token = f"{frac_str(reduce_frac(c_left))}>{frac_str(reduce_frac(c_right))}"
                paths[nxt] = f"{paths[cur_level]}|{token}"
            else:
                paths[nxt] = ""
            if nxt < level:
                child_points[nxt] = None
                child_idx[nxt] = 0
            cur_level = nxt


# Backward-compatible alias; now implemented as BFS.
def iter_intervals_inverted_with_prov(
    Nmin: int, Mmax: int, W: int, depth: int, include_paths: bool = True
) -> Iterable[IntervalProv]:
    return iter_intervals_inverted_bfs_with_prov(
        Nmin=Nmin, Mmax=Mmax, W=W, depth=depth, include_paths=include_paths
    )


def iter_unique_fractions_first_prov(
    Nmin: int,
    Mmax: int,
    W: int,
    depth: int,
    include_paths: bool = True,
    *,
    traversal_mode: str = "streaming-bfs",
    level_only: Optional[int] = None,
    dedup_scope: str = "global",
) -> Iterable[Tuple[Frac, FractionProv]]:
    """
    Stream reduced fractions in deterministic order with first provenance.
    """
    if level_only is not None and level_only < 1:
        raise ValueError("--level-only must be >= 1")
    if dedup_scope not in ("global", "level", "none"):
        raise ValueError("dedup_scope must be one of: global, level, none")
    if traversal_mode != "streaming-bfs":
        raise ValueError(f"Unsupported traversal_mode={traversal_mode!r}")

    if level_only is not None:
        interval_iter = iter_level(
            level=level_only, Nmin=Nmin, Mmax=Mmax, W=W, include_paths=include_paths
        )
    else:
        interval_iter = iter_intervals_inverted_bfs_with_prov(
            Nmin=Nmin, Mmax=Mmax, W=W, depth=depth, include_paths=include_paths
        )

    seen_global = set()
    seen_level = set()
    current_level = -1

    for it in interval_iter:
        lvl = it.level
        if dedup_scope == "level" and lvl != current_level:
            seen_level.clear()
            current_level = lvl

        iL = reduce_frac(it.left)
        iR = reduce_frac(it.right)
        pL = reduce_frac(it.parent_left)
        pR = reduce_frac(it.parent_right)

        def maybe_pair(fr: Frac) -> Optional[Tuple[Frac, FractionProv]]:
            r = reduce_frac(fr)
            if dedup_scope == "global":
                if r in seen_global:
                    return None
                seen_global.add(r)
            elif dedup_scope == "level":
                if r in seen_level:
                    return None
                seen_level.add(r)
            row = FractionProv(
                frac=r,
                level=lvl,
                interval_left=iL,
                interval_right=iR,
                parent_left=pL,
                parent_right=pR,
                path=it.path,
            )
            return (r, row)

        for fr in (it.left, it.median, it.right):
            pair = maybe_pair(fr)
            if pair is not None:
                yield pair


def _dummy_worker_main(conn) -> None:
    """
    Isolated worker process for dummy_check calls.
    A hung call is handled by terminating/restarting this process from parent.
    """
    try:
        import dummy_optimized_v5 as backend
    except Exception:
        try:
            import dummy_optimized_v4 as backend
        except Exception:
            import dummy_optimized_v3 as backend

    while True:
        msg = conn.recv()
        if msg is None:
            break
        task_id, N, x0, n, d, deadline_seconds = msg
        deadline = None
        if deadline_seconds is not None:
            deadline = time.perf_counter() + max(0.0, float(deadline_seconds))
        try:
            ret = _call_dummy_backend(
                backend=backend,
                N=N,
                x0=x0,
                n=n,
                d=d,
                deadline=deadline,
            )
            conn.send((task_id, "ok", ret))
        except Exception as e:
            conn.send((task_id, "error", repr(e)))


def _call_dummy_backend(
    *,
    backend,
    N: int,
    x0: int,
    n: int,
    d: int,
    deadline: Optional[float],
):
    try:
        return backend.dummy_check_An_x0_fraction(
            N,
            x0,
            n,
            d,
            return_coeffs=False,
            deadline=deadline,
            time_check_every=1 if deadline is not None else 2048,
            collect_trace=False,
            verbose_roots=False,
            lean_output=True,
            validate_limits=False,
            return_root_details=True,
        )
    except TypeError:
        return backend.dummy_check_An_x0_fraction(
            N,
            x0,
            n,
            d,
            return_coeffs=False,
            deadline=deadline,
            time_check_every=1 if deadline is not None else 2048,
            collect_trace=False,
            verbose_roots=False,
            lean_output=True,
            validate_limits=False,
        )


def _get_mp_context() -> mp.context.BaseContext:
    try:
        return mp.get_context("fork")
    except ValueError:
        return mp.get_context("spawn")


class DummyCheckRunner:
    def __init__(self) -> None:
        self._ctx = _get_mp_context()
        self._proc = None
        self._conn = None
        self._task_id = 0
        self._disabled = False

    def _ensure_started(self) -> None:
        if self._disabled:
            return
        if self._proc is not None and self._proc.is_alive() and self._conn is not None:
            return
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        try:
            parent_conn, child_conn = self._ctx.Pipe(duplex=True)
            proc = self._ctx.Process(target=_dummy_worker_main, args=(child_conn,), daemon=True)
            proc.start()
            child_conn.close()
            self._proc = proc
            self._conn = parent_conn
        except Exception:
            # Fallback for environments where spawning a child process is not allowed.
            self._disabled = True
            self._kill_worker()

    def _kill_worker(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        if self._proc is not None:
            try:
                if self._proc.is_alive():
                    self._proc.terminate()
                self._proc.join(timeout=1.0)
            except Exception:
                pass
            self._proc = None

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.send(None)
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        if self._proc is not None:
            try:
                self._proc.join(timeout=1.0)
                if self._proc.is_alive():
                    self._proc.terminate()
                    self._proc.join(timeout=1.0)
            except Exception:
                pass
            self._proc = None

    def run(
        self,
        *,
        N: int,
        x0: int,
        n: int,
        d: int,
        timeout_sec: Optional[float],
    ) -> Tuple[str, Optional[object]]:
        """
        Return:
          ("ok", ret) on success
          ("timed_out", None) if call exceeded timeout (worker terminated)
          ("error", None) on call error
        """
        self._ensure_started()
        if self._disabled:
            local_deadline = None
            if timeout_sec is not None:
                local_deadline = time.perf_counter() + max(0.0, timeout_sec)
            try:
                ret = _call_dummy_backend(
                    backend=dummy_backend,
                    N=N,
                    x0=x0,
                    n=n,
                    d=d,
                    deadline=local_deadline,
                )
                return ("ok", ret)
            except Exception:
                return ("error", None)
        if self._conn is None:
            return ("error", None)

        self._task_id += 1
        task_id = self._task_id
        try:
            self._conn.send((task_id, N, x0, n, d, timeout_sec))
        except Exception:
            self._kill_worker()
            return ("error", None)

        try:
            if timeout_sec is None:
                msg = self._conn.recv()
            else:
                if timeout_sec <= 0.0 or not self._conn.poll(timeout_sec):
                    self._kill_worker()
                    return ("timed_out", None)
                msg = self._conn.recv()
        except Exception:
            self._kill_worker()
            return ("error", None)

        if not isinstance(msg, tuple) or len(msg) != 3:
            return ("error", None)
        msg_task_id, status, payload = msg
        if msg_task_id != task_id:
            return ("error", None)
        if status == "ok":
            return ("ok", payload)
        return ("error", None)

# -------------------------
# Output writer
# -------------------------
def write_output_file(
    out_path: str,
    *,
    fmt_version: int,
    run_id: str,
    id_line: int,
    s: int,
    p: int,
    N: int,
    sqrtN: int,
    Nmin: int,
    Mmax: int,
    W: int,
    depth: int,
    timelimit_sec: int,
    status: str,
    stopped_reason: str,
    roots_found: int,
    fractions_tested: int,
    unique_fractions: int,
    build_time_sec: float,
    search_time_sec: float,
    total_time_sec: float,
    error_message: str = "",
    rows: Optional[List[str]] = None,
    emit_zero_row_on_timeout: bool = True,
):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        # Header
        f.write(f"# format_version={fmt_version}\n")
        f.write(f"# run_id={run_id}\n")
        f.write(f"# id={id_line}\n")
        f.write(f"# s={s}\n")
        f.write(f"# p={p}\n")
        f.write(f"# N={N}\n")
        f.write(f"# sqrtN={sqrtN}\n")
        f.write(f"# Nmin={Nmin}\n")
        f.write(f"# Mmax={Mmax}\n")
        f.write(f"# W={W}\n")
        f.write(f"# depth={depth}\n")
        f.write(f"# timelimit_sec={timelimit_sec}\n")
        f.write(f"# status={status}\n")
        f.write(f"# roots_found={roots_found}\n")
        f.write(f"# fractions_tested={fractions_tested}\n")
        f.write(f"# unique_fractions={unique_fractions}\n")
        f.write(f"# build_time_sec={build_time_sec:.6f}\n")
        f.write(f"# search_time_sec={search_time_sec:.6f}\n")
        f.write(f"# total_time_sec={total_time_sec:.6f}\n")
        f.write(f"# stopped_reason={stopped_reason}\n")
        f.write(f"# error_message={error_message}\n")

        # Columns
        f.write(
            "COLUMNS "
            "run_id root_idx x0 root_x triplet_x0 triplet_x2 aF bF loop_i loop_dx "
            "offset frac_n frac_d level "
            "interval_L interval_R parent_L parent_R "
            "interval_examined_L interval_examined_R examined_pct frac_path\n"
        )

        # Rows
        if rows:
            for r in rows:
                f.write(r + "\n")
        else:
            if status == "TIMEOUT_NO_ROOTS" and emit_zero_row_on_timeout:
                f.write(
                    "0:0:0 0 0 0 0 0 0/1 0/1 0 0 0 0 0 "
                    "0/0 0/0 0/0 0/0 0 0 0.000000 -\n"
                )



def write_meta_file(
    meta_path: str,
    *,
    run_id: str,
    id_line: int,
    s: int,
    p: int,
    N: int,
    Nmin: int,
    Mmax: int,
    W: int,
    depth: int,
    timelimit_sec: int,
    hard_timelimit: bool,
    stop_after_roots: int,
    status: str,
    stopped_reason: str,
    roots_found: int,
    fractions_tested: int,
    unique_fractions: int,
    total_time_sec: float,
    last_fraction_started: Optional[Frac] = None,
    last_level_started: Optional[int] = None,
    last_fraction_new_root: Optional[Frac] = None,
    last_level_new_root: Optional[int] = None,
    traversal_mode: str = "streaming-bfs",
    level_only: Optional[int] = None,
    dummy_call_timeouts: int = 0,
    error_message: str = "",
) -> None:
    """Write a small per-run metadata file (one key per line)."""
    os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(f"run_id: {run_id}\n")
        f.write(f"id: {id_line}\n")
        f.write(f"s: {s}\n")
        f.write(f"p: {p}\n")
        f.write(f"N: {N}\n")
        f.write(f"Nmin: {Nmin}\n")
        f.write(f"Mmax: {Mmax}\n")
        f.write(f"W: {W}\n")
        f.write(f"depth: {depth}\n")
        f.write(f"timelimit_sec: {timelimit_sec}\n")
        f.write(f"hard_timelimit: {str(bool(hard_timelimit)).lower()}\n")
        f.write(f"stop_after_roots: {int(stop_after_roots)}\n")
        f.write(f"status: {status}\n")
        f.write(f"stopped_reason: {stopped_reason}\n")
        f.write(f"roots_found: {int(roots_found)}\n")
        f.write(f"fractions_tested: {int(fractions_tested)}\n")
        f.write(f"unique_fractions: {int(unique_fractions)}\n")
        f.write(f"elapsed_seconds: {total_time_sec:.6f}\n")
        f.write(f"traversal_mode: {traversal_mode}\n")
        f.write(f"level_only: {int(level_only) if level_only is not None else 'none'}\n")
        f.write(f"dummy_call_timeouts: {int(dummy_call_timeouts)}\n")
        f.write(f"last_fraction_started: {frac_str(last_fraction_started) if last_fraction_started else 'none'}\n")
        f.write(f"last_level_started: {str(int(last_level_started)) if last_level_started is not None else 'none'}\n")
        f.write(f"last_fraction_new_root: {frac_str(last_fraction_new_root) if last_fraction_new_root else 'none'}\n")
        f.write(f"last_level_new_root: {str(int(last_level_new_root)) if last_level_new_root is not None else 'none'}\n")
        if error_message:
            f.write(f"error_message: {error_message}\n")


def write_progress_file(
    progress_path: str,
    *,
    run_id: str,
    id_line: int,
    s: int,
    p: int,
    N: int,
    Nmin: int,
    Mmax: int,
    W: int,
    depth: int,
    timelimit_sec: int,
    phase: str,
    roots_found: int,
    fractions_tested: int,
    unique_fractions: int,
    elapsed_seconds: float,
    first_root_elapsed: Optional[float],
    last_fraction_started: Optional[Frac],
    last_level_started: Optional[int],
    last_fraction_new_root: Optional[Frac],
    last_level_new_root: Optional[int],
    status_hint: str = "",
    stopped_reason_hint: str = "",
) -> None:
    """Write/overwrite a lightweight live progress file for an in-flight run."""
    os.makedirs(os.path.dirname(progress_path) or ".", exist_ok=True)
    with open(progress_path, "w", encoding="utf-8") as f:
        f.write(f"run_id: {run_id}\n")
        f.write(f"id: {id_line}\n")
        f.write(f"s: {s}\n")
        f.write(f"p: {p}\n")
        f.write(f"N: {N}\n")
        f.write(f"Nmin: {Nmin}\n")
        f.write(f"Mmax: {Mmax}\n")
        f.write(f"W: {W}\n")
        f.write(f"depth: {depth}\n")
        f.write(f"timelimit_sec: {timelimit_sec}\n")
        f.write(f"phase: {phase}\n")
        if status_hint:
            f.write(f"status_hint: {status_hint}\n")
        if stopped_reason_hint:
            f.write(f"stopped_reason_hint: {stopped_reason_hint}\n")
        f.write(f"roots_found: {int(roots_found)}\n")
        f.write(f"fractions_tested: {int(fractions_tested)}\n")
        f.write(f"unique_fractions: {int(unique_fractions)}\n")
        f.write(f"elapsed_seconds: {elapsed_seconds:.6f}\n")
        if first_root_elapsed is None:
            f.write("first_root_elapsed: none\n")
        else:
            f.write(f"first_root_elapsed: {first_root_elapsed:.6f}\n")
        f.write(
            f"last_fraction_started: "
            f"{frac_str(last_fraction_started) if last_fraction_started else 'none'}\n"
        )
        f.write(
            f"last_level_started: "
            f"{str(int(last_level_started)) if last_level_started is not None else 'none'}\n"
        )
        f.write(
            f"last_fraction_new_root: "
            f"{frac_str(last_fraction_new_root) if last_fraction_new_root else 'none'}\n"
        )
        f.write(
            f"last_level_new_root: "
            f"{str(int(last_level_new_root)) if last_level_new_root is not None else 'none'}\n"
        )


# -------------------------
# Main run logic
# -------------------------
def run_one_experiment(
    *,
    id_line: int,
    params: Tuple[int, int, int, int, int],
    s: int,
    p: int,
    out_dir: str,
    emit_zero_row: bool,
    stop_after_roots: int,
    hard_timelimit: bool,
    fmt_version: int,
    traversal_mode: str = "streaming-bfs",
    level_only: Optional[int] = None,
    strict_level_only: bool = False,
    heartbeat_every: int = 0,
) -> None:
    Nmin, Mmax, W, depth, timelimit_sec = params
    effective_level_only = level_only
    if effective_level_only is None and strict_level_only:
        effective_level_only = depth
    N = s * p
    sqrtN = math.isqrt(N)
    run_id = f"{id_line}:{s}:{p}"
    out_name = f"result_{s}_{p}_{id_line}.out.txt"
    out_path = os.path.join(out_dir, out_name)

    meta_name = f"result_{s}_{p}_{id_line}.meta.txt"
    meta_path = os.path.join(out_dir, meta_name)
    progress_name = f"result_{s}_{p}_{id_line}.progress.txt"
    progress_path = os.path.join(out_dir, progress_name)

    start_wall = time.time()
    start_stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_wall))
    print(f"Exp id={id_line}, s={s}, Start time={start_stamp}", flush=True)

    t0 = time.perf_counter()
    build_t0 = t0
    deadline = t0 + timelimit_sec
    dummy_runner = DummyCheckRunner()

    try:
        # Stream unique fractions (no full tree / levels dict stored)
        # This keeps memory roughly O(frontier + #unique_fractions_seen).
        roots_found = 0
        fractions_tested = 0
        unique_fractions = 0
        rows: List[str] = []
        root_idx = 0
        reached_root_quota = False
        dummy_call_timeouts = 0
        last_fraction_started: Optional[Frac] = None
        last_level_started: Optional[int] = None
        last_fraction_new_root: Optional[Frac] = None
        last_level_new_root: Optional[int] = None

        # In streaming mode, "build_time" is not a separate phase; generation + checking are interleaved.
        build_time = 0.0

        search_t0 = time.perf_counter()
        first_root_time_sec: Optional[float] = None
        progress_last_write = -1.0
        progress_every_sec = 2.0

        def _search_time_for_output(search_elapsed_now: float) -> float:
            # If any root was found, report time-to-first-root; otherwise report full search elapsed.
            if first_root_time_sec is not None:
                return first_root_time_sec
            return search_elapsed_now

        def _write_progress(
            *,
            phase: str,
            force: bool = False,
            status_hint: str = "",
            stopped_reason_hint: str = "",
        ) -> None:
            nonlocal progress_last_write
            now = time.perf_counter()
            if (not force) and progress_last_write >= 0.0 and (now - progress_last_write) < progress_every_sec:
                return
            progress_last_write = now
            write_progress_file(
                progress_path,
                run_id=run_id,
                id_line=id_line,
                s=s,
                p=p,
                N=N,
                Nmin=Nmin,
                Mmax=Mmax,
                W=W,
                depth=depth,
                timelimit_sec=timelimit_sec,
                phase=phase,
                roots_found=roots_found,
                fractions_tested=fractions_tested,
                unique_fractions=unique_fractions,
                elapsed_seconds=now - t0,
                first_root_elapsed=first_root_time_sec,
                last_fraction_started=last_fraction_started,
                last_level_started=last_level_started,
                last_fraction_new_root=last_fraction_new_root,
                last_level_new_root=last_level_new_root,
                status_hint=status_hint,
                stopped_reason_hint=stopped_reason_hint,
            )

        _write_progress(phase="running", force=True)

        def _write_timeout_and_stop() -> bool:
            elapsed_total = time.perf_counter() - t0
            if elapsed_total <= timelimit_sec:
                return False
            if not (hard_timelimit or roots_found == 0):
                return False

            total_time = time.perf_counter() - t0
            search_time = time.perf_counter() - search_t0
            if roots_found == 0:
                # TIMEOUT with no roots: write file with zeros and stop
                _write_progress(
                    phase="finished",
                    force=True,
                    status_hint="TIMEOUT_NO_ROOTS",
                    stopped_reason_hint="timeout_no_roots",
                )
                write_output_file(
                    out_path,
                    fmt_version=fmt_version,
                    run_id=run_id,
                    id_line=id_line,
                    s=s,
                    p=p,
                    N=N,
                    sqrtN=sqrtN,
                    Nmin=Nmin,
                    Mmax=Mmax,
                    W=W,
                    depth=depth,
                    timelimit_sec=timelimit_sec,
                    status="TIMEOUT_NO_ROOTS",
                    stopped_reason="timeout_no_roots",
                    roots_found=0,
                    fractions_tested=fractions_tested,
                    unique_fractions=unique_fractions,
                    build_time_sec=build_time,
                    search_time_sec=_search_time_for_output(search_time),
                    total_time_sec=total_time,
                    rows=None,
                    emit_zero_row_on_timeout=emit_zero_row,
                )
                write_meta_file(
                    meta_path,
                    run_id=run_id,
                    id_line=id_line,
                    s=s,
                    p=p,
                    N=N,
                    Nmin=Nmin,
                    Mmax=Mmax,
                    W=W,
                    depth=depth,
                    timelimit_sec=timelimit_sec,
                    hard_timelimit=hard_timelimit,
                    stop_after_roots=stop_after_roots,
                    status="TIMEOUT_NO_ROOTS",
                    stopped_reason="timeout_no_roots",
                    roots_found=0,
                    fractions_tested=fractions_tested,
                    unique_fractions=unique_fractions,
                    total_time_sec=total_time,
                    last_fraction_started=last_fraction_started,
                    last_level_started=last_level_started,
                    last_fraction_new_root=last_fraction_new_root,
                    last_level_new_root=last_level_new_root,
                    traversal_mode=traversal_mode,
                    level_only=effective_level_only,
                    dummy_call_timeouts=dummy_call_timeouts,
                )
            else:
                # TIMEOUT with roots: write partial rows and stop
                _write_progress(
                    phase="finished",
                    force=True,
                    status_hint="TIMEOUT_WITH_ROOTS",
                    stopped_reason_hint="timeout_with_roots",
                )
                write_output_file(
                    out_path,
                    fmt_version=fmt_version,
                    run_id=run_id,
                    id_line=id_line,
                    s=s,
                    p=p,
                    N=N,
                    sqrtN=sqrtN,
                    Nmin=Nmin,
                    Mmax=Mmax,
                    W=W,
                    depth=depth,
                    timelimit_sec=timelimit_sec,
                    status="TIMEOUT_WITH_ROOTS",
                    stopped_reason="timeout_with_roots",
                    roots_found=roots_found,
                    fractions_tested=fractions_tested,
                    unique_fractions=unique_fractions,
                    build_time_sec=build_time,
                    search_time_sec=_search_time_for_output(search_time),
                    total_time_sec=total_time,
                    rows=rows,
                    emit_zero_row_on_timeout=emit_zero_row,
                )
                write_meta_file(
                    meta_path,
                    run_id=run_id,
                    id_line=id_line,
                    s=s,
                    p=p,
                    N=N,
                    Nmin=Nmin,
                    Mmax=Mmax,
                    W=W,
                    depth=depth,
                    timelimit_sec=timelimit_sec,
                    hard_timelimit=hard_timelimit,
                    stop_after_roots=stop_after_roots,
                    status="TIMEOUT_WITH_ROOTS",
                    stopped_reason="timeout_with_roots",
                    roots_found=roots_found,
                    fractions_tested=fractions_tested,
                    unique_fractions=unique_fractions,
                    total_time_sec=total_time,
                    last_fraction_started=last_fraction_started,
                    last_level_started=last_level_started,
                    last_fraction_new_root=last_fraction_new_root,
                    last_level_new_root=last_level_new_root,
                    traversal_mode=traversal_mode,
                    level_only=effective_level_only,
                    dummy_call_timeouts=dummy_call_timeouts,
                )
            return True

        for (fr, prov) in iter_unique_fractions_first_prov(
            Nmin=Nmin,
            Mmax=Mmax,
            W=W,
            depth=depth,
            include_paths=False,
            traversal_mode=traversal_mode,
            level_only=effective_level_only,
            dedup_scope="global",
        ):
            unique_fractions += 1
            if (unique_fractions & 2047) == 0:
                _write_progress(phase="running")

            # timeout check
            if _write_timeout_and_stop():
                return
            n, d = fr
            if n <= 0 or d <= 0:
                continue

            fractions_tested += 1

            # x0 as in GUI
            x0 = math.isqrt((N * n) // d)
            if x0 <= 0:
                continue

            # Track where we are in the fraction stream
            last_fraction_started = (n, d)
            last_level_started = prov.level if prov is not None else None

            if heartbeat_every > 0 and (fractions_tested % heartbeat_every) == 0:
                elapsed = time.perf_counter() - t0
                print(
                    f"HEARTBEAT run_id={run_id} elapsed={elapsed:.3f}s "
                    f"frac={n}/{d} level={last_level_started if last_level_started is not None else 0} "
                    f"fractions_tested={fractions_tested}",
                    flush=True,
                )

            enforce_timeout = hard_timelimit or roots_found == 0
            per_call_timeout = None
            if enforce_timeout:
                per_call_timeout = deadline - time.perf_counter()
                if per_call_timeout <= 0.0:
                    if _write_timeout_and_stop():
                        return
                    continue

            call_status, ret = dummy_runner.run(
                N=N,
                x0=x0,
                n=n,
                d=d,
                timeout_sec=per_call_timeout,
            )
            if call_status == "timed_out":
                dummy_call_timeouts += 1
                if _write_timeout_and_stop():
                    return
                continue
            if call_status != "ok":
                continue
            if _write_timeout_and_stop():
                return
            if not ret:
                continue

            if len(ret) >= 11:
                (
                    _x_inDummy,
                    _y_inDummy,
                    _x_zero,
                    _y_zero,
                    _x_neg,
                    _y_neg,
                    x_Roots,
                    x_RootDetails,
                    _x_left,
                    _x_right,
                    interval_examined,
                ) = ret[:11]
            else:
                (
                    _x_inDummy,
                    _y_inDummy,
                    _x_zero,
                    _y_zero,
                    _x_neg,
                    _y_neg,
                    x_Roots,
                    _x_left,
                    _x_right,
                    interval_examined,
                ) = ret
                x_RootDetails = []

            if not x_Roots:
                continue

            # Compute examined pct (same for all roots from this call)
            pct = examined_pct(interval_examined, sqrtN)
            Lx, Rx = interval_examined if interval_examined else (None, None)
            Lx_out = str(int(Lx)) if Lx is not None else "0"
            Rx_out = str(int(Rx)) if Rx is not None else "0"

            # Provenance fields (compact "a/b" tokens)
            if prov is not None:
                interval_L = frac_str(prov.interval_left)
                interval_R = frac_str(prov.interval_right)
                parent_L = frac_str(prov.parent_left)
                parent_R = frac_str(prov.parent_right)
                level_out = str(prov.level)
                path_out = prov.path if prov.path else "-"
            else:
                interval_L = "0/0"
                interval_R = "0/0"
                parent_L = "0/0"
                parent_R = "0/0"
                level_out = "0"
                path_out = "-"

            for root_local_idx, xr in enumerate(x_Roots):
                if stop_after_roots > 0 and roots_found >= stop_after_roots:
                    reached_root_quota = True
                    break
                if root_local_idx < len(x_RootDetails):
                    triplet_x0, triplet_x2, aF_out, bF_out, loop_i, loop_dx = x_RootDetails[root_local_idx]
                else:
                    triplet_x0, triplet_x2, aF_out, bF_out, loop_i, loop_dx = 0, 0, "0/1", "0/1", -1, 0
                # Row schema:
                # run_id root_idx x0 root_x triplet_x0 triplet_x2 aF bF loop_i loop_dx
                # offset frac_n frac_d level interval_L interval_R parent_L parent_R
                # interval_examined_L interval_examined_R examined_pct frac_path
                rows.append(
                    f"{run_id} {root_idx} {x0} {root_str(xr)} "
                    f"{triplet_x0} {triplet_x2} {aF_out} {bF_out} {loop_i} {loop_dx} "
                    f"{n} {n} {d} {level_out} "
                    f"{interval_L} {interval_R} {parent_L} {parent_R} "
                    f"{Lx_out} {Rx_out} {pct:.6f} {path_out}"
                )
                if first_root_time_sec is None:
                    first_root_time_sec = time.perf_counter() - search_t0
                    print(
                        f"Exp id={id_line}, s={s}, FIRST ROOT FOUND at "
                        f"elapsed={first_root_time_sec:.3f}s "
                        f"frac={n}/{d} level={level_out} x0={x0} root_x={root_str(xr)}",
                        flush=True,
                    )
                    _write_progress(
                        phase="first_root_found",
                        force=True,
                        status_hint="RUNNING_WITH_ROOTS",
                    )
                root_idx += 1
                roots_found += 1
                last_fraction_new_root = (n, d)
                last_level_new_root = prov.level if prov is not None else None
            # Early stop if requested number of roots reached
            if stop_after_roots > 0 and roots_found >= stop_after_roots:
                reached_root_quota = True
                break


        search_time = time.perf_counter() - search_t0
        total_time = time.perf_counter() - t0

        if roots_found > 0:
            if reached_root_quota:
                status_out = "OK_ROOTS"
                reason_out = "stop_on_root"
            else:
                status_out = "OK_ROOTS"
                reason_out = "completed"
            _write_progress(
                phase="finished",
                force=True,
                status_hint=status_out,
                stopped_reason_hint=reason_out,
            )
            write_output_file(
                out_path,
                fmt_version=fmt_version,
                run_id=run_id,
                id_line=id_line,
                s=s,
                p=p,
                N=N,
                sqrtN=sqrtN,
                Nmin=Nmin,
                Mmax=Mmax,
                W=W,
                depth=depth,
                timelimit_sec=timelimit_sec,
                status=status_out,
                stopped_reason=reason_out,
                roots_found=roots_found,
                fractions_tested=fractions_tested,
                unique_fractions=unique_fractions,
                build_time_sec=build_time,
                search_time_sec=_search_time_for_output(search_time),
                total_time_sec=total_time,
                rows=rows,
                emit_zero_row_on_timeout=emit_zero_row,
            )
            write_meta_file(
                meta_path,
                run_id=run_id,
                id_line=id_line,
                s=s,
                p=p,
                N=N,
                Nmin=Nmin,
                Mmax=Mmax,
                W=W,
                depth=depth,
                timelimit_sec=timelimit_sec,
                hard_timelimit=hard_timelimit,
                stop_after_roots=stop_after_roots,
                status=status_out,
                stopped_reason=reason_out,
                roots_found=roots_found,
                fractions_tested=fractions_tested,
                unique_fractions=unique_fractions,
                total_time_sec=total_time,
                last_fraction_started=last_fraction_started,
                last_level_started=last_level_started,
                last_fraction_new_root=last_fraction_new_root,
                last_level_new_root=last_level_new_root,
                traversal_mode=traversal_mode,
                level_only=effective_level_only,
                dummy_call_timeouts=dummy_call_timeouts,
            )
        else:
            # Completed with no roots (timelimit only stops early with --hard-timelimit
            # or when no roots and time exceeded).
            _write_progress(
                phase="finished",
                force=True,
                status_hint="TIMEOUT_NO_ROOTS",
                stopped_reason_hint="completed_no_roots",
            )
            write_output_file(
                out_path,
                fmt_version=fmt_version,
                run_id=run_id,
                id_line=id_line,
                s=s,
                p=p,
                N=N,
                sqrtN=sqrtN,
                Nmin=Nmin,
                Mmax=Mmax,
                W=W,
                depth=depth,
                timelimit_sec=timelimit_sec,
                status="TIMEOUT_NO_ROOTS",
                stopped_reason="completed_no_roots",
                roots_found=0,
                fractions_tested=fractions_tested,
                unique_fractions=unique_fractions,
                build_time_sec=build_time,
                search_time_sec=_search_time_for_output(search_time),
                total_time_sec=total_time,
                rows=None,
                emit_zero_row_on_timeout=emit_zero_row,
            )
            write_meta_file(
                meta_path,
                run_id=run_id,
                id_line=id_line,
                s=s,
                p=p,
                N=N,
                Nmin=Nmin,
                Mmax=Mmax,
                W=W,
                depth=depth,
                timelimit_sec=timelimit_sec,
                hard_timelimit=hard_timelimit,
                stop_after_roots=stop_after_roots,
                status="TIMEOUT_NO_ROOTS",
                stopped_reason="completed_no_roots",
                roots_found=0,
                fractions_tested=fractions_tested,
                unique_fractions=unique_fractions,
                total_time_sec=total_time,
                last_fraction_started=last_fraction_started,
                last_level_started=last_level_started,
                last_fraction_new_root=last_fraction_new_root,
                last_level_new_root=last_level_new_root,
                traversal_mode=traversal_mode,
                level_only=effective_level_only,
                dummy_call_timeouts=dummy_call_timeouts,
            )

    except Exception as e:
        total_time = time.perf_counter() - t0
        # If we failed early, these may not have been set
        last_fraction_started = locals().get('last_fraction_started', None)
        last_level_started = locals().get('last_level_started', None)
        last_fraction_new_root = locals().get('last_fraction_new_root', None)
        last_level_new_root = locals().get('last_level_new_root', None)
        build_time = time.perf_counter() - build_t0
        write_progress_file(
            progress_path,
            run_id=run_id,
            id_line=id_line,
            s=s,
            p=p,
            N=N,
            Nmin=Nmin,
            Mmax=Mmax,
            W=W,
            depth=depth,
            timelimit_sec=timelimit_sec,
            phase="finished",
            roots_found=0,
            fractions_tested=0,
            unique_fractions=0,
            elapsed_seconds=total_time,
            first_root_elapsed=None,
            last_fraction_started=last_fraction_started,
            last_level_started=last_level_started,
            last_fraction_new_root=last_fraction_new_root,
            last_level_new_root=last_level_new_root,
            status_hint="ERROR",
            stopped_reason_hint="error",
        )
        write_output_file(
            out_path,
            fmt_version=fmt_version,
            run_id=run_id,
            id_line=id_line,
            s=s,
            p=p,
            N=N,
            sqrtN=sqrtN,
            Nmin=Nmin,
            Mmax=Mmax,
            W=W,
            depth=depth,
            timelimit_sec=timelimit_sec,
            status="ERROR",
            stopped_reason="error",
            roots_found=0,
            fractions_tested=0,
            unique_fractions=0,
            build_time_sec=build_time,
            search_time_sec=0.0,
            total_time_sec=total_time,
            error_message=str(e),
            rows=None,
            emit_zero_row_on_timeout=emit_zero_row,
        )
        write_meta_file(
            meta_path,
            run_id=run_id,
            id_line=id_line,
            s=s,
            p=p,
            N=N,
            Nmin=Nmin,
            Mmax=Mmax,
            W=W,
            depth=depth,
            timelimit_sec=timelimit_sec,
            hard_timelimit=hard_timelimit,
            stop_after_roots=stop_after_roots,
            status="ERROR",
            stopped_reason="error",
            roots_found=0,
            fractions_tested=0,
            unique_fractions=0,
            total_time_sec=total_time,
            last_fraction_started=last_fraction_started,
            last_level_started=last_level_started,
            last_fraction_new_root=last_fraction_new_root,
            last_level_new_root=last_level_new_root,
            traversal_mode=traversal_mode,
            level_only=effective_level_only,
            dummy_call_timeouts=locals().get("dummy_call_timeouts", 0),
            error_message=str(e),
        )
    finally:
        dummy_runner.close()
        end_wall = time.time()
        end_stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_wall))
        run_time = end_wall - start_wall
        print(
            f"Exp id={id_line}, s={s}, End time={end_stamp}, run time={run_time:.3f}s",
            flush=True,
        )


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Batch CLI runner for Nikos Fractions root experiments"
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
        type=int,
        nargs="?",
        const=1,
        default=0,
        help="Stop after finding this many roots (default: 0 = do not stop early). If provided with no value, defaults to 1.",
    )
    parser.add_argument(
        "--hard-timelimit",
        dest="hard_timelimit",
        action="store_true",
        default=True,
        help="Always stop when timelimit_sec is exceeded (default: true)",
    )
    parser.add_argument(
        "--soft-timelimit",
        dest="hard_timelimit",
        action="store_false",
        help="Allow running past timelimit once roots are found (legacy behavior)",
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
        help="Use streaming BFS traversal (level-by-level). This is the default behavior.",
    )
    parser.add_argument(
        "--level-only",
        type=int,
        default=None,
        metavar="L",
        help="Enumerate and test only level L using O(L) path memory.",
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
        help="Emit a lightweight heartbeat every N tested fractions (0=disabled).",
    )

    args = parser.parse_args(argv[1:])

    params_path = args.par
    primes_path = args.sp
    out_dir = args.out
    traversal_mode = "streaming-bfs"
    if args.streaming_bfs:
        traversal_mode = "streaming-bfs"
    if args.level_only is not None and args.level_only < 1:
        raise ValueError("--level-only must be >= 1")
    if args.heartbeat_every < 0:
        raise ValueError("--heartbeat-every must be >= 0")

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
    for (id_line, params) in experiments:
        for (s, p) in primes:
            print(
                f"Starting experiment id={id_line} s={s} p={p} "
                f"params=Nmin:{params[0]} Mmax:{params[1]} W:{params[2]} "
                f"depth:{params[3]} timelimit_sec:{params[4]}",
                flush=True,
            )
            run_one_experiment(
                id_line=id_line,
                params=params,
                s=s,
                p=p,
                out_dir=out_dir,
                emit_zero_row=not args.no_zero_row,
                stop_after_roots=args.stop_on_root,
                hard_timelimit=args.hard_timelimit,
                fmt_version=args.format,
                traversal_mode=traversal_mode,
                level_only=args.level_only,
                strict_level_only=args.strict_level_only,
                heartbeat_every=args.heartbeat_every,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
