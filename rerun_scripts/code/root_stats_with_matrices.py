#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
root_stats.py

Compute statistics about "root-generating fractions" from run_experiments_cli_streaming_rootsN outputs.

Input:
  - result_*_*.out.txt files (format_version=1 as in your examples)
  - (optional) matching .meta.txt files

Outputs (CSV):
  1) <prefix>_fraction_events.csv
     One row per root event (one line in .out.txt)
  2) <prefix>_per_run_fraction_stats.csv
     Per (run_id, frac_n/frac_d): event counts, levels, distinct roots
  3) <prefix>_run_summary.csv
     Per run_id: timelimit, W, depth, fractions_tested, roots_found, distinct root-fractions, etc.
  4) <prefix>_per_sp_fraction_stats.csv
     Per (s,p, frac_n/frac_d): support across ids, min/max/mean level, event counts, distinct roots
  5) <prefix>_per_sp_classification.csv
     Core/derived classification per (s,p, frac)
  6) <prefix>_support_histogram.csv
     For each (s,p): how many fractions appear in exactly k ids
  7) <prefix>_core_summary.csv
     For each (s,p): counts of core/derived + ratios
  8) For each input result_...out.txt:
     writes sibling result_...ext.txt with extra columns:
       - after aF: aF_red_num, aF_red_den, aF_gcd
       - after bF: bF_abs_red_num, bF_abs_red_den, bF_abs_gcd,
         bF_abs_red_num_coef_s, bF_abs_red_num_coef_p

Core definition (editable via CLI):
  - support_ids >= K_CORE
  - min_level <= L_CORE
  - denom <= D_CORE

Derived:
  - root-generating but not core

Noise:
  - not root-generating (not present in .out rows).
    NOTE: true "noise rate" requires logging tested fractions too; outputs only contain root events.

Usage:
  python3 root_stats.py --input-dir ./exp_10 --out-prefix stats_exp10
  python3 root_stats.py --input-dir . --glob-out "result_*_*.out.txt"
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import pandas as pd


def parse_meta(path: Path) -> dict:
    d: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()

    # best-effort typing
    for k in (
        "id", "s", "p", "N", "Nmin", "Mmax", "W", "depth", "timelimit_sec",
        "stop_after_roots", "roots_found", "fractions_tested", "unique_fractions"
    ):
        if k in d:
            try:
                d[k] = int(d[k])
            except Exception:
                pass
    if "elapsed_seconds" in d:
        try:
            d["elapsed_seconds"] = float(d["elapsed_seconds"])
        except Exception:
            pass
    if "hard_timelimit" in d:
        d["hard_timelimit"] = str(d["hard_timelimit"]).lower() == "true"
    return d


def _find_out_header(lines: list[str], path: Path) -> tuple[int, list[str], bool]:
    col_line_idx = None
    cols = None
    had_columns_prefix = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("COLUMNS "):
            col_line_idx = i
            cols = s.split()[1:]  # old format: drop 'COLUMNS'
            had_columns_prefix = True
            break
        # new format: plain header line starting with column names
        toks = s.split()
        if "run_id" in toks and "root_x" in toks:
            col_line_idx = i
            cols = toks
            had_columns_prefix = False
            break
    if col_line_idx is None or not cols:
        raise ValueError(f"No column header line found in {path}")
    return col_line_idx, cols, had_columns_prefix


def _parse_fraction_token(token: str) -> tuple[int, int]:
    s = token.strip()
    if "/" in s:
        n_s, d_s = s.split("/", 1)
        n = int(n_s)
        d = int(d_s)
    else:
        n = int(s)
        d = 1
    if d == 0:
        raise ZeroDivisionError(f"Zero denominator in fraction token {token!r}")
    if d < 0:
        n = -n
        d = -d
    return n, d


def _reduce_fraction(n: int, d: int) -> tuple[int, int, int]:
    g = math.gcd(abs(n), abs(d))
    if g == 0:
        g = 1
    return n // g, d // g, g


def _extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    """
    Return (g, x, y) such that a*x + b*y = g = gcd(a,b).
    """
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t
    if old_r < 0:
        old_r, old_s, old_t = -old_r, -old_s, -old_t
    return old_r, old_s, old_t


