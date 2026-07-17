# Collected BCI 2026 paper experiments

This directory is a non-destructive collection of the experiment artifacts
used to produce the paper's digit-by-digit results table. The archive is
complete: all configurations for every digit size (10–50) have been executed.

## Contents

- `digits_10` through `digits_50`: curated inputs, manifests, and surviving
  raw result artifacts from the original experimental campaign.
- `pending_results/`: the four final configurations, completed on
  2026-07-15/16 (the directory name is historical):
  `exp_35_depth_8`, `exp_40_depth_16`, `exp_45_depth_11`,
  `exp_50_depth_19_10000s`. Each contains five output/metadata/progress
  triplets. Provenance logs for these runs are in `../rerun_scripts/run_logs/`.
- `stats_v3_by_digits.csv` and `.ods`: the summary values reproduced in the
  manuscript.
- `manifest_summary.csv`: original Ubuntu source provenance.
- `completeness.csv`: per-digit audit; all rows are complete.
- `archive_metadata/SHA256SUMS.txt` and `SHA256SUMS_pending_results.txt`:
  integrity hashes for the collected files.

## Notes

- The new 50-digit 10,000-second results are kept separate from
  `digits_50/results`, which contains the valid historical 7,200-second runs
  with the same result filenames; merging them would overwrite historical
  evidence.
- For digits 35, 40, and 45, the parameter IDs were deliberately preserved as
  5, 1, and 3 respectively, so the completing artifacts associate with the
  original parameter rows without renumbering.
- One surviving historical 35-digit depth-9 output lacks its metadata sidecar.
  The output itself is final and contains the essential status and parameters.
- The 40-digit depth-16 configuration used a 14,400-second budget (the
  recovered original setting).

Do not delete or replace the source archive. Preserve both this collection and
the original experiment directories.
