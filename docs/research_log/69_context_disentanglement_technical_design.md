# 69 — Context-disentanglement technical and statistical certification

## A. Provenance

This task is `CONTEXT_DISENTANGLEMENT_TECHNICAL_AND_STATISTICAL_CERTIFICATION` (`CD-T`). It is a technical and design certification, not a scientific experiment.

- Source branch: `research/phase4c-formal`.
- Source local and remote HEAD at freeze: `ae8cbb1afd766ddaab03540a7cb7f6dd41aa110d`.
- Frozen v14 tree: `82c934201e75dc42c9718455c860fa1cc4f2630e`.
- Frozen v14 heterogeneity tree: `720779e2eb2efb1bf253df051207e675ae26e31b`.
- All 14 critical v14 SHA256 checks passed before certification and the frozen v14 and v14-H worktrees remained clean.
- The formal scientific state remains `V14_PROSPECTIVE_NO_SUPPORT`; `UNIVERSAL_BROAD_SWEEP_HYPOTHESIS` remains `STOPPED`; the post-confirmatory direction remains `MULTIFACTOR_INTERACTION_CANDIDATE`.
- The frozen protocol SHA256 is `416596725551d4e2eb7da61284850b665cbc2ad894d30e823a85dcc8c8fc6289`; all six frozen code hashes matched after the run.

One interrupted attempt ended before producing a complete branch. It was moved intact to `technical/interrupted_attempts/20260928T094948Z/target_A/H1/D0_ZERO` and is excluded from the 24-branch certification table. The completed run used a fresh ROS master and fresh Stage instance per branch. Karto and every scientific backend endpoint remained disabled.

Canonical evidence is under `results/realizability_pilot/p1_context_disentangle_t_20260928/`. Neither `p1_v14_confirmatory_20260928` nor `p1_v14_heterogeneity_20260928` was modified.

## B. Dose intervention definition

The prospective intervention uses three newly named controlled angular-dose arms:

| Arm | Planned cumulative post-start yaw | Common motion template |
|---|---:|---|
| `D0_ZERO` | 0 rad | static at `theta0` |
| `D1_THRESHOLD` | 1.087946562824985 rad | `theta0 -> theta0 + D1/2 -> theta0` |
| `D2_HIGH` | pi rad | `theta0 -> theta0 + D2/2 -> theta0` |

Every arm starts at the same block-specific `(x, y, theta0)` and finishes at `theta0`. Every nonzero arm uses positive outbound and negative return rotation; direction is fixed across target, block, and dose and is therefore not an additional factor. D1 and D2 share maximum angular speed 0.65 rad/s, proportional gain 1.8, 0.018 rad heading tolerance, three stable cycles, 0.05 s control period, and identical zero-twist semantics. The only planned arm difference is cumulative angular dose; D0 is static.

## C. Why this is not A2 replication

D1's numerical dose is derived from the v14 A3 median planned post-arrival angular path, and D2's dose is derived from the v14 A2 median but standardized to pi. The old A1/A3/A2 action packages had target-confounded realized yaw, completion exposure, and endpoint realization. CD-T instead imposes one common start/final-orientation geometry and a deterministic dose-only manipulation on both targets. It therefore does not reproduce the complete old A2 package, and the A1/A3/A2 terminology must not be used for future arms.

## D. Fixed-N technical certification

All old public Target A/B H1-H4 geometries were exercised with D0/D1/D2: 24 planned branches, 24 complete, and 24 `TECHNICALLY_VALID`. Every branch captured the exact first `N = 347` scientific scans, had monotonic unique timestamps, completed before N, returned within the 0.04 rad final-heading tolerance, and raised no controller exception. The observed minimum completion margin was 265 scans, exceeding the frozen minimum of 60.

| Target | Arm | Actual cumulative yaw range [rad] | Completion scan range | Completion margin range | Duration range [s] | Moving scans | Final-heading residual [rad] |
|---|---|---:|---:|---:|---:|---:|---:|
| A | D0 | 0 | 3 | 344 | 0.30 | 3 | 0.01358–0.01726 |
| A | D1 | 1.05016–1.05699 | 48–50 | 297–299 | 4.80–5.00 | 48–50 | 0.01607–0.01750 |
| A | D2 | 3.10232–3.11968 | 80–82 | 265–267 | 8.00–8.10 | 80–82 | 0.01098–0.01790 |
| B | D0 | 0 | 3 | 344 | 0.30 | 3 | 0.01552–0.01733 |
| B | D1 | 1.04934–1.05827 | 49–50 | 297–298 | 4.90–5.00 | 49–50 | 0.01540–0.01688 |
| B | D2 | 3.10712–3.11114 | 81 | 266 | 8.00–8.10 | 81 | 0.01248–0.01624 |

All eight within-block checks satisfy strict `D0 < D1 < D2`. The nonzero actual-dose error remains within the frozen +/-0.06 rad tolerance, and D0 is exactly zero.

## E. Target-dose deconfounding check

The machine label is `DOSE_TARGET_DECONFOUNDING_TECHNICALLY_CERTIFIED`.

