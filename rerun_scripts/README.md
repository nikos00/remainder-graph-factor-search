# Kubuntu launch package for the remaining BCI 2026 experiments

This folder contains only the launchers still needed to complete the paper
archive. The older broad rerun scripts were deliberately removed. The combined
launcher `run_only_missing_depths.sh` was retained.

Copy the entire `kubuntu_rerun` directory to every laptop. Each launcher needs
the shared `code/`, `input/`, and `run_single_missing_experiment.bash` files.

## One experiment per laptop

Choose one command on each laptop:

```bash
./run_missing_35_depth8.sh
./run_missing_40_depth16.sh
./run_missing_45_depth11.sh
./run_missing_50_depth19_10000s.sh
```

The four configurations are:

| Launcher | Configuration | Five pairs | Expected wall time |
|---|---|---:|---:|
| `run_missing_35_depth8.sh` | 35 digits, depth 8, 9,900 s | yes | about 3 h |
| `run_missing_40_depth16.sh` | 40 digits, depth 16, 14,400 s | yes | about 4–5 h |
| `run_missing_45_depth11.sh` | 45 digits, depth 11, 10,000 s | yes | about 3 h |
| `run_missing_50_depth19_10000s.sh` | 50 digits, depth 19, 10,000 s | yes | about 3 h |

Each launcher processes all five prime pairs. Concurrency is controlled with
the `WORKERS` environment variable and defaults to one task at a time. For
example:

```bash
WORKERS=1 ./run_missing_40_depth16.sh
WORKERS=2 ./run_missing_40_depth16.sh
```

The five-task 40-digit, depth-16 run had allocated about 50 GB and was still
growing when stopped, so 50 GB is not a known peak. On a 32 GB laptop, start
with `WORKERS=1` and monitor memory. See `HOW_TO_RUN_40_DEPTH16.txt` for the
commands, monitoring instructions, and memory warning.

## Preparation on each laptop

```bash
cd /path/to/kubuntu_rerun
chmod +x run_only_missing_depths.sh run_missing_*.sh run_single_missing_experiment.bash
```

Run unattended while preventing sleep, for example:

```bash
nohup systemd-inhibit --what=sleep --why="BCI 2026 missing experiment" \
  ./run_missing_35_depth8.sh > missing_35_depth8.console.log 2>&1 &
```

Replace the launcher and log name for the experiment assigned to that laptop.
Monitor with:

```bash
tail -f missing_35_depth8.console.log
```

## Combined alternative

To run all four configurations sequentially on one laptop:

```bash
nohup systemd-inhibit --what=sleep --why="BCI 2026 missing experiments" \
  ./run_only_missing_depths.sh > only_missing.console.log 2>&1 &
```

Allow approximately 13–15 hours for the combined launcher.

## Results

Every invocation creates a new directory under `output/`, so existing evidence
is never overwritten. Each successful five-pair configuration should create:

- five `.out.txt` files;
- five `.meta.txt` files;
- five `.progress.txt` files;
- an environment record, master log, and SHA-256 checksum file.

Copy the resulting experiment directory into the matching destination under:

`../collected_good_experiments/pending_results/`

The 45-digit launcher uses the recovered original depth-11 row
`Nmin=1, Mmax=300, W=1, depth=11, timelimit=10000`. The 50-digit launcher uses
the paper-aligned 10,000-second budget; the historical run used 7,200 seconds.

See `UBUNTU_INSTRUCTIONS.md` for setup, monitoring, stopping, and collection.
