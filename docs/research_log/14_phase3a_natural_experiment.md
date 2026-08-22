# Phase 3A Stage B: Natural Experiment Analysis

Date: 2026-08-22

## 1. Objective

Using only existing Phase 2C data (no new runs), examine whether the revisit
realization quality of the 21 active loops is associated with the two Phase 2C
bottlenecks: **C3 candidate-chain insufficiency** (chain too short) and **D1
coarse-response rejection** (coarse < 0.60). All features are descriptive; no model,
no threshold tuning, no GT-based method input.

## 2. Data and feature definitions

Inputs: `results/phase2c/map3/seed_21xxx/` (diagnostics, rosout, trajectory_gt.txt,
trajectory_slam.txt) + `active_loop_confirmed_taxonomy.csv`.

Per-loop realization features (see `tools/analyze_phase3a.py`, output
`results/phase3a/analysis/loop_realization_features.csv`):

- **Planned history path** (from `PHASE2_LOOP_PLANNED`): waypoint count, polyline
  length, mean/max waypoint spacing, heading change.
- **Actual execution** (GT within loop [start, finish]): path length, sim duration,
  keyscan count.
- **Actual→history fidelity**: per-GT-sample distance to the planned-history polyline
  (mean / median / p90 / max).
- **Spatial overlap**: fraction of actual samples within 0.5 / 1.0 / 2.0 m of the
  history polyline; longest continuous run of within-1 m samples (continuous overlap).
- **Orientation consistency**: per-actual-sample absolute yaw difference to the nearest
  pre-loop SLAM pose (mean / median / p90; fraction < 0.26 / 0.52 / 0.78 rad). All yaw
  from trajectories (never the invalid diagnostics `scan_yaw`, see Audit 5).
- **Karto opportunity persistence**: fraction of loop keyscans with ≥ 1 chain of size
  ≥ 4 ("valid-chain fraction"), longest consecutive valid-chain keyscans, max chain
  size.
- **Matcher persistence**: best coarse response per keyscan; fractions ≥ 0.4 / 0.5 /
  0.6; longest consecutive keyscans with best coarse ≥ 0.5.
- **Vote counts** (C1/C2/C3/D1/D2/D4/ACCEPTED), deepest stage, dominant stage.

## 3. Results

### 3.1 Per-subclass summary

| Feature | C3 (n=12) | D1 (n=8) | S (n=1) |
|---|---:|---:|---:|
| history path length (m) | 3.11 | 5.03 | 4.81 |
| mean waypoint spacing (m) | 0.67 | 0.98 | 0.96 |
| actual→history median dist (m) | 4.28 | 3.42 | 4.78 |
| spatial overlap ≤1 m | 0.34 | 0.30 | 0.34 |
| continuous overlap ≤1 m (samples) | 139 | 158 | 223 |
| yaw-diff median (rad) | 1.45 | 1.27 | 0.56 |
| valid-chain fraction | 0.22 | 0.63 | 0.59 |
| max chain size | 6.1 | 7.0 | 8 |
| best coarse response | 0.45 | 0.40 | 0.66 |

### 3.2 Correlations (n=21, descriptive)

| Realization feature | vs best coarse | vs valid-chain fraction | vs longest consec. valid chain |
|---|---:|---:|---:|
| history path length | −0.29 | **+0.67** | **+0.54** |
| mean waypoint spacing | −0.39 | **+0.65** | **+0.56** |
| max waypoint spacing | −0.45 | **+0.64** | **+0.57** |
| spatial overlap ≤1 m | +0.22 | −0.35 | −0.42 |
| yaw fraction < 0.52 | −0.14 | +0.25 | −0.15 |

### 3.3 Same-vertex replications (BQ4)

| Vertex | Seeds | Outcomes | Pattern |
|---|---|---|---|
| 8 | 21001/2/3/4/5 | C3,C3,C3,C3,C3 | **consistent C3** (best coarse 0.47–0.53) |
| 15 | 21001/3/4/5 | D1,D1,D1,D1 | **consistent D1** (best coarse 0.32–0.40) |
| 26 | 21001/4/5 | S, C3, C3 | **mixed** (realization-dependent) |
| 35 | 21004/5 | C3, D1 | mixed |
| 22 | 21004/5 | D1, D1 | consistent D1 |

### 3.4 Matched case (success s21001 l4 v26 vs similar failures)

| Loop | Outcome | yaw-med (rad) | cont. overlap | valid-chain frac | best coarse |
|---|---|---:|---:|---:|---:|
| s21001 l4 v26 | **S** | **0.56** | 223 | 0.59 | **0.66** |
| s21004 l2 v26 | C3 | 2.36 | 84 | 0.28 | 0.43 |
| s21005 l2 v26 | C3 | 1.76 | 228 | 0.07 | 0.48 |
| s21004 l3 v35 | C3 | 0.06 | 256 | 0.44 | 0.42 |
| s21004 l4 v22 | D1 | 0.84 | 39 | 0.65 | 0.57 |
| s21005 l3 v35 | D1 | 0.18 | 172 | 0.61 | 0.41 |

