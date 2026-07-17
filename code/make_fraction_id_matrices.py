#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events-csv", required=True, help="e.g. stats_exp10_fraction_events.csv")
    ap.add_argument("--out-dir", default="matrices", help="output directory")
    args = ap.parse_args()

    df = pd.read_csv(args.events_csv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # For each (s,p) build an (n,d) x id matrix with counts
    for (s, p), g in df.groupby(["s", "p"]):
        mat = (
            g.pivot_table(
                index=["frac_n", "frac_d"],     # rows: (n,d)
                columns="id",                  # columns: id
                values="root_idx",             # any column works for count
                aggfunc="count",
                fill_value=0
            )
            .astype(int)
            .reset_index()
            .sort_values(["frac_d", "frac_n"])
        )

        # Also add a "total" column (occurrences summed over all ids)
        id_cols = [c for c in mat.columns if isinstance(c, (int, float)) or str(c).isdigit()]
        # ids may have been read as int columns or as strings; handle both:
        id_cols = [c for c in mat.columns if c not in ["frac_n", "frac_d"]]
        mat["total"] = mat[id_cols].sum(axis=1)

        out_path = out_dir / f"matrix_s{s}_p{p}.csv"
        mat.to_csv(out_path, index=False)
        print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
