# Other explored depths (companion to the reported-configuration folder)

This folder contains the experiment runs for the depths that appear in the
"Depth Values" column of the paper table but are NOT the reported configuration
of each row. The reported (deepest) configuration that produces the table's
Mean and Maximum values lives in the companion folder `table_experiments`.

Together the two folders hold every run listed by the table's Depth Values
column: `table_experiments` has the deepest depth per size, this folder has all
the shallower ones.

## What is here, per digit size

| Digits | Depths here | Reported depth (other folder) |
|-------:|:-----------:|:-----------------------------:|
| 10 | 2, 3, 4 | 7 |
| 12–30 | 2 | 3 |
| 35 | 2, 3, 8, 9 | 10 |
| 45 | 9, 10 | 11 |

Digit sizes 40 and 50 list a single depth in the table, so they have no other
depths and do not appear here.

Total: 120 runs. Each digit subfolder holds the result triplets
(`.out.txt`, `.meta.txt`, `.progress.txt`), a `param.txt` listing the
configurations of these other depths, and `s_p.txt` with the five semiprime
pairs.

## Important: these numbers are NOT the paper table values

`MANIFEST.csv` reports, per digit size and per depth, the mean successful
events, mean distinct successful centers, maximum distinct successful centers,
and the number of factored instances. These values differ from the published
table, which reports only the deepest depth of each row. For example, at 10
digits the reported depth 7 gives 134.4 mean events, whereas depth 3 gives 214
and depth 2 gives 70. This folder documents those non-reported search depths
for completeness and transparency; it is not a second copy of the table.

A successful event is an admissible constrained-quadratic test that produces an
integer candidate t with 1 < gcd(N, t) < N, counted from the `roots_found`
field of each run header.
