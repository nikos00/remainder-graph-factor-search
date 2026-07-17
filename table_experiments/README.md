# Experiments behind the paper's results table

This folder contains exactly the experiment files that produce the values
reported in the paper's digit-by-digit results table, and nothing else.

## Reported configuration per digit size

For each digit size the reported statistics correspond to a single parameter
configuration: the one with the largest refinement depth among those explored
at that size. Shallower depths were also run during the search, but their
individual counts are not tabulated in the paper and are not included here.

| Digits | Depth | Runtime (s) | Instances |
|-------:|:-----:|:-----------:|:---------:|
| 10 | 7 | 200 | 5 |
| 12–20 | 3 | 200 | 5 |
| 22–30 | 3 | 1000 | 5 |
| 35 | 10 | 9900 | 5 |
| 40 | 16 | 14400 | 5 |
| 45 | 11 | 10000 | 5 |
| 50 | 19 | 10000 | 5 |

Total: 75 runs (15 digit sizes, five semiprimes each).

## Contents

One subfolder per digit size. Each holds, for the reported configuration:

- five result triplets (`.out.txt` result, `.meta.txt` metadata,
  `.progress.txt` progress log), one per semiprime;
- `param.txt`: the exact parameter line, `Nmin Mmax W depth timelimit_sec`;
- `s_p.txt`: the five semiprime factor pairs `s p`.

## Verification

`MANIFEST.csv` is recomputed directly from the files in this folder. Its
`vs_published` column is `MATCH` for every row: mean successful events, mean
distinct successful centers and maximum distinct successful centers reproduce
the published table exactly. The `factored` column additionally reports how
many of the five semiprimes yielded at least one non-trivial factor.

A successful event is an admissible constrained-quadratic test that produces an
integer candidate t with 1 < gcd(N, t) < N, counted from the `roots_found`
field of each run header. Placeholder zero rows written by runs that found no
roots are not counted as events.

## Note on the "Depth Values" column of the paper table

The paper table lists, per digit size, several depth values (for example
2|3|4|7 for 10 digits). Those are the depths explored during the search. The
Mean and Maximum columns of each row report the deepest of those depths only
(depth 7 for the 10-digit row, depth 3 for 12 to 30 digits, and so on), not an
aggregate across all listed depths. This folder therefore contains that single
deepest configuration per size.
