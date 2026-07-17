# Experiment input files

All recovered experiment inputs are included directly in this `code` directory. They remain beside the runner scripts because `run_par.py` expects these filenames in its current working directory.

## Parameter files

Files named `param_dig.<D>.txt` describe the search configurations for semiprimes with `D` decimal digits.

Each non-comment line has five fields:

```text
Nmin Mmax W depth timelimit_sec
```

Included paper buckets:

```text
param_dig.10.txt
param_dig.12.txt
param_dig.14.txt
param_dig.16.txt
param_dig.18.txt
param_dig.20.txt
param_dig.22.txt
param_dig.24.txt
param_dig.26.txt
param_dig.28.txt
param_dig.30.txt
param_dig.35.txt
param_dig.40.txt
param_dig.50.txt
```

`param_dig.45.txt` was not found in the recovered archive. Additional `28.a` and 32-digit parameter files are retained as historical variants.

## Prime-pair files

Files named `s_p.<D>.txt` contain the exact semiprime factors used as inputs.

Each line has two fields:

```text
s p
```

Five-pair manifests survive for every paper bucket, including 45 digits. For 40 digits, the complete five-pair manifest is `s_p.40.all_5.txt`; the active `s_p.40.txt` copy contains only two pairs from a later state. To rerun all five 40-digit paper inputs without changing the archived file, call the lower-level runner explicitly:

```bash
python3 run_par_exp.py \
  --par param_dig.40.txt \
  --sp s_p.40.all_5.txt \
  --out ./exp_40_all_5 \
  --hard-timelimit \
  --strict-level-only
```

Every pair in the complete paper manifests satisfies:

```text
5 <= p/s <= 15
```

## Inputs to analysis scripts

The experiment runner generates:

```text
result_<s>_<p>_<id>.out.txt
result_<s>_<p>_<id>.meta.txt
result_<s>_<p>_<id>.progress.txt
```

`root_stats.py`, `root_stats_with_matrices.py`, and `st_runmeta_stats.py` use these generated files as their inputs. Recovered examples are stored under `../output/`.

`make_fraction_id_matrices.py` takes a generated event CSV such as:

```text
../output/aggregate_10_digit/stats_fraction_events.csv
```

These are analysis inputs, not additional inputs needed to run the factor-search experiments.

## Local source modules

The main runner also imports these local modules, both included here:

- `nikos_fractions_core.py`
- `dummy_optimized_v5.py`

No external fraction list or hidden prime database is read by the main runner.

