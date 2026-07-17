# Verification on a fresh Linux machine

The following steps confirm that the package builds and runs correctly before
launching any long experiments. Verified on Ubuntu with Python 3.10 and 3.12.

## 1. Prerequisites

```bash
sudo apt install python3 python3-dev python3-pip build-essential
python3 -m pip install setuptools Cython
```

## 2. If the folder was copied from Windows

Executable bits may have been lost in transfer. Restore them:

```bash
cd remainder-graph-factor-search
chmod +x rerun_scripts/*.sh rerun_scripts/*.bash
```

This is not needed after a git clone, since git restores the file modes.

## 3. Build the backend

```bash
cd code
python3 setup_dummy_optimized_v5.py build_ext --inplace
ls dummy_optimized_v5*.so
```

The last command must list a compiled module.

## 4. Smoke test, about 15 seconds

```bash
head -1 s_p.10.txt > /tmp/sp_test.txt
echo "1 1000 50 2 15" > /tmp/par_test.txt
python3 run_experiments_cli_streaming_rootsN.py \
  --par /tmp/par_test.txt --sp /tmp/sp_test.txt --out /tmp/results_test
```

Expected behavior for the first pair (`s=14537 p=201389`, ten-digit N):

1. a line such as `FIRST ROOT FOUND at elapsed=0.0xs frac=2/249 level=1 x0=4849 root_x=14537/3` appears almost immediately;
2. the run ends after about 15 seconds, which is the configured time limit;
3. `/tmp/results_test/` contains `result_14537_201389_1.out.txt`, `.meta.txt`, and `.progress.txt`.

If all three hold, the environment is set up correctly.

## 5. Consistency tests

```bash
python3 -m unittest -v test_streaming_refactor.py
```

## 6. Reproducing a paper row

The exact 10-digit configuration of the paper (experiment ID 9, five pairs,
200 s each):

```bash
python3 run_par.py --exp 10 --id 9 --heartbeat-every 10000
```

Compare the outputs in `exp_10/` against
`../verification_output/aggregate_10_digit/`: mean successful events 134.4,
mean distinct successful centers 57.6, maximum 73.

The full command reference is `code/COMMANDS.md`; input formats are described
in `code/INPUT_FILES.md`.
