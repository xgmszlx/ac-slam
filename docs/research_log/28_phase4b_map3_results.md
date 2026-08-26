# Phase 4B map3 Fresh Controlled Results

Date completed: 2026-08-26

This document reports the frozen map3 A/B/C observations. Scientific interpretation
and the phase decision are separated into document 29. Raw tables and plots are in
`results/phase4b/map3/aggregate/`.

## 1. Completion and integrity

- Formal branch: `research/phase4b-realization-aware`
- Frozen root commit: `07cb9993a6049466520194283aec99013ea19b24`
- Frozen baseline commit: `7993bf8b93e503b352d89e3992b8e5d7b08e4459`
- Frozen navigation commit: `062283d364d891603a546b83e557ab638ffaa163`
- Preflight: PASS; catkin build PASS; Phase 4A tests PASS; mapping tests PASS.
- Formal suite: 15/15 runs `COMPLETED`, 15 `VALID`, zero experimental failures and
  zero formal technical-invalid runs.
- Every formal run contains all 19 required manifest, raw-log, trajectory, map,
  closure, gate, repair and summary artifacts.
- `enable_loop_diagnostics=false` in all 15 formal manifests. Ground truth and Karto
  rejection diagnostics were not online inputs.
- For every seed, A/B/C independently produced byte-identical `tsp_record.json`
  files. The five per-seed SHA-256 prefixes are `5348898d994c`, `0e4d2479b3c3`,
  `26c2ab59cda9`, `4b5a1ea1ceba` and `b5db3999a04d`.

One externally interrupted seed-21004/C attempt stopped before exploration
completion. Its partial run and six author-side outputs are preserved under
`interrupted_attempt_20260825T162238_seed21004_C/`, labelled
`TECHNICAL_INVALID_INTERRUPTED`, and excluded from all aggregate tables. The frozen
runner, source commits and scientific parameters were unchanged for the successful
replacement. The earlier seed-21001 pipeline pilot remains separately archived and
excluded as specified in document 26.

| Seed | execution order | A | B | C |
|---:|---|---|---|---|
| 21001 | A -> B -> C | VALID | VALID | VALID |
| 21002 | B -> C -> A | VALID | VALID | VALID |
| 21003 | C -> A -> B | VALID | VALID | VALID |
| 21004 | A -> C -> B | VALID | VALID | VALID |
| 21005 | B -> A -> C | VALID | VALID | VALID |

## 2. Active-loop realization

The seed, not the loop, is the inference unit. The pooled counts below are descriptive
only.

| Condition | planned | execution started | attributable accepted | pooled accepted/executed | seed-rate mean | median | range |
|---|---:|---:|---:|---:|---:|---:|---:|
| A Original | 21 | 21 | 1 | 4.76% | 6.67% | 0% | 0–33.33% |
| B Always-Trace | 21 | 21 | 2 | 9.52% | 8.00% | 0% | 0–40% |
| C Selective | 21 | 21 | 3 | 14.29% | 13.00% | 0% | 0–40% |

Seed-wise acceptance rates were:

| Seed | A | B | C |
|---:|---:|---:|---:|
| 21001 | 0 | 0 | 0 |
| 21002 | 0.333 | 0 | 0 |
| 21003 | 0 | 0 | 0.250 |
| 21004 | 0 | 0.400 | 0 |
| 21005 | 0 | 0 | 0.400 |

All accepted events came from `/Mapper/loop_closed` and have contiguous typed event
sequences. Accepted loop identities were A: seed 21002 vertex 8; B: seed 21004
vertices 15 and 22; C: seed 21003 vertex 21 and seed 21005 vertices 26 and 8.
The C seed-21003 acceptance occurred on `NO_REPAIR`; the two C seed-21005
acceptances occurred during `SELECTIVE_REPAIR` and triggered early stop.

## 3. Execution cost

| Condition | active-loop distance mean / median / range (m) | active-loop time mean / median / range (s) | total distance mean (m) | total sim time mean (s) |
|---|---|---|---:|---:|
| A | 88.87 / 97.34 / 58.00–116.14 | 257.34 / 263.30 / 167.0–320.5 | 531.23 | 1338.16 |
| B | 173.54 / 145.68 / 112.53–251.99 | 604.12 / 487.30 / 347.5–1086.0 | 600.85 | 1663.44 |
| C | 104.93 / 101.20 / 66.87–156.18 | 328.68 / 326.90 / 235.8–484.3 | 518.45 | 1374.26 |

C minus B active-loop distance was negative in all five seeds: mean -68.61 m,
median -45.66 m, range -162.77 to -32.07 m. C minus B active-loop time was also
negative in all five seeds: mean -275.44 s, median -130.40 s, range -850.20 to
-108.00 s. Total exploration distance and time were lower for C than B in all five
seeds (mean differences -82.41 m and -289.18 s).

