#!/usr/bin/env bash
set -Eeuo pipefail

# Complete only the experiment configurations missing from the paper archive:
#   35 digits: depth 8 (original parameter row 5)
#   40 digits: depth 16 (the only recovered parameter row)
#   45 digits: depth 11 (recovered original parameter row 3)
#   50 digits: depth 19 with the paper's 10000-second budget

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_DIR="$ROOT_DIR/code"
INPUT_DIR="$ROOT_DIR/input"
OUTPUT_DIR="$ROOT_DIR/output"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="run_only_missing_${RUN_STAMP}_pid$$"
RUN_DIR="$OUTPUT_DIR/$RUN_ID"
LOG_DIR="$RUN_DIR/_run_logs"
MASTER_LOG="$LOG_DIR/run.log"

mkdir -p "$RUN_DIR" "$LOG_DIR"
exec > >(tee -a "$MASTER_LOG") 2>&1

on_error() {
    local exit_code=$?
    echo "ERROR: launcher stopped with exit code $exit_code at $(date -u --iso-8601=seconds)"
    echo "Completed result directories are preserved in: $RUN_DIR"
    echo "See: $MASTER_LOG"
    exit "$exit_code"
}
trap on_error ERR

echo "BCI 2026 missing-depth completion launcher"
echo "start_utc=$(date -u --iso-8601=seconds)"
echo "root=$ROOT_DIR"
echo "python=$PYTHON_BIN"
echo "run_directory=$RUN_DIR"

command -v "$PYTHON_BIN" >/dev/null
"$PYTHON_BIN" --version

{
    echo "run_stamp=$RUN_STAMP"
    echo "mode=only_missing_depths"
    echo "start_utc=$(date -u --iso-8601=seconds)"
    echo "python_command=$PYTHON_BIN"
    "$PYTHON_BIN" --version 2>&1
    uname -a 2>/dev/null || true
    lscpu 2>/dev/null || true
    free -h 2>/dev/null || true
} > "$LOG_DIR/environment_${RUN_STAMP}.txt"

(
    cd "$CODE_DIR"
    "$PYTHON_BIN" -c 'import nikos_fractions_core; import dummy_optimized_v5; print("Required modules imported successfully")'
    "$PYTHON_BIN" -m unittest -v test_streaming_refactor.py
)

run_selected() {
    local label="$1"
    local par_file="$2"
    local sp_file="$3"
    local out_dir="$4"
    local parameter_id="$5"

    [[ -f "$par_file" ]] || { echo "ERROR: missing parameter file: $par_file"; return 1; }
    [[ -f "$sp_file" ]] || { echo "ERROR: missing prime-pair file: $sp_file"; return 1; }
    mkdir -p "$out_dir"

    echo
    echo "============================================================"
    echo "Starting $label at $(date -u --iso-8601=seconds)"
    echo "parameters=$par_file"
    echo "parameter_id=$parameter_id"
    echo "prime_pairs=$sp_file"
    echo "output=$out_dir"
    echo "============================================================"

    (
        cd "$CODE_DIR"
        "$PYTHON_BIN" run_par_exp.py \
            --par "$par_file" \
            --sp "$sp_file" \
            --out "$out_dir" \
            --id "$parameter_id" \
            --hard-timelimit \
            --strict-level-only \
            --heartbeat-every 10000
    )

    echo "Completed $label at $(date -u --iso-8601=seconds)"
}

run_selected \
    "35 digits, depth 8, 9900 seconds" \
    "$INPUT_DIR/param_dig.35.txt" \
    "$INPUT_DIR/s_p.35.txt" \
    "$RUN_DIR/exp_35_depth_8" \
    5

run_selected \
    "40 digits, depth 16, 14400 seconds" \
    "$INPUT_DIR/param_dig.40.txt" \
    "$INPUT_DIR/s_p.40.all_5.txt" \
    "$RUN_DIR/exp_40_depth_16" \
    1

run_selected \
    "45 digits, depth 11, 10000 seconds (recovered original settings)" \
    "$INPUT_DIR/param_dig.45.recovered.txt" \
    "$INPUT_DIR/s_p.45.txt" \
    "$RUN_DIR/exp_45_depth_11" \
    3

run_selected \
    "50 digits, depth 19, paper-aligned 10000 seconds" \
    "$INPUT_DIR/param_dig.50.paper_10000.txt" \
    "$INPUT_DIR/s_p.50.txt" \
    "$RUN_DIR/exp_50_depth_19_10000s" \
    1

echo
echo "All missing configurations completed at $(date -u --iso-8601=seconds)"

# Hash immutable inputs, code, environment record, and result artifacts. The
# live master log and checksum file itself are excluded to avoid self-changing
# checksum entries after the final status messages are appended.
(
    cd "$ROOT_DIR"
    find code input "$RUN_DIR" -type f \
        ! -path "$MASTER_LOG" \
        ! -name 'SHA256SUMS_*' \
        -print0 \
        | sort -z \
        | xargs -0 sha256sum \
        > "$LOG_DIR/SHA256SUMS_${RUN_STAMP}.txt"
)

echo "Checksums: $LOG_DIR/SHA256SUMS_${RUN_STAMP}.txt"
echo "Master log: $MASTER_LOG"
echo "Results preserved in: $RUN_DIR"