def _linear_combo_coeffs(target: int, a: int, b: int) -> tuple[int | None, int | None]:
    """
    Find an integer solution (u, v) to target = u*a + v*b with small coefficients.
    Among all integer solutions, choose the one minimizing u^2 + v^2
    (Euclidean norm), with deterministic tie-breakers.
    Returns (None, None) if no integer solution exists.
    """
    g, x0, y0 = _extended_gcd(a, b)
    if g == 0:
        return (0, 0) if target == 0 else (None, None)
    if target % g != 0:
        return (None, None)
    k = target // g
    u0 = x0 * k
    v0 = y0 * k

    # General solution:
    #   u = u0 + (b/g) * t
    #   v = v0 - (a/g) * t
    step_u = b // g
    step_v = a // g
    A = step_u * step_u + step_v * step_v
    if A == 0:
        return u0, v0

    # Minimize quadratic f(t)=u(t)^2+v(t)^2.
    # Real minimizer: t* = -(u0*step_u - v0*step_v) / A
    num = -(u0 * step_u - v0 * step_v)
    t_floor = num // A
    candidates = {t_floor - 1, t_floor, t_floor + 1, t_floor + 2}

    best_u, best_v = None, None
    best_score = None
    for t in candidates:
        u = u0 + step_u * t
        v = v0 - step_v * t
        score = (
            u * u + v * v,           # primary: minimal Euclidean norm
            abs(u) + abs(v),         # tie-break 1
            max(abs(u), abs(v)),     # tie-break 2
            abs(u),                  # tie-break 3
            abs(v),                  # tie-break 4
        )
        if best_score is None or score < best_score:
            best_score = score
            best_u, best_v = u, v

    return best_u, best_v


def _parse_sp_from_run_id(run_id_token: str) -> tuple[int | None, int | None]:
    """
    Parse run_id token with expected form id:s:p and return (s,p).
    """
    parts = run_id_token.split(":")
    if len(parts) >= 3:
        try:
            return int(parts[-2]), int(parts[-1])
        except Exception:
            return None, None
    return None, None


def write_extended_out_file(path: Path) -> Path | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    col_line_idx, cols, had_columns_prefix = _find_out_header(lines, path)
    if "aF" not in cols or "bF" not in cols:
        return None

    new_cols: list[str] = []
    for c in cols:
        new_cols.append(c)
        if c == "aF":
            new_cols.extend(["aF_red_num", "aF_red_den", "aF_gcd"])
        if c == "bF":
            new_cols.extend(
                [
                    "bF_abs_red_num",
                    "bF_abs_red_den",
                    "bF_abs_gcd",
                    "bF_abs_red_num_coef_s",
                    "bF_abs_red_num_coef_p",
                ]
            )

    out_path = path.with_name(path.name.replace(".out.txt", ".ext.txt"))
    if out_path == path:
        out_path = path.with_suffix(path.suffix + ".ext")

    out_lines: list[str] = []
    out_lines.extend(lines[:col_line_idx])
    header = " ".join(new_cols)
    if had_columns_prefix:
        header = "COLUMNS " + header
    out_lines.append(header)

    for raw in lines[col_line_idx + 1 :]:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            out_lines.append(raw)
            continue
        parts = s.split()
        if len(parts) != len(cols):
            raise ValueError(
                f"Data row token mismatch in {path}: expected {len(cols)} tokens, got {len(parts)} in row: {raw}"
            )

        out_row: list[str] = []
        run_id_token = parts[cols.index("run_id")] if "run_id" in cols else ""
        s_val, p_val = _parse_sp_from_run_id(run_id_token)
        for c, v in zip(cols, parts):
            out_row.append(v)
            if c == "aF":
                an, ad = _parse_fraction_token(v)
                an_r, ad_r, ag = _reduce_fraction(an, ad)
                out_row.extend([str(an_r), str(ad_r), str(ag)])
            if c == "bF":
                bn, bd = _parse_fraction_token(v)
                bn = abs(bn)
                bn_r, bd_r, bg = _reduce_fraction(bn, bd)
                coef_s: str
                coef_p: str
                if s_val is None or p_val is None:
                    coef_s, coef_p = "NA", "NA"
                else:
                    u, w = _linear_combo_coeffs(bn_r, s_val, p_val)
                    if u is None or w is None:
                        coef_s, coef_p = "NA", "NA"
                    else:
                        coef_s, coef_p = str(u), str(w)
                out_row.extend([str(bn_r), str(bd_r), str(bg), coef_s, coef_p])

        out_lines.append(" ".join(out_row))

    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return out_path