B repaired/traced all 21 loops. C triggered repair for 9/21 and selected
`NO_REPAIR` for 12/21. C produced two early stops, both in seed 21005, with 23 of 24
planned waypoints skipped in each case and a combined conservative saved-polyline
lower bound of 21.53 m. Counterfactual saved time is not measured.

The seed-21005 B loop at vertex 22 took 491.3 s and 68.92 m but produced no accepted
constraint. It initially stalled after waypoint 1 while `/clock`, Navigator and
nonzero velocity commands remained active, then recovered without intervention.

## 4. Trajectory outcome

| Condition | APE mean / median / range (m) | RPE translation mean / median / range (m) | RPE rotation mean / median / range (deg) |
|---|---|---|---|
| A | 1.0839 / 0.8017 / 0.2401–1.9310 | 0.03764 / 0.03476 / 0.03248–0.05242 | 0.2153 / 0.2083 / 0.1406–0.3379 |
| B | 0.7242 / 0.6034 / 0.5087–1.0433 | 0.07171 / 0.07439 / 0.06283–0.07929 | 0.5580 / 0.3628 / 0.2876–1.3284 |
| C | 0.7210 / 0.6047 / 0.4936–1.1569 | 0.04348 / 0.04332 / 0.03510–0.05231 | 0.2372 / 0.2437 / 0.2101–0.2635 |

C-A APE differences were better in 3/5 seeds and worse in 2/5 (mean -0.3629 m,
median -0.1159 m, range -1.3302 to +0.9168 m). C-A RPE translation was worse in
4/5 seeds (mean +0.00584 m), and C-A RPE rotation was worse in 4/5 seeds (mean
+0.02188 deg). C-B RPE translation and rotation were lower in all five seeds, while
C-B APE was lower in 3/5 seeds and nearly equal on the five-seed mean (-0.0032 m).

## 5. Mapping outcome

| Condition | occupied IoU mean / median / range | boundary F1 mean / median / range | unknown ratio mean |
|---|---|---|---:|
| A | 0.06645 / 0.06127 / 0.04997–0.08330 | 0.41059 / 0.39196 / 0.31588–0.55859 | 0.11135 |
| B | 0.08043 / 0.07766 / 0.07234–0.09172 | 0.50453 / 0.52350 / 0.43614–0.58420 | 0.10986 |
| C | 0.06751 / 0.07090 / 0.05599–0.07584 | 0.44954 / 0.48551 / 0.32782–0.54552 | 0.11489 |

C-A occupied-IoU differences were positive in 3/5 seeds and negative in 2/5
(mean +0.00106; range -0.02184 to +0.02587). C-A boundary-F1 differences were
positive in 4/5 seeds but had one large negative value (mean +0.03895; range
-0.23077 to +0.22123). C-B occupied IoU was lower in all five seeds (mean
-0.01292), and C-B boundary F1 was lower in 3/5 seeds (mean -0.05499).

These scores use identity map-frame registration, occupied threshold 0.65, GT
unknown exclusion and 0.20 m boundary tolerance. Occupied IoU remains sensitive to
the frozen Stage-filled-obstacle versus LiDAR-surface representation mismatch.

## 6. Paired effects and observed regressions

Seed-wise acceptance differences were heterogeneous:

- C-A: `[0, -0.333, +0.250, 0, +0.400]`; mean +0.0633, median 0.
- B-A: `[0, -0.333, 0, +0.400, 0]`; mean +0.0133, median 0.
- C-B: `[0, 0, +0.250, -0.400, +0.400]`; mean +0.0500, median 0.

Observed paired regressions include seed 21002 vertex 8, accepted by A but rejected
after both B and C execution, and seed 21004 vertices 15 and 22, accepted by B but
not C. Conversely, C uniquely accepted seed 21003 vertex 21 and seed 21005 vertices
26 and 8. These are condition-level outcomes from fresh stochastic executions, not
deterministic per-loop counterfactuals.

Three C repair plans recorded lengths above the nominal 12 m configuration (12.45,
12.56 and 12.77 m). The implementation appends the final segment before detecting
that the accumulated cap is crossed. This is reported as an implementation-bound
semantic anomaly; no formal parameter or planner logic was changed.

## 7. Statistical validation scope

The statistical fallacy scan covered 11/11 prescribed categories. No aggregate/per-
seed direction reversal changes the main cost result, but acceptance and outcome
heterogeneity prevent a stability claim. There was no attrition among formal runs;
the interrupted technical attempt is transparently retained. Metrics and thresholds
were frozen before formal results, limiting look-elsewhere and forking-path risks.
No p-values or loop-level pseudo-replication are used. With five seeds, all effect
summaries remain descriptive and uncertain.