## 4. Answers to the natural-experiment questions

### BQ1 — Is there an interpretable association between revisit realization and candidate/chain availability (C-stage)?

**Supported (descriptive).** The valid-chain fraction separates C3 (0.22) from D1
(0.63), and it correlates positively with the *length* of the planned history path
(r = +0.67) and its waypoint spacing (r = +0.65). The interpretable mechanism: Karto
chains are built from consecutive *graph-linked* historical scans in the current
scan's neighborhood; forming a chain of size ≥ 4 requires the revisit to generate a
contiguous string of scans that each overlap the history graph. Longer coverage of the
history path supplies that string. Notably, **proximity is not the driver**: spatial
overlap ≤ 1 m correlates *negatively* with chain availability (r = −0.35) — e.g.,
s21001 l3 (v8) had the highest overlap (0.66) but the lowest valid-chain fraction
(0.04). A revisit that stays close to a short history segment produces few
chain-eligible scans. The current active-loop revisit frequently does exactly this.

### BQ2 — Is there an interpretable association between revisit realization and matcher response (D-stage)?

**Weakly supported / inconclusive.** D1 loops do reach the matcher (valid-chain
fraction 0.58–0.80) yet their best coarse response clusters in [0.30, 0.57] — always
below the 0.60 gate — across widely different realization qualities. Within D1 loops,
better orientation consistency does not systematically raise the coarse response
(e.g., s21005 l3 yaw-med 0.18 → coarse 0.41, while s21004 l4 yaw-med 0.84 → coarse
0.57). The coarse response is dominated by scan-content similarity at the matched
*candidate poses* (which heading-dependent laser geometry at candidate locations),
which trajectory-level realization features do not capture. This is precisely the D1
bottleneck: the revisit never produces a scan scoring ≥ 0.60 against any candidate.

### BQ3 — How does the single success differ from the failures?

**Supported (descriptive, n=1).** The only success (s21001 l4 v26) is the only loop
with best coarse ≥ 0.60 (0.66), and differs from failures by: best orientation
consistency (yaw-med 0.56 vs 1.3–2.4 in most failures), long continuous overlap (223
samples), and a high valid-chain fraction (0.59) *jointly*. Same-vertex s21005 l2 v26
matched its continuous overlap (228) but still failed (valid-chain fraction 0.07,
coarse 0.48), so continuous spatial overlap is necessary but not sufficient —
orientation consistency and the timing of the revisit relative to scan-graph
connectivity appear decisive. With n=1 this is descriptive only.

### BQ4 — Are same-vertex replications consistent?

**Mixed.** Vertices 8 and 15 are replication-stable (v8 → C3 in all 5 seeds; v15 → D1
in all 4 seeds), showing vertex geometry sets a *baseline* mechanism. Vertex 26 is
realization-dependent (S in s21001, C3 in s21004 and s21005), and vertices 35 and 22
also vary. Conclusion: the bottleneck is partly vertex-determined and partly
realization-determined; a realization-only fix cannot help vertices whose geometry
determines the mechanism (v8, v15), but for realization-dependent vertices (v26) a
better revisit could change the outcome.

## 5. Synthesis

1. **C3 is a coverage problem, not a proximity problem.** Chain continuity requires
   re-traversing a contiguous stretch of the history graph; the active-loop revisit
   often stays near the history but covers little, so chains stay < 4.
2. **D1 is a scan-content problem.** The matcher is reached, but no scan at any
   candidate pose scores ≥ 0.60, regardless of measured trajectory-level realization
   quality.
3. **The success jointly had**: consistent orientation, long continuous overlap, and
   persistent valid chains. This is the "sustained, matchable historical re-observation"
   the Phase 3A hypothesis describes.
4. **Vertex-dependent baseline**: some vertices (8, 15) are mechanism-stable across
   replications; a realization-only intervention is unlikely to change their outcome.

## 6. Success criterion

Spec: "21 loops show interpretable association between revisit-realization features and
candidate/matcher state."

**Met (descriptively)**: valid-chain fraction vs history-path coverage (BQ1) and the
coarse-response floor in D1 loops (BQ2) are interpretable associations grounded in the
Karto mechanism; the success case (BQ3) shows the joint signature; same-vertex
replications (BQ4) bound the vertex-dependent baseline. All associations are
descriptive (no statistical model); n=1 success keeps BQ3 descriptive.

Proceed to Stage C (minimal causal/oracle experiment): V0 vs V1 history-trace revisit,
holding loop selection, planning, Karto, and all thresholds fixed.
