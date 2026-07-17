# Expected runtime for the remaining experiments

The five prime pairs inside each configuration run concurrently. Runtime is
therefore approximately one configured time budget, plus setup and shutdown
overhead, rather than five times the budget.

| Launcher | Parameter budget | Practical allowance |
|---|---:|---:|
| `run_missing_35_depth8.sh` | 9,900 s (2 h 45 min) | about 3–3.5 h |
| `run_missing_40_depth16.sh` | 14,400 s (4 h) | about 4–5 h |
| `run_missing_45_depth11.sh` | 10,000 s (2 h 47 min) | about 3–3.5 h |
| `run_missing_50_depth19_10000s.sh` | 10,000 s (2 h 47 min) | about 3–3.5 h |

When distributed across four laptops, all configurations can finish in roughly
the time of the longest job: approximately 4–5 hours.

`run_only_missing_depths.sh` runs them sequentially with a total configured
budget of 44,300 seconds (12 h 18 min). Allow approximately 13–15 hours.
