#!/usr/bin/env python3
from __future__ import annotations

import unittest

import nikos_fractions_core as core
import run_experiments_cli_streaming_rootsN as runner


Frac = tuple[int, int]


def _legacy_levels(Nmin: int, Mmax: int, W: int, depth: int):
    levels: dict[int, list[tuple[Frac, Frac, Frac, Frac, Frac]]] = {i: [] for i in range(1, depth + 1)}
    current: list[tuple[Frac, Frac]] = []

    for m in range(Nmin, Mmax):
        L = (1, m + 1)
        R = (1, m)
        levels[1].append((L, R, core.mediant(L, R), L, R))
        current.append((L, R))

    for lvl in range(2, depth + 1):
        nxt: list[tuple[Frac, Frac]] = []
        for pL, pR in current:
            pts = core.refine_interval(pL, pR, W=W)
            for i in range(len(pts) - 1):
                cL = pts[i]
                cR = pts[i + 1]
                levels[lvl].append((cL, cR, core.mediant(cL, cR), pL, pR))
                nxt.append((cL, cR))
        current = nxt
    return levels


class StreamingRefactorTests(unittest.TestCase):
    def test_bfs_matches_legacy_interval_sequence(self) -> None:
        Nmin, Mmax, W, depth = 1, 5, 2, 3
        legacy = _legacy_levels(Nmin=Nmin, Mmax=Mmax, W=W, depth=depth)
        expected = []
        for lvl in range(1, depth + 1):
            for L, R, M, pL, pR in legacy[lvl]:
                expected.append((lvl, L, R, M, pL, pR))

        got = [
            (it.level, it.left, it.right, it.median, it.parent_left, it.parent_right)
            for it in runner.iter_intervals_inverted_bfs_with_prov(
                Nmin=Nmin, Mmax=Mmax, W=W, depth=depth, include_paths=False
            )
        ]
        self.assertEqual(expected, got)

    def test_level_only_matches_bfs_level_slice(self) -> None:
        Nmin, Mmax, W, depth = 1, 6, 2, 4
        bfs = list(
            runner.iter_intervals_inverted_bfs_with_prov(
                Nmin=Nmin, Mmax=Mmax, W=W, depth=depth, include_paths=False
            )
        )
        for lvl in range(1, depth + 1):
            expected = [(it.left, it.right, it.parent_left, it.parent_right) for it in bfs if it.level == lvl]
            got = [
                (it.left, it.right, it.parent_left, it.parent_right)
                for it in runner.iter_level(level=lvl, Nmin=Nmin, Mmax=Mmax, W=W, include_paths=False)
            ]
            self.assertEqual(expected, got)

    def test_unique_fraction_stream_matches_legacy_first_seen(self) -> None:
        Nmin, Mmax, W, depth = 1, 5, 2, 3
        legacy = _legacy_levels(Nmin=Nmin, Mmax=Mmax, W=W, depth=depth)
        seen = set()
        expected = []

        for lvl in range(1, depth + 1):
            for L, R, M, pL, pR in legacy[lvl]:
                iL = runner.reduce_frac(L)
                iR = runner.reduce_frac(R)
                ppL = runner.reduce_frac(pL)
                ppR = runner.reduce_frac(pR)
                for fr in (L, M, R):
                    r = runner.reduce_frac(fr)
                    if r in seen:
                        continue
                    seen.add(r)
                    expected.append((r, lvl, iL, iR, ppL, ppR))

        got = [
            (fr, prov.level, prov.interval_left, prov.interval_right, prov.parent_left, prov.parent_right)
            for fr, prov in runner.iter_unique_fractions_first_prov(
                Nmin=Nmin,
                Mmax=Mmax,
                W=W,
                depth=depth,
                include_paths=False,
                traversal_mode="streaming-bfs",
                dedup_scope="global",
            )
        ]
        self.assertEqual(expected, got)


if __name__ == "__main__":
    unittest.main()