def parse_out(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8").splitlines()
    col_line_idx, cols, _had_columns_prefix = _find_out_header(lines, path)

    data_lines = [ln for ln in lines[col_line_idx + 1 :] if ln.strip() and not ln.lstrip().startswith("#")]
    from io import StringIO
    buf = StringIO("\n".join(data_lines))
    df = pd.read_csv(buf, sep=r"\s+", names=cols, engine="python")
    df["source_file"] = str(path)
    return df


def frac_str(n: int, d: int) -> str:
    return f"{int(n)}/{int(d)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compute fraction/root statistics from .out/.meta files")
    ap.add_argument("--input-dir", default=".", help="Directory to search for result files")
    ap.add_argument("--glob-out", default="**/result_*_*_*.out.txt", help="Glob for .out files (relative to input-dir)")
    ap.add_argument("--glob-meta", default="**/result_*_*_*.meta.txt", help="Glob for .meta files (relative to input-dir)")
    ap.add_argument("--out-prefix", default="stats", help="Prefix for output CSV files")
    ap.add_argument("--emit-matrices", action="store_true",
                    help="Write per-(s,p) fraction-by-id count matrices as CSV")
    ap.add_argument("--matrices-dir", default=None,
                    help="Output directory for matrices (default: <out-prefix>_matrices)")

    ap.add_argument("--k-core", type=int, default=2, help="Core support threshold: appear in >=k ids (default: 2)")
    ap.add_argument("--l-core", type=int, default=3, help="Core max min_level threshold (default: 3)")
    ap.add_argument("--d-core", type=int, default=500, help="Core max denominator threshold (default: 500)")

    args = ap.parse_args(argv)

    base = Path(args.input_dir)
    out_paths = sorted(base.glob(args.glob_out))
    if not out_paths:
        raise SystemExit(f"No .out files found under {base} with glob {args.glob_out!r}")

    meta_map: dict[str, dict] = {}
    for mp in base.glob(args.glob_meta):
        md = parse_meta(mp)
        run_id = str(md.get("run_id", ""))
        if run_id:
            meta_map[run_id] = md

    dfs = []
    ext_written = 0
    for op in out_paths:
        ext_path = write_extended_out_file(op)
        if ext_path is not None:
            ext_written += 1
        df = parse_out(op)
        run_id = str(df["run_id"].iloc[0])
        if run_id in meta_map:
            md = meta_map[run_id]
            parts = run_id.split(":")
            df["id"] = int(md.get("id", parts[0]))
            df["s"] = int(md.get("s", parts[1]))
            df["p"] = int(md.get("p", parts[2]))
            df["W"] = int(md.get("W", -1))
            df["depth_max"] = int(md.get("depth", -1))
            df["timelimit_sec"] = int(md.get("timelimit_sec", -1))
        else:
            parts = run_id.split(":")
            df["id"] = int(parts[0])
            df["s"] = int(parts[1])
            df["p"] = int(parts[2])
            df["W"] = -1
            df["depth_max"] = -1
            df["timelimit_sec"] = -1

        df["frac"] = df.apply(lambda r: frac_str(r["frac_n"], r["frac_d"]), axis=1)
        dfs.append(df)

    events = pd.concat(dfs, ignore_index=True)
    events["root_x"] = events["root_x"].astype(str)

    # Write raw events
    out_prefix = args.out_prefix
    events_out = f"{out_prefix}_fraction_events.csv"
    events.to_csv(events_out, index=False)

    # Per-run per-fraction stats
    per_run_frac = (
        events
        .groupby(["run_id","id","s","p","W","depth_max","timelimit_sec","frac_n","frac_d","frac"], as_index=False)
        .agg(
            root_events=("root_idx","count"),
            distinct_roots=("root_x", pd.Series.nunique),
            min_level=("level","min"),
            max_level=("level","max"),
            mean_level=("level","mean"),
        )
    )
    per_run_frac_out = f"{out_prefix}_per_run_fraction_stats.csv"
    per_run_frac.to_csv(per_run_frac_out, index=False)

    # Run summary
    run_sum = (
        events
        .groupby(["run_id","id","s","p","W","depth_max","timelimit_sec"], as_index=False)
        .agg(
            root_events=("root_idx","count"),
            distinct_roots=("root_x", pd.Series.nunique),
            distinct_root_fractions=("frac", pd.Series.nunique),
            min_level=("level","min"),
            max_level=("level","max"),
            max_denom=("frac_d","max"),
        )
    )
    if meta_map:
        md_df = pd.DataFrame([{"run_id": rid, **md} for rid, md in meta_map.items()]).drop_duplicates(subset=["run_id"])
        keep = [c for c in ["run_id","status","stopped_reason","elapsed_seconds","fractions_tested","unique_fractions","Mmax","Nmin","N","hard_timelimit","stop_after_roots"] if c in md_df.columns]
        run_sum = run_sum.merge(md_df[keep], on="run_id", how="left")
    run_sum_out = f"{out_prefix}_run_summary.csv"
    run_sum.to_csv(run_sum_out, index=False)

    # Per (s,p, frac) across ids
    per_sp_frac = (
        events
        .groupby(["s","p","frac_n","frac_d","frac"], as_index=False)
        .agg(
            support_ids=("id", pd.Series.nunique),
            ids_list=("id", lambda x: ",".join(map(str, sorted(set(map(int, x)))))),
            root_events=("root_idx","count"),
            distinct_roots=("root_x", pd.Series.nunique),
            min_level=("level","min"),
            max_level=("level","max"),
            mean_level=("level","mean"),
            min_W=("W","min"),
            max_W=("W","max"),
            min_depth_max=("depth_max","min"),
            max_depth_max=("depth_max","max"),
        )
    )
    per_sp_frac_out = f"{out_prefix}_per_sp_fraction_stats.csv"
    per_sp_frac.to_csv(per_sp_frac_out, index=False)

    # Classification: core vs derived
    K_CORE = args.k_core
    L_CORE = args.l_core
    D_CORE = args.d_core

    per_sp_class = per_sp_frac.copy()
    per_sp_class["is_core"] = (
        (per_sp_class["support_ids"] >= K_CORE)
        & (per_sp_class["min_level"] <= L_CORE)
        & (per_sp_class["frac_d"] <= D_CORE)
    )
    per_sp_class["is_derived"] = ~per_sp_class["is_core"]

    per_sp_class_out = f"{out_prefix}_per_sp_classification.csv"
    per_sp_class.to_csv(per_sp_class_out, index=False)

    # Support histogram per (s,p)
    support_hist = (
        per_sp_frac
        .groupby(["s","p","support_ids"], as_index=False)
        .agg(num_fractions=("frac","count"))
        .sort_values(["s","p","support_ids"])
    )
    support_hist_out = f"{out_prefix}_support_histogram.csv"
    support_hist.to_csv(support_hist_out, index=False)

    # Core summary per (s,p)
    core_summary = (
        per_sp_class
        .groupby(["s","p"], as_index=False)
        .agg(
            num_root_fractions=("frac","count"),
            num_core_fractions=("is_core","sum"),
        )
    )
    core_summary["num_derived_fractions"] = core_summary["num_root_fractions"] - core_summary["num_core_fractions"]
    core_summary["core_fraction_ratio"] = core_summary["num_core_fractions"] / core_summary["num_root_fractions"].where(core_summary["num_root_fractions"] != 0, 1)
    core_summary_out = f"{out_prefix}_core_summary.csv"
    core_summary.to_csv(core_summary_out, index=False)

    print(f"Wrote: {events_out}")
    print(f"Wrote: {per_run_frac_out}")
    print(f"Wrote: {run_sum_out}")
    print(f"Wrote: {per_sp_frac_out}")
    print(f"Wrote: {per_sp_class_out}")
    print(f"Wrote: {support_hist_out}")
    print(f"Wrote: {core_summary_out}")
    print(f"Wrote extended result files (.ext.txt): {ext_written}")

    # Optional: per-(s,p) pivot matrix with rows=(frac_n,frac_d) and columns=id, cells=event counts
    if args.emit_matrices:
        mdir = Path(args.matrices_dir) if args.matrices_dir else Path(f"{out_prefix}_matrices")
        mdir.mkdir(parents=True, exist_ok=True)

        for (s, p_) in events.groupby(["s", "p"]).groups.keys():
            g = events[(events["s"] == s) & (events["p"] == p_)]
            mat = (
                g.pivot_table(
                    index=["frac_n", "frac_d"],
                    columns="id",
                    values="root_idx",
                    aggfunc="count",
                    fill_value=0,
                )
                .astype(int)
                .reset_index()
                .sort_values(["frac_d", "frac_n"])
            )
            # add total column (sum across ids)
            id_cols = [c for c in mat.columns if c not in ["frac_n", "frac_d"]]
            mat["total"] = mat[id_cols].sum(axis=1)

            out_path = mdir / f"matrix_s{int(s)}_p{int(p_)}.csv"
            mat.to_csv(out_path, index=False)

        print(f"Wrote matrices to: {mdir}")

    # Quick core list per (s,p)
    core_only = per_sp_class[per_sp_class["is_core"]].copy()
    if not core_only.empty:
        for (s, p_) in core_only.groupby(["s","p"]).groups.keys():
            sub = core_only[(core_only["s"] == s) & (core_only["p"] == p_)].sort_values(["frac_d","frac_n"])
            fracs = ", ".join(sub["frac"].tolist()[:25])
            print(f"[CORE] s={s} p={p_}: {fracs}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
