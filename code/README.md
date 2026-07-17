# Nikos Fractions Streaming Experiments

## What was changed

This refactor removes static/full-tree allocation and keeps memory bounded:

- Added **streaming BFS** traversal (level-by-level), keeping only current/next level in memory.
- Added **level-only mode** (`--level-only L`) that enumerates only one level with **O(depth)** path memory.
- Kept deterministic ordering for reproducibility.
- Added hard-timeout-safe dummy checking via isolated worker process (with fallback when process spawning is restricted).
- Preserved output compatibility (`.out.txt`, `.meta.txt`, `.progress.txt`) and restored `COLUMNS ...` header in `.out.txt`.
- Added optional heartbeat logging every N tested fractions.

---

## Main scripts

- `run_experiments_cli_streaming_rootsN.py`  
  Main runner (single-process over `(s,p)` pairs).
- `run_par_exp.py`  
  Parallel runner (parallel over `(s,p)` for each experiment line).
- `run_par.py`  
  Thin wrapper using `param_dig.<exp>.txt` and `s_p.<exp>.txt`.

---

## Input files

### 1) Parameter file (`--par`)
Each non-empty, non-comment line must be:

`Nmin Mmax W depth timelimit_sec`

Example:
```txt
1 1000 50 3 150
```

### 2) Prime-pairs file (`--sp`)
Each non-empty, non-comment line must be:

`s p`

Example:
```txt
14243 211199
14537 201389
```

Repository already includes many ready files like:

- `param_dig.10.txt`, `param_dig.40.txt`, ...
- `s_p.10.txt`, `s_p.40.txt`, ...

---

## How to run

## A) Direct main runner

```bash
python3 run_experiments_cli_streaming_rootsN.py \
  --par param_dig.40.txt \
  --sp s_p.40.txt \
  --out ./exp_40 \
  --hard-timelimit
```

### Useful flags

- `--streaming-bfs` : explicit BFS mode (default behavior).
- `--level-only L` : enumerate/test only level `L` (O(depth) mode).
- `--heartbeat-every N` : print progress heartbeat every `N` tested fractions.
- `--stop-on-root [K]` : stop after finding `K` roots (`--stop-on-root` alone means `K=1`).
- `--no-zero-row` : do not emit zero row on `TIMEOUT_NO_ROOTS`.
- `--id N` : run only the Nth line from the parameter file.

Example level-only run:
```bash
python3 run_experiments_cli_streaming_rootsN.py \
  --par param_dig.40.txt \
  --sp s_p.40.txt \
  --out ./exp_40_level2 \
  --level-only 2 \
  --hard-timelimit
```

## B) Parallel over `(s,p)` pairs

```bash
python3 run_par_exp.py \
  --par param_dig.40.txt \
  --sp s_p.40.txt \
  --out ./exp_40 \
  --hard-timelimit \
  --heartbeat-every 10000
```

## C) Wrapper by experiment number

```bash
python3 run_par.py --exp 40 --dry-run
python3 run_par.py --exp 40 --level-only 2 --heartbeat-every 10000
```

`run_par.py` maps:

- `--exp 40` -> `param_dig.40.txt` + `s_p.40.txt`
- output dir -> `./exp_40`

---

## Output files

For each run (`id`, `s`, `p`) you get:

- `result_<s>_<p>_<id>.out.txt`
- `result_<s>_<p>_<id>.meta.txt`
- `result_<s>_<p>_<id>.progress.txt`

`out.txt` includes:

- header lines (`# key=value`)
- `COLUMNS ...` line
- rows for root events

These remain compatible with existing analytics scripts.

---

## Tests added

Added `test_streaming_refactor.py` to verify:

- BFS interval order matches legacy small-case behavior.
- `--level-only` enumeration matches BFS slice for the same level.
- Unique-fraction stream order/provenance is deterministic and correct.

Run:
```bash
python3 -m unittest -v test_streaming_refactor.py
```

---

## Notes

- Python 3.12 is supported in current setup.
- `root_stats.py` / `root_stats_with_matrices.py` require `pandas`.
