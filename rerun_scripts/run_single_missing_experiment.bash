#!/usr/bin/env bash
set -Eeuo pipefail

# Shared implementation for the four per-configuration launchers.
# Invoke through one of the run_missing_*.sh wrappers, or directly with:
#   ./run_single_missing_experiment.bash 35_depth8|40_depth16|45_depth11|50_depth19_10000s

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_DIR="$ROOT_DIR/code"
INPUT_DIR="$ROOT_DIR/input"
OUTPUT_DIR="$ROOT_DIR/output"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORKERS="${WORKERS:-1}"
MODE="${1:-}"

if [[ ! "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: WORKERS must be a positive integer (received: $WORKERS)" >&2
    exit 2
fi

case "$MODE" in
    35_depth8)
        LABEL="35 digits, depth 8, 9900 seconds"
        PAR_FILE="$INPUT_DIR/param_dig.35.txt"
        SP_FILE="$INPUT_DIR/s_p.35.txt"
        PARAMETER_ID=5
        RESULT_DIR_NAME="exp_35_depth_8"
        ;;
    40_depth16)
        LABEL="40 digits, depth 16, 14400 seconds"
        PAR_FILE="$INPUT_DIR/param_dig.40.txt"
        SP_FILE="$INPUT_DIR/s_p.40.all_5.txt"
        PARAMETER_ID=1
        RESULT_DIR_NAME="exp_40_depth_16"
        ;;
    45_depth11)
        LABEL="45 digits, depth 11, 10000 seconds (recovered original settings)"
        PAR_FILE="$INPUT_DIR/param_dig.45.recovered.txt"
        SP_FILE="$INPUT_DIR/s_p.45.txt"
        PARAMETER_ID=3
        RESULT_DIR_NAME="exp_45_depth_11"
        ;;
    50_depth19_10000s)
        LABEL="50 digits, depth 19, paper-aligned 10000 seconds"
        PAR_FILE="$INPUT_DIR/param_dig.50.paper_10000.txt"
        SP_FILE="$INPUT_DIR/s_p.50.txt"
        PARAMETER_ID=1
        RESULT_DIR_NAME="exp_50_depth_19_10000s"
        ;;
    *)
        echo "Usage: $0 35_depth8|40_depth16|45_depth11|50_depth19_10000s" >&2
        exit 2
        ;;
esac

RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="run_${MODE}_${RUN_STAMP}_pid$$"
RUN_DIR="$OUTPUT_DIR/$RUN_ID"
RESULT_DIR="$RUN_DIR/$RESULT_DIR_NAME"
LOG_DIR="$RUN_DIR/_run_logs"
MASTER_LOG="$LOG_DIR/run.log"

mkdir -p "$RESULT_DIR" "$LOG_DIR"
exec > >(tee -a "$MASTER_LOG") 2>&1

on_error() {
    local exit_code=$?
    echo "ERROR: launcher stopped with exit code $exit_code at $(date -u --iso-8601=seconds)"
    echo "Partial results are preserved in: $RUN_DIR"
    echo "See: $MASTER_LOG"
    exit "$exit_code"
}
trap on_error ERR

echo "BCI 2026 single missing-experiment launcher"
echo "configuration=$MODE"
echo "description=$LABEL"
echo "start_utc=$(date -u --iso-8601=seconds)"
echo "root=$ROOT_DIR"
echo "python=$PYTHON_BIN"
echo "max_concurrent_tasks=$WORKERS"
echo "run_directory=$RUN_DIR"

command -v "$PYTHON_BIN" >/dev/null
"$PYTHON_BIN" --version
[[ -f "$PAR_FILE" ]] || { echo "ERROR: missing parameter file: $PAR_FILE"; exit 1; }
[[ -f "$SP_FILE" ]] || { echo "ERROR: missing prime-pair file: $SP_FILE"; exit 1; }

{
    echo "run_stamp=$RUN_STAMP"
    echo "configuration=$MODE"
    echo "description=$LABEL"
    echo "parameter_file=$PAR_FILE"
    echo "parameter_id=$PARAMETER_ID"
    echo "prime_pairs=$SP_FILE"
    echo "start_utc=$(date -u --iso-8601=seconds)"
    echo "python_command=$PYTHON_BIN"
    echo "max_concurrent_tasks=$WORKERS"
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

echo
echo "============================================================"
echo "Starting $LABEL at $(date -u --iso-8601=seconds)"
echo "parameters=$PAR_FILE"
echo "parameter_id=$PARAMETER_ID"
echo "prime_pairs=$SP_FILE"
echo "output=$RESULT_DIR"
echo "============================================================"

(
    cd "$CODE_DIR"
    "$PYTHON_BIN" run_par_exp.py \
        --par "$PAR_FILE" \
        --sp "$SP_FILE" \
        --out "$RESULT_DIR" \
        --id "$PARAMETER_ID" \
        --hard-timelimit \
        --strict-level-only \
        --workers "$WORKERS" \
        --heartbeat-every 10000
)

echo "Completed $LABEL at $(date -u --iso-8601=seconds)"

# Exclude the still-open master log and checksum file itself so every recorded
# checksum remains stable after the final launcher messages are appended.
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
