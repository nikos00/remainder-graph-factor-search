# Pending result destinations

These directories are intentionally empty until
`kubuntu_rerun/run_only_missing_depths.sh` finishes.

Copy the complete output directory for each configuration into its matching
directory here. Each completed configuration should add 15 files: five
`.out.txt`, five `.meta.txt`, and five `.progress.txt` files.

After copying, regenerate `archive_metadata/SHA256SUMS.txt` and update
`completeness.csv` from `pending` to `complete` only after confirming all five
final statuses and parameters.
