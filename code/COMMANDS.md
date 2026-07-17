# Commands for running the BCI 2026 experiments

All commands below assume the current directory is `code/`.

## 0. Build the required backend first (one-time step)

The runners import the compiled module `dummy_optimized_v5`. No prebuilt
binaries are shipped, and `dummy_optimized_v5.py` contains Cython syntax, so
it is not directly importable. Build the module before anything else:

```bash
python3 -m pip install setuptools Cython
python3 setup_dummy_optimized_v5.py build_ext --inplace
```

A C compiler (`gcc`) and Python development headers (`python3-dev`) are
required. Verified on Ubuntu with Python 3.10 and 3.12.

## 1. Check the planned command without running it

```bash
python3 run_par.py --exp 10 --dry-run
```

On Windows, use `python` instead of `python3` if that is how Python is installed.

## 2. Reproduce the exact 10-digit configuration used for the paper row

Experiment ID 9 is the final line of `param_dig.10.txt`:

```text
1 500 1 7 200
```

Run all five saved semiprimes with that configuration:

```bash
python3 run_par.py --exp 10 --id 9 --heartbeat-every 10000
```

Outputs are written to `code/exp_10/` as:

```text
result_<s>_<p>_9.out.txt
result_<s>_<p>_9.meta.txt
result_<s>_<p>_9.progress.txt
```

## 3. Run every retained configuration for one digit bucket

```bash
python3 run_par.py --exp 12 --heartbeat-every 10000
```

Replace `12` with one of:

```text
10 12 14 16 18 20 22 24 26 28 30 35 40 50
```

Digit 45 is excluded here because `param_dig.45.txt` was not recovered in
this directory; reconstructed and recovered versions are available as
`../rerun_scripts/input/param_dig.45.reconstructed.txt` and
`param_dig.45.recovered.txt` (copy one next to the runner as
`param_dig.45.txt` to enable `--exp 45`).

## 4. Run several buckets sequentially

```bash
python3 run_par.py --exp 10 12 14 16 18 20 22 24 26 28 30 --heartbeat-every 10000
```

Be aware that the retained time limits range from hundreds to many thousands of seconds per configuration and prime pair.

## 5. Run the lower-level parallel driver directly

```bash
python3 run_par_exp.py \
  --par param_dig.10.txt \
  --sp s_p.10.txt \
  --out ./exp_10 \
  --id 9 \
  --hard-timelimit \
  --strict-level-only \
  --heartbeat-every 10000
```

## 6. Run a single-process experiment

```bash
python3 run_experiments_cli_streaming_rootsN.py \
  --par param_dig.10.txt \
  --sp s_p.10.txt \
  --out ./exp_10_sequential \
  --id 9 \
  --hard-timelimit \
  --strict-level-only \
  --heartbeat-every 10000
```

Use `--help` with any runner to see all options.

## 7. Generate statistics from raw results

From the `code` directory, after runs have produced `exp_*` folders:

Install the analysis dependency if needed:

```bash
python3 -m pip install pandas
```

```bash
python3 root_stats.py --input-dir . --out-prefix stats
```

For the grouped run-metadata tables:

```bash
python3 st_runmeta_stats.py .
```

To include fraction matrices:

```bash
python3 root_stats_with_matrices.py \
  --input-dir . \
  --out-prefix stats \
  --emit-matrices \
  --matrices-dir matrices
```

## 8. Run the consistency tests

```bash
python3 -m unittest -v test_streaming_refactor.py
```

## 9. Compiled backend

See step 0 above: building `dummy_optimized_v5` locally is mandatory. No
prebuilt `.so` is shipped in this repository, and `dummy_optimized_v5.py` is
Cython source (kept for reference alongside `dummy_optimized_v5.pyx`), not a
runnable pure-Python fallback.

## Input formats

Each `param_dig.<D>.txt` line contains:

```text
Nmin Mmax W depth timelimit_sec
```

Each `s_p.<D>.txt` line contains the two prime factors:

```text
s p
```

The recovered manifests contain five pairs per paper digit bucket, and every retained pair satisfies `5 <= p/s <= 15`.
