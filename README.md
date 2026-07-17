# Quadratic Structures in the Remainder Graph N mod x and Semiprime Factor Search

Code, exact inputs, and complete experimental artifacts for the paper:

> N. Verykios, C. Gogos. Quadratic Structures in the Remainder Graph N mod x and Semiprime Factor Search. BCI 2026.

The method examines local quadratic patterns in the discrete graph `y = N mod x` for semiprimes `N = s*p`, in windows around centers of the form `x0 = floor(sqrt(nN/d))` produced by mediant refinement of fractions. Quadratics constrained to pass through `(0, N)` are intersected with the diagonal `y = x`, and integer candidates `t` are tested with `gcd(N, t)`.

## Repository layout

`code/` contains the experiment runners, the Cython backend sources, all parameter files (`param_dig.*.txt`), and the exact prime-pair manifests (`s_p.*.txt`) for every digit size reported in the paper. See `code/README.md`, `code/COMMANDS.md`, and `code/INPUT_FILES.md`.

`experiments/` contains the archive of experimental artifacts behind the results table of the paper, for digit sizes 10 to 50: per-digit curated inputs, manifests, raw result triplets (`.out.txt`, `.meta.txt`, `.progress.txt`, `.ext.txt`), the summary statistics file `stats_v3_by_digits.csv`, the per-digit audit `completeness.csv`, and SHA-256 integrity hashes under `archive_metadata/`.

`experiments/pending_results/` holds the four final configurations (35 digits depth 8, 40 digits depth 16, 45 digits depth 11, 50 digits depth 19 at 10,000 s), completed on 2026-07-15 and 2026-07-16. The directory name is historical; all runs are complete.

`rerun_scripts/` contains the launcher scripts, inputs, and the code snapshot used to execute the four final configurations on Kubuntu, together with per-run provenance logs in `run_logs/` (environment description, master log, SHA-256 sums).

`verification_output/` contains aggregate outputs that reproduce the 10-digit table row of the paper exactly, and a later 24-digit rerun which is not the original 24-digit output of the paper and is marked as such.

## Building and running

Requirements: Linux, Python 3.10 or newer (the recovered environment used 3.12), setuptools, Cython. The statistics utilities additionally need pandas.

The runners import the compiled module `dummy_optimized_v5`. No prebuilt binaries are shipped, so the module must be built once before running anything. The file `dummy_optimized_v5.py` is Cython source kept for reference and cannot be imported directly. From inside `code/`:

```bash
pip install cython setuptools
python3 setup_dummy_optimized_v5.py build_ext --inplace

# run one digit-size experiment (example: 10 digits)
python3 run_par.py --exp 10
```

Parameter file format (`param_dig.<D>.txt`): one line per configuration, `Nmin Mmax W depth timelimit_sec`. Prime-pair file format (`s_p.<D>.txt`): one line per pair, `s p`, five pairs per digit size.

A short verification procedure for a fresh machine is given in `TESTING.md`. The full command reference is `code/COMMANDS.md`.

## Verifying the results of the paper

The five 10-digit runs reproduce the published values exactly: mean successful events 134.4, mean distinct successful centers 57.6, maximum 73. See `verification_output/aggregate_10_digit/`.

`experiments/stats_v3_by_digits.csv` contains the summary values reproduced in the table of the manuscript. `experiments/completeness.csv` records, per digit size, the expected and existing outputs; all rows are complete. Integrity hashes are in `experiments/archive_metadata/SHA256SUMS.txt` and `SHA256SUMS_pending_results.txt`.

## Provenance

Artifacts for digit sizes 10 to 30 are the surviving originals from the experimental campaign of the paper. The four configurations in `experiments/pending_results/` were re-executed on 2026-07-15 and 2026-07-16 with the preserved parameter rows and the same five prime pairs per digit size; run logs and environment records are in `rerun_scripts/run_logs/`. The directory `experiments/digits_50/results` additionally retains valid historical 7,200-second finals, kept separate from the paper-aligned 10,000-second runs. The 40-digit depth-16 configuration used a 14,400-second budget, which is the recovered original setting.

## License

MIT, see `LICENSE`.
