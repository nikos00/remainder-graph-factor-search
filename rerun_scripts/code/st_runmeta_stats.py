#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, List, Optional, Set, Tuple


def parse_int(v: Optional[str]) -> Optional[int]:
    s = (v or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def parse_float(v: Optional[str]) -> Optional[float]:
    s = (v or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def first_nonempty(md: Dict[str, str], keys: List[str]) -> str:
    for k in keys:
        v = (md.get(k) or "").strip()
        if v:
            return v
    return ""


def mean(vals: List[float]) -> float:
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def cf_terms_count(frac_str: str) -> Optional[int]:
    s = (frac_str or "").strip()
    if not s or s.lower() == "none" or s == "-":
        return None
    try:
        if "/" in s:
            a, b = s.split("/", 1)
            q = Fraction(int(a), int(b))
        else:
            q = Fraction(int(s), 1)
    except Exception:
        return None
    if q.denominator == 0:
        return None
    x = abs(q.numerator)
    y = q.denominator
    cnt = 0
    while y != 0:
        x, y = y, x % y
        cnt += 1
    return cnt


def extract_exp_tag(rel_path: str, default_tag: str) -> str:
    parts = rel_path.split(os.sep)
    exp_parts = [p for p in parts if p.startswith("exp_")]
    if exp_parts:
        return exp_parts[-1]
    parent = os.path.dirname(rel_path)
    if parent and parent != ".":
        return parent.split(os.sep)[0]
    return default_tag


def parse_meta_lines(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                body = line[1:].strip()
                if "=" in body:
                    k, v = body.split("=", 1)
                    out[k.strip()] = v.strip()
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
                continue
    return out


def derive_from_result_filename(path: str) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    base = os.path.basename(path)
    m = re.match(r"^result_(\d+)_(\d+)_(\d+)\.(?:out|meta|progress|ext)\.txt$", base)
    if not m:
        return None, None, None, None
    s = int(m.group(1))
    p = int(m.group(2))
    run_idx = int(m.group(3))
    run_id = f"{run_idx}:{s}:{p}"
    return run_id, s, p, s * p


def derive_from_roots_filename(path: str) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    base = os.path.basename(path)

    m = re.match(r"^roots_+(\d+)_(\d+)_([0-9]{8}_[0-9]{6})(?:.*)\.csv$", base)
    if m:
        s = int(m.group(1))
        p = int(m.group(2))
        stamp = m.group(3)
        return f"roots:{stamp}:{s}:{p}", s, p, s * p

    m2 = re.match(r"^roots_+(\d+)_(\d+)(?:_.*)?\.csv$", base)
    if m2:
        s = int(m2.group(1))
        p = int(m2.group(2))
        stem = os.path.splitext(base)[0]
        return f"roots:{stem}:{s}:{p}", s, p, s * p

    return None, None, None, None


def file_rank(path: str) -> int:
    b = os.path.basename(path)
    if b.endswith(".meta.txt"):
        return 50
    if b.endswith(".out.txt") or b.endswith(".ext.txt"):
        return 40
    if b.endswith(".progress.txt"):
        return 30
    if re.match(r"^roots_+.*\.csv$", b):
        return 20
    return 10


def parse_prefixed_meta(path: str, max_lines: int = 30) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f, 1):
            if i > max_lines:
                break
            line = raw.strip()
            if not line.startswith("#"):
                continue
            body = line[1:].strip()
            if "=" in body:
                k, v = body.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def parse_roots_csv(path: str) -> Tuple[Dict[str, str], int, int, Optional[int], str]:
    meta: Dict[str, str] = {}
    rows_with_roots = 0
    fracs_seen: Set[str] = set()
    max_terms_seen: Optional[int] = None
    last_fraction_seen = ""

    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        row1 = next(reader, None)
        row2 = next(reader, None)
        if row1 and row2 and len(row1) == len(row2):
            for k, v in zip(row1, row2):
                kk = (k or "").strip()
                vv = (v or "").strip()
                if kk:
                    meta[kk] = vv

        header = next(reader, None)
        if not header:
            return meta, rows_with_roots, 0, max_terms_seen, last_fraction_seen

        header_lc = [str(h or "").strip().lower() for h in header]
        idx_frac_n = header_lc.index("frac_n") if "frac_n" in header_lc else -1
        idx_frac_d = header_lc.index("frac_d") if "frac_d" in header_lc else -1
        idx_af = header_lc.index("af") if "af" in header_lc else -1

        for row in reader:
            if not row:
                continue
            if not any((c or "").strip() for c in row):
                continue
            rows_with_roots += 1

            frac = ""
            if idx_frac_n >= 0 and idx_frac_d >= 0 and len(row) > max(idx_frac_n, idx_frac_d):
                n = parse_int(row[idx_frac_n])
                d = parse_int(row[idx_frac_d])
                if n is not None and d not in (None, 0):
                    try:
                        q = Fraction(n, d)
                        frac = f"{q.numerator}/{q.denominator}"
                    except Exception:
                        frac = ""
            if not frac and idx_af >= 0 and len(row) > idx_af:
                af = (row[idx_af] or "").strip()
                if af:
                    frac = af

            if frac:
                fracs_seen.add(frac)
                last_fraction_seen = frac
                terms = cf_terms_count(frac)
                if terms is not None:
                    max_terms_seen = terms if max_terms_seen is None else max(max_terms_seen, terms)

    return meta, rows_with_roots, len(fracs_seen), max_terms_seen, last_fraction_seen


@dataclass
class RunRecord:
    run_id: str
    source_file: str
    exp_tag: str
    source_rank: int
    source_kind: str

    s: Optional[int] = None
    p: Optional[int] = None
    n_value: Optional[int] = None
    dec_digits: Optional[int] = None

    status: str = ""
    stopped_reason: str = ""
    runtime_sec: Optional[float] = None
    fractions_tested: Optional[int] = None
    last_fraction_started: str = ""
    last_fraction_terms: Optional[int] = None
    last_level_started: Optional[int] = None
    rows_with_roots: Optional[int] = None
    unique_fractions_with_roots: Optional[int] = None
    max_fraction_terms_seen_in_roots: Optional[int] = None
    last_fraction_seen_in_roots: str = ""


def merge_record(base: Optional[RunRecord], cand: RunRecord) -> RunRecord:
    if base is None:
        return cand

    choose = cand.source_rank > base.source_rank
    if choose:
        primary = cand
        secondary = base
    else:
        primary = base
        secondary = cand

    merged = RunRecord(
        run_id=primary.run_id,
        source_file=primary.source_file,
        exp_tag=primary.exp_tag,
        source_rank=max(base.source_rank, cand.source_rank),
        source_kind=primary.source_kind,
    )

    for field in ("s", "p", "n_value", "dec_digits", "status", "stopped_reason",
                  "runtime_sec", "fractions_tested", "last_fraction_started",
                  "last_fraction_terms", "last_level_started",
                  "rows_with_roots", "unique_fractions_with_roots",
                  "max_fraction_terms_seen_in_roots", "last_fraction_seen_in_roots"):
        a = getattr(primary, field)
        b = getattr(secondary, field)
        if a is not None and a != "":
            setattr(merged, field, a)
        else:
            setattr(merged, field, b)

    # If both have numeric values, keep max for these progress-like metrics.
    if base.runtime_sec is not None and cand.runtime_sec is not None:
        merged.runtime_sec = max(base.runtime_sec, cand.runtime_sec)
    if base.fractions_tested is not None and cand.fractions_tested is not None:
        merged.fractions_tested = max(base.fractions_tested, cand.fractions_tested)
    if base.last_level_started is not None and cand.last_level_started is not None:
        merged.last_level_started = max(base.last_level_started, cand.last_level_started)
    if base.last_fraction_terms is not None and cand.last_fraction_terms is not None:
        merged.last_fraction_terms = max(base.last_fraction_terms, cand.last_fraction_terms)
    if base.rows_with_roots is not None and cand.rows_with_roots is not None:
        merged.rows_with_roots = max(base.rows_with_roots, cand.rows_with_roots)
    if base.unique_fractions_with_roots is not None and cand.unique_fractions_with_roots is not None:
        merged.unique_fractions_with_roots = max(base.unique_fractions_with_roots, cand.unique_fractions_with_roots)
    if base.max_fraction_terms_seen_in_roots is not None and cand.max_fraction_terms_seen_in_roots is not None:
        merged.max_fraction_terms_seen_in_roots = max(
            base.max_fraction_terms_seen_in_roots, cand.max_fraction_terms_seen_in_roots
        )

    return merged


def build_candidate_result(path: str, rel_path: str, default_tag: str) -> Optional[RunRecord]:
    md = parse_meta_lines(path)
    rid_f, s_f, p_f, n_f = derive_from_result_filename(path)

    run_id = (md.get("run_id") or "").strip() or (rid_f or "")
    if not run_id:
        return None

    s = parse_int(md.get("s")) if md.get("s") else None
    p = parse_int(md.get("p")) if md.get("p") else None
    n_value = parse_int(md.get("N")) if md.get("N") else None

    if s is None:
        s = s_f
    if p is None:
        p = p_f
    if n_value is None:
        if n_f is not None:
            n_value = n_f
        elif s is not None and p is not None:
            n_value = s * p

    runtime = None
    runtime_s = first_nonempty(md, [
        "total_time_sec", "elapsed_seconds", "search_time_sec", "runtime_sec", "time_sec"
    ])
    if runtime_s:
        runtime = parse_float(runtime_s)

    fractions_tested = parse_int(first_nonempty(md, ["fractions_tested", "tested_fractions", "fractions_count"]))
    last_fraction_started = first_nonempty(md, ["last_fraction_started", "last_fraction"])
    last_level_started = parse_int(first_nonempty(md, ["last_level_started", "last_level"]))
    terms = cf_terms_count(last_fraction_started)

    return RunRecord(
        run_id=run_id,
        source_file=rel_path,
        exp_tag=extract_exp_tag(rel_path, default_tag),
        source_rank=file_rank(path),
        source_kind="result_txt",
        s=s,
        p=p,
        n_value=n_value,
        dec_digits=(len(str(n_value)) if n_value is not None else None),
        status=(first_nonempty(md, ["status", "phase"])),
        stopped_reason=(md.get("stopped_reason") or "").strip(),
        runtime_sec=runtime,
        fractions_tested=fractions_tested,
        last_fraction_started=last_fraction_started,
        last_fraction_terms=terms,
        last_level_started=last_level_started,
    )


def build_candidate_roots(path: str, rel_path: str, default_tag: str) -> Optional[RunRecord]:
    md_pref = parse_prefixed_meta(path)
    md_top, rows_with_roots, uniq_fracs, max_terms_seen, last_frac_seen = parse_roots_csv(path)
    md = dict(md_top)
    md.update(md_pref)

    rid_f, s_f, p_f, n_f = derive_from_roots_filename(path)
    run_id = first_nonempty(md, ["run_id"]) or rid_f or os.path.splitext(os.path.basename(path))[0]

    s = parse_int(first_nonempty(md, ["s"]))
    p = parse_int(first_nonempty(md, ["p"]))
    n_value = parse_int(first_nonempty(md, ["N", "n_value"]))
    if s is None:
        s = s_f
    if p is None:
        p = p_f
    if n_value is None:
        if n_f is not None:
            n_value = n_f
        elif s is not None and p is not None:
            n_value = s * p

    runtime_s = first_nonempty(md, [
        "total_time_sec", "elapsed_seconds", "search_time_sec", "runtime_sec", "time_sec"
    ])
    runtime = parse_float(runtime_s) if runtime_s else None

    fractions_tested = parse_int(first_nonempty(md, ["fractions_tested", "tested_fractions", "fractions_count"]))
    last_fraction_started = first_nonempty(md, ["last_fraction_started", "last_fraction"])
    last_level_started = parse_int(first_nonempty(md, ["last_level_started", "last_level"]))
    last_terms = cf_terms_count(last_fraction_started)

    return RunRecord(
        run_id=run_id,
        source_file=rel_path,
        exp_tag=extract_exp_tag(rel_path, default_tag),
        source_rank=file_rank(path),
        source_kind="roots_csv",
        s=s,
        p=p,
        n_value=n_value,
        dec_digits=(len(str(n_value)) if n_value is not None else None),
        status=first_nonempty(md, ["status", "phase"]),
        stopped_reason=first_nonempty(md, ["stopped_reason", "reason"]),
        runtime_sec=runtime,
        fractions_tested=fractions_tested,
        last_fraction_started=last_fraction_started,
        last_fraction_terms=last_terms,
        last_level_started=last_level_started,
        rows_with_roots=rows_with_roots,
        unique_fractions_with_roots=uniq_fracs,
        max_fraction_terms_seen_in_roots=max_terms_seen,
        last_fraction_seen_in_roots=last_frac_seen,
    )


def collect_files(folder: str) -> List[str]:
    rx_result = re.compile(r"^result_.*\.(meta|out|progress|ext)\.txt$")
    rx_roots = re.compile(r"^roots_+.*\.csv$")
    out: List[str] = []
    for root, _dirs, names in os.walk(folder):
        for fn in names:
            if rx_result.match(fn) or rx_roots.match(fn):
                out.append(os.path.join(root, fn))
    out.sort()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Aggregate run metadata stats: mean runtime, mean fractions tested, "
            "max fraction-term count, max last_level_started."
        )
    )
    ap.add_argument("folder", nargs="?", default=".", help="Root folder (recursive)")
    ap.add_argument("--out_runs", default="stats_runmeta_by_run.csv", help="Per-run output CSV")
    ap.add_argument("--out_digits", default="stats_runmeta_by_digits.csv", help="Grouped by N digits")
    ap.add_argument("--out_exp", default="stats_runmeta_by_experiment.csv", help="Grouped by experiment tag")
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    default_tag = os.path.basename(folder.rstrip(os.sep)) or "root"
    files = collect_files(folder)
    if not files:
        raise SystemExit(f"No result_*.txt or roots_*.csv files found under {folder}")

    runs: Dict[str, RunRecord] = {}
    for path in files:
        rel = os.path.relpath(path, folder)
        base = os.path.basename(path)
        if base.startswith("result_") and base.endswith((".meta.txt", ".out.txt", ".progress.txt", ".ext.txt")):
            cand = build_candidate_result(path, rel, default_tag)
        elif base.startswith("roots_") and base.endswith(".csv"):
            cand = build_candidate_roots(path, rel, default_tag)
        else:
            cand = None
        if cand is None:
            continue
        runs[cand.run_id] = merge_record(runs.get(cand.run_id), cand)

    run_list = sorted(runs.values(), key=lambda r: (r.dec_digits or -1, r.s or -1, r.p or -1, r.run_id))

    out_runs = os.path.join(folder, args.out_runs)
    out_digits = os.path.join(folder, args.out_digits)
    out_exp = os.path.join(folder, args.out_exp)

    with open(out_runs, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "run_id", "source_file", "exp_tag", "source_kind", "s", "p", "N", "dec_digits",
            "status", "stopped_reason",
            "runtime_sec", "fractions_tested",
            "last_fraction_started", "last_fraction_terms", "last_level_started",
            "rows_with_roots", "unique_fractions_with_roots",
            "max_fraction_terms_seen_in_roots", "last_fraction_seen_in_roots",
        ])
        for r in run_list:
            w.writerow([
                r.run_id, r.source_file, r.exp_tag, r.source_kind,
                r.s if r.s is not None else "",
                r.p if r.p is not None else "",
                r.n_value if r.n_value is not None else "",
                r.dec_digits if r.dec_digits is not None else "",
                r.status, r.stopped_reason,
                f"{r.runtime_sec:.6f}" if r.runtime_sec is not None else "",
                r.fractions_tested if r.fractions_tested is not None else "",
                r.last_fraction_started,
                r.last_fraction_terms if r.last_fraction_terms is not None else "",
                r.last_level_started if r.last_level_started is not None else "",
                r.rows_with_roots if r.rows_with_roots is not None else "",
                r.unique_fractions_with_roots if r.unique_fractions_with_roots is not None else "",
                r.max_fraction_terms_seen_in_roots if r.max_fraction_terms_seen_in_roots is not None else "",
                r.last_fraction_seen_in_roots,
            ])

    by_digits: Dict[int, List[RunRecord]] = defaultdict(list)
    for r in run_list:
        if r.dec_digits is not None:
            by_digits[r.dec_digits].append(r)

    with open(out_digits, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "dec_digits",
            "runs",
            "mean_runtime_sec",
            "mean_fractions_tested",
            "max_last_fraction_terms",
            "max_last_level_started",
            "runtime_samples",
            "fractions_tested_samples",
            "last_fraction_terms_samples",
            "last_level_samples",
            "mean_fractions_with_roots",
            "max_fraction_terms_seen_in_roots",
        ])
        for d in sorted(by_digits):
            grp = by_digits[d]
            runt = [r.runtime_sec for r in grp if r.runtime_sec is not None]
            frac = [float(r.fractions_tested) for r in grp if r.fractions_tested is not None]
            terms = [r.last_fraction_terms for r in grp if r.last_fraction_terms is not None]
            lvl = [r.last_level_started for r in grp if r.last_level_started is not None]
            uniq = [float(r.unique_fractions_with_roots) for r in grp if r.unique_fractions_with_roots is not None]
            seen_terms = [r.max_fraction_terms_seen_in_roots for r in grp if r.max_fraction_terms_seen_in_roots is not None]
            w.writerow([
                d,
                len(grp),
                f"{mean(runt):.6f}" if runt else "",
                f"{mean(frac):.6f}" if frac else "",
                max(terms) if terms else "",
                max(lvl) if lvl else "",
                len(runt),
                len(frac),
                len(terms),
                len(lvl),
                f"{mean(uniq):.6f}" if uniq else "",
                max(seen_terms) if seen_terms else "",
            ])

    by_exp: Dict[str, List[RunRecord]] = defaultdict(list)
    for r in run_list:
        by_exp[r.exp_tag].append(r)

    with open(out_exp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "experiment",
            "runs",
            "mean_runtime_sec",
            "mean_fractions_tested",
            "max_last_fraction_terms",
            "max_last_level_started",
            "runtime_samples",
            "fractions_tested_samples",
            "last_fraction_terms_samples",
            "last_level_samples",
            "mean_fractions_with_roots",
            "max_fraction_terms_seen_in_roots",
        ])
        for tag in sorted(by_exp):
            grp = by_exp[tag]
            runt = [r.runtime_sec for r in grp if r.runtime_sec is not None]
            frac = [float(r.fractions_tested) for r in grp if r.fractions_tested is not None]
            terms = [r.last_fraction_terms for r in grp if r.last_fraction_terms is not None]
            lvl = [r.last_level_started for r in grp if r.last_level_started is not None]
            uniq = [float(r.unique_fractions_with_roots) for r in grp if r.unique_fractions_with_roots is not None]
            seen_terms = [r.max_fraction_terms_seen_in_roots for r in grp if r.max_fraction_terms_seen_in_roots is not None]
            w.writerow([
                tag,
                len(grp),
                f"{mean(runt):.6f}" if runt else "",
                f"{mean(frac):.6f}" if frac else "",
                max(terms) if terms else "",
                max(lvl) if lvl else "",
                len(runt),
                len(frac),
                len(terms),
                len(lvl),
                f"{mean(uniq):.6f}" if uniq else "",
                max(seen_terms) if seen_terms else "",
            ])

    print(f"Files scanned: {len(files)}")
    print(f"Runs merged: {len(run_list)}")
    print(
        "Exact-metric coverage: "
        f"runtime={sum(1 for r in run_list if r.runtime_sec is not None)}, "
        f"fractions_tested={sum(1 for r in run_list if r.fractions_tested is not None)}, "
        f"last_fraction_terms={sum(1 for r in run_list if r.last_fraction_terms is not None)}, "
        f"last_level_started={sum(1 for r in run_list if r.last_level_started is not None)}"
    )
    print(f"Wrote: {out_runs}")
    print(f"Wrote: {out_digits}")
    print(f"Wrote: {out_exp}")


if __name__ == "__main__":
    main()
