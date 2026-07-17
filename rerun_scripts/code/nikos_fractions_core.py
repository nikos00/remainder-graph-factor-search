#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nikos Fractions (clean core + driver)

Level 1:
  intervals: (m/1 , (m+1)/1) for m=1..Mmax-1
  median:    (2m+1)/2 (i.e. mediant)

Refinement (Level >= 2):
  For each interval [L,R] with L=a/b, R=c/d:
    M = mediant(L,R) = (a+c)/(b+d)
    Create W points on each side of M using *median-based fans*:
      Left side points (between L and M):   P_L(k) = (k*L + M) / (k + 1) in pair form
        = (k*a + (a+c)) / (k*b + (b+d)) = ((k+1)a + c)/((k+1)b + d), k=1..W
      Right side points (between M and R):  P_R(k) = (M + k*R) / (k + 1) in pair form
        = ((a+c) + k*c) / ((b+d) + k*d) = (a + (k+1)c)/(b + (k+1)d), k=1..W

  Then take the set of points: {L} ∪ {P_L(k)} ∪ {M} ∪ {P_R(k)} ∪ {R},
  sort by numeric value, and children intervals are consecutive pairs.

Notes:
  - No reduction/simplification is performed.
  - Sorting uses exact rational ordering via cross multiplication (no floats).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
import argparse
import csv

Frac = Tuple[int, int]  # (num, den), den>0 in this model


def mediant(x: Frac, y: Frac) -> Frac:
    return (x[0] + y[0], x[1] + y[1])


def frac_cmp_desc(x: Frac, y: Frac) -> int:
    """Compare x and y by value x_num/x_den vs y_num/y_den, descending.
    Returns -1 if x>y, 0 if equal, +1 if x<y.
    """
    xn, xd = x
    yn, yd = y
    left = xn * yd
    right = yn * xd
    if left == right:
        return 0
    return -1 if left > right else 1


def sort_fracs_desc(fracs: List[Frac]) -> List[Frac]:
    from functools import cmp_to_key
    return sorted(fracs, key=cmp_to_key(frac_cmp_desc))


@dataclass(frozen=True)
class Interval:
    level: int
    left: Frac
    right: Frac
    median: Frac


def refine_interval(left: Frac, right: Frac, W: int) -> List[Frac]:
    """Return sorted points inside [left,right] used to create children."""
    a, b = left
    c, d = right
    m = (a + c, b + d)  # mediant

    pts: List[Frac] = [left]

    # Left points between left and median (median-based fan)
    for k in range(1, W + 1):
        pts.append(((k + 1) * a + c, (k + 1) * b + d))

    pts.append(m)

    # Right points between median and right (median-based fan)
    for k in range(1, W + 1):
        pts.append((a + (k + 1) * c, b + (k + 1) * d))

    pts.append(right)

    pts_sorted = sort_fracs_desc(pts)

    # Drop consecutive equal-by-value points to avoid zero-width intervals
    dedup: List[Frac] = []
    for p in pts_sorted:
        if not dedup or frac_cmp_desc(dedup[-1], p) != 0:
            dedup.append(p)
    return dedup


def build_levels(Mmax: int, W: int, depth: int) -> Dict[int, List[Interval]]:
    """Build intervals up to `depth` (Level 1..depth)."""
    if Mmax < 2:
        raise ValueError("Mmax must be >= 2.")
    if W < 0:
        raise ValueError("W must be >= 0.")
    if depth < 1:
        raise ValueError("depth must be >= 1.")

    levels: Dict[int, List[Interval]] = {i: [] for i in range(1, depth + 1)}

    # Level 1: (m/1, (m+1)/1)
    current: List[Tuple[Frac, Frac]] = []
    for m in range(1, Mmax):
        L = (m, 1)
        R = (m + 1, 1)
        M = mediant(L, R)  # (2m+1)/2
        levels[1].append(Interval(level=1, left=L, right=R, median=M))
        current.append((L, R))

    # Levels >= 2
    for lvl in range(2, depth + 1):
        nxt: List[Tuple[Frac, Frac]] = []
        for (L, R) in current:
            pts = refine_interval(L, R, W=W)
            for i in range(len(pts) - 1):
                cL = pts[i]
                cR = pts[i + 1]
                cM = mediant(cL, cR)
                levels[lvl].append(Interval(level=lvl, left=cL, right=cR, median=cM))
                nxt.append((cL, cR))
        current = nxt

    return levels


def write_csv(levels: Dict[int, List[Interval]], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["level", "L_num", "L_den", "M_num", "M_den", "R_num", "R_den"])
        for lvl in sorted(levels.keys()):
            for it in levels[lvl]:
                a, b = it.left
                m, n = it.median
                c, d = it.right
                w.writerow([lvl, a, b, m, n, c, d])


def main() -> None:
    ap = argparse.ArgumentParser(description="Nikos Fractions core + driver (no GUI).")
    ap.add_argument("--Mmax", type=int, default=6, help="Level-1 endpoints are m/1 for m=1..Mmax.")
    ap.add_argument("--W", type=int, default=3, help="Fan width per side (W left + W right).")
    ap.add_argument("--depth", type=int, default=3, help="Max depth (Level 1..depth).")
    ap.add_argument("--csv", type=str, default="", help="Optional output CSV path.")
    ap.add_argument("--head", type=int, default=12, help="Print first N intervals of each level.")
    args = ap.parse_args()

    levels = build_levels(Mmax=args.Mmax, W=args.W, depth=args.depth)

    total = sum(len(v) for v in levels.values())
    print(f"Mmax={args.Mmax}, W={args.W}, depth={args.depth}")
    for lvl in sorted(levels.keys()):
        items = levels[lvl]
        print(f"Level {lvl}: {len(items)} intervals")
        for it in items[:max(0, args.head)]:
            a, b = it.left
            m, n = it.median
            c, d = it.right
            print(f"  [{a}/{b}]  M={m}/{n}  [{c}/{d}]")
        if len(items) > args.head:
            print("  ...")

    if args.csv:
        write_csv(levels, args.csv)
        print(f"Wrote CSV: {args.csv}")
    print(f"Total intervals: {total}")


if __name__ == "__main__":
    main()