- D0: A and B actual-dose ranges are both exactly 0; completion scan ranges are both exactly 3.
- D1: A range 1.05016–1.05699 rad and B range 1.04934–1.05827 rad fully overlap relative to the smaller range. Target mean absolute difference is 0.000725 rad. Completion scan ranges 48–50 and 49–50 overlap.
- D2: A range 3.10232–3.11968 rad and B range 3.10712–3.11114 rad fully overlap relative to the smaller range. Target mean absolute difference is 0.001299 rad. Completion scan ranges 80–82 and 81–81 overlap.

Thus target is not separated by realized dose or maneuver-completion range in this technical sample. This certifies manipulation feasibility only; it does not establish a scientific target-by-dose effect.

## F. Sample-size sensitivity and selected future n

The design-only Monte Carlo sensitivity used 50,000 repetitions with seed 280928, candidate sizes 4/6/8/10/12 blocks per target, effects at 100%, 50%, and 25% of the exploratory v14 interaction scale, and empirical/1.5x/2x variance. The v14 scale is explicitly exploratory and target-confounded, so these simulations are planning inputs rather than prior evidence.

The frozen choice is 8 blocks per target (16 independent blocks, 48 repeated-measure branches). Under the conservative 2x-variance scenario at n=8:

| Effect scenario | Approximate power | Sign stability | Median 95% CI half-width |
|---|---:|---:|---:|
| observed scale | 1.000 | 1.000 | 0.1303 |
| 50% scale | 0.840 | 0.9997 | 0.1305 |
| 25% scale | 0.321 | 0.9549 | 0.1304 |

This is the smallest candidate satisfying the frozen rule: observed-scale power at least 0.95, half-scale power at least 0.80, and quarter-scale sign stability at least 0.95 under 2x variance. The weak 0.321 quarter-scale power is an explicit residual risk, not evidence that small effects are adequately powered.

Fresh candidate pools are Target A seeds 101001–101016 and Target B seeds 102001–102016. Future selection is full outcome-blind technical qualification followed by the first eight eligible seeds in frozen order; scientific-outcome replacement is forbidden.

## G. Frozen primary interaction estimand

The canonical-history block is the statistical unit. Dose is a within-block repeated measure; Target A/B is a between-context stratum. The primary block contrast is:

`C_HT(block) = J_T(D2_HIGH) - J_T(D1_THRESHOLD)`

The primary interaction is:

`I_HT = mean_B(C_HT) - mean_A(C_HT)`

There are no co-primary pairwise contrasts. `J(D1)-J(D0)` and `J(D2)-J(D0)`, plus their B-minus-A interactions, are secondary. Future inference must preserve within-block pairing using a block bootstrap or paired/randomization procedure stratified by target. Treating 48 branches as independent observations is forbidden; mixed models are auxiliary only.

## H. Mechanistic secondary endpoints

Future branches are designed to record accepted keyscans, E_T, E_N, historical-factor total, historical endpoint set, endpoint novelty/loss, insertion geodesic, hops, cycle length, information eigenvalues, matcher response, and provenance family. The secondary contrasts are `H_HT = HistoricalFactors(D2)-HistoricalFactors(D1)` and `I_HIST_HT = mean_B(H_HT)-mean_A(H_HT)`. These can describe measurement-realization patterns but are not causal-mediation proof.

Capture-side pre-treatment logging records the range histogram, angular range profile, valid-return ratio, range entropy, bilateral symmetry, range quantiles, and geometric openness before the action. It does not alter backend input. Pre-graph descriptors remain future-only because acquiring them here would have required entering the backend path.

## I. Remaining risks

- This technical run used four old geometries per target. It verifies controller feasibility and A/B dose overlap, not outcome generalization to fresh histories.
- The sample-size scale and variance originate in only eight exploratory, target-confounded v14 blocks. Power may be optimistic under different fresh-history variance or smaller effects.
- At the quarter-scale effect, n=8 gives high simulated sign stability but only 0.321 approximate two-sided power under 2x variance.
- Fixed rotation direction removes a direction factor but does not estimate direction sensitivity. This is an intentional protocol restriction, not evidence that direction is irrelevant.
- The dedicated pytest suite requires SciPy and therefore ran in the repository's Conda Python 3.12 environment (13/13 passed). The four new files also compile under `/usr/bin/python3` 3.8, but that system interpreter lacks SciPy for rerunning the design simulation.
- One pre-certification process interruption is archived separately. It generated no complete certification row and is not included in the 24/24 result.

The frozen v14 scientific conclusion is unchanged by every item above.

## J. Gate

All required checks are true: controller 24/24 valid, identical start/final-heading semantics, fixed exposure and minimum margin valid, dose ordering valid, target-dose deconfounding certified, primary estimand and sample-size design frozen, and no scientific endpoint produced.

`CONTEXT_DISENTANGLEMENT_TECHNICALLY_READY`

This gate authorizes no scientific collection by itself; a future formal experiment still requires separate authorization.

## K. Stop statement

`No context-disentanglement scientific experiment was started.`

Reproduction commands for the design checks are:

```bash
PYTHONPATH=tools/realizability_pilot python3 -m pytest -q \
  tools/realizability_pilot/test_context_disentangle.py
```

The dedicated suite passes 13/13 tests. `technical/controller_preflight_summary.json`, `technical/target_dose_deconfounding.json`, and `decision/CDT_gate.json` are the machine-readable certification records.
