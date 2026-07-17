# Kubuntu instructions for the four remaining experiments

## 1. Copy the complete package

Copy the entire `kubuntu_rerun` directory to each laptop. Do not copy only a
launcher: every run also needs `code/`, `input/`, and
`run_single_missing_experiment.bash`.

## 2. Install prerequisites

Python 3.12 is recommended because the recovered compiled accelerator targets
CPython 3.12 on x86-64 Linux. From the package directory, confirm:

```bash
python3 --version
python3 -c 'import sys; print(sys.version)'
```

If required, install the packages used by the analysis/runtime environment:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv build-essential
python3 -m pip install --user numpy pandas sympy
```

## 3. Enable launchers

```bash
chmod +x run_only_missing_depths.sh run_missing_*.sh run_single_missing_experiment.bash
```

## 4. Assign one launcher per laptop

Concurrency is controlled by `WORKERS`. It defaults to `1`. On a 32 GB laptop,
start the 40-digit, depth-16 run with one task at a time:

Laptop A:

```bash
nohup systemd-inhibit --what=sleep --why="BCI 35 depth 8" \
  env WORKERS=1 ./run_missing_35_depth8.sh > missing_35_depth8.console.log 2>&1 &
```

Laptop B:

```bash
nohup systemd-inhibit --what=sleep --why="BCI 40 depth 16" \
  env WORKERS=1 ./run_missing_40_depth16.sh > missing_40_depth16.console.log 2>&1 &
```

Laptop C:

```bash
nohup systemd-inhibit --what=sleep --why="BCI 45 depth 11" \
  env WORKERS=1 ./run_missing_45_depth11.sh > missing_45_depth11.console.log 2>&1 &
```

Laptop D:

```bash
nohup systemd-inhibit --what=sleep --why="BCI 50 depth 19 10000s" \
  env WORKERS=1 ./run_missing_50_depth19_10000s.sh > missing_50_depth19_10000s.console.log 2>&1 &
```

After confirming that one task stays within safe memory limits, use
`WORKERS=2` to allow two tasks at once. The 40-digit run previously reached
about 50 GB across five tasks and was still growing, so monitor it carefully.
See `HOW_TO_RUN_40_DEPTH16.txt` for a short command reference.

If `systemd-inhibit` is unavailable, omit it but disable automatic suspend in
Kubuntu's power settings.

## 5. Monitor

Use the matching console log, for example:

```bash
tail -f missing_40_depth16.console.log
```

Check active processes:

```bash
pgrep -af 'run_single_missing_experiment|run_par_exp|run_experiments_cli'
```

Progress files are updated inside the newest `output/run_<configuration>_*`
directory. A finished run has `phase: finished` in all five progress files and
five final `.out.txt` plus five `.meta.txt` files.

## 6. Stop safely if necessary

First identify the relevant processes:

```bash
pgrep -af 'run_single_missing_experiment|run_par_exp|run_experiments_cli'
```

Send a normal termination signal to the specific launcher PID rather than
deleting its output. Partial progress remains preserved in the timestamped run
directory.

## 7. Collect completed results

Each laptop creates a separate timestamped directory under `output/`. Copy the
experiment subdirectory to the corresponding location in
`collected_good_experiments/pending_results/`:

- `exp_35_depth_8`
- `exp_40_depth_16`
- `exp_45_depth_11`
- `exp_50_depth_19_10000s`

Also retain each `_run_logs` directory. It records the machine, CPU, Python
version, console output, and checksums needed for reproducibility.

## 8. Combined one-laptop alternative

The retained `run_only_missing_depths.sh` runs all four configurations
sequentially:

```bash
nohup systemd-inhibit --what=sleep --why="BCI all missing experiments" \
  ./run_only_missing_depths.sh > only_missing.console.log 2>&1 &
```
