# Doc 80 review packet

`DOC80_POSTHOC_DIRECTIONAL_OBSERVABILITY_AND_UTILITY_AUDIT` — pure offline
convergence audit of the Doc-79 continuous-revisit direction study. No ROS, no
new Stage runs, no Karto changes, no model training. Review baseline
`4f290fc0691324e13158d72fa77c18278e28b71e` (branch `research/phase4c-formal`).

## 1. GitHub baseline SHA

- local HEAD == remote `refs/heads/research/phase4c-formal` ==
  `4f290fc0691324e13158d72fa77c18278e28b71e` (Doc-79 commit, fast-forward
  chain from `cac55c4b`).

## 2. Local raw file SHA-256 verification

- `analysis/local_only_files.csv` (Doc-79 registry): 99 files, 381 MB —
  **99/99 verified**, 0 missing, 0 mismatched
  (`audit/local_only_file_verification.csv`); includes 8 `scan_stream.jsonl`,
  all `gt_stream/keyscan_stream/loop_events/provenance/ledger` JSONL, all logs,
  `final_map.pgm`, `prior_map_*.pickle`.

## 3. Were any old data modified?

No. Doc 76–79 artifacts, `final_gate.json`, frozen protocol, figures and the
two pre-existing user-modified files are untouched; this root is new
(`git status` shows only Doc-80 additions).

## 4. Frozen target: topic vs sync comparison

- Reproduction: the exact freeze rule re-run on the executed topic graph
  reproduces anchor/segment/targets in **7/7** runs.
- Switching to `G_before_return_sync` (same reference): **7/7 identical**.
- Laser-frame-corrected reference (+0.2 m along heading): **7/7 identical**.
- Topic graph was missing 1 node at freeze time in 4 runs; the missing node
  never affected the selection.
- Verdict: `ORIGINAL_FROZEN_TARGET_ESTIMAND` robust; the Doc-79 freeze is not
  contaminated (`audit/target_freeze_consistency.csv`,
  `audit/target_freeze_sensitivity.json`).

## 5. GT before/after (target map error)

- Corrected per-target stage means: before_return 0.0153, arrival 0.0158,
  action_done 0.0165, final 0.0165 m (n=35 each).
- Doc-79 original values agree within −0.018…+0.001 m (TF-lag band); the
  original was stage-constant by construction.
- Historical target nodes move by <= 14.2 mm total (mean 3.2 mm in the action
  stage, 0 afterwards) — no stage-dependent optimisation of the targets.
- Robot boundary GT (arrival vs action_done): 6/7 runs at identical GT pose
  (B_Lplus_2 0.31 m apart); localisation-error change −0.008…+0.063 m,
  1 improved / 3 worsened at the ±5 mm level.

## 6. Extrinsics and frame verification

- Karto nodes are map->laser poses (source-verified: `odom->laser` odometric
  pose, corrected pose dumped).
- Recovered base-in-laser transform: x = −0.1993…−0.2000 m, sd <= 0.0067;
  matches Stage `hokuyolaser(pose [0.2 0 -0.2 0])` and
  `geometry.py LASER_OFFSET_X=0.20`.
- Model check against recorded `map_base` at acceptance: mean 0.025–0.048 m,
  max 0.152 m (TF publish lag).
- Dump `index == state_id`, contiguous ids, stable `unique_id` mapping: 7/7.
- Real sensor parameters: FOV 180.0°, 901 beams, range 0–25 m.

## 7. First-visit vs return decomposition of the action gain

- New non-chain edges: A (first-visit) 29, B (return) 18, C (action-internal)
  10. Joint set-level contributions: A 0.897, B 0.025, C 0.029 nats; A
  dominant in 6/7 runs.
- The L+ gains are essentially pure class-A contributions
  (e.g. B_Lplus 0.283/0.349 all from A; C_Lplus 0.124/0.106 all from A).
- Class C is not zero-valued everywhere (B_Lplus_2 C = 0.023).

## 8. Synchronous gain vs fixed-linearization diagnostic

- `closure_contribution == historic_contribution` reproduced to <= 5e-14.
- `delta_J_action_sync − historic_contribution` differs by −3.0e-6…+1.8e-5
  (largest C_Lplus_1) — the two comparisons are reported separately in
  `analysis/doc79_contribution_comparisons.csv`; they must not be merged.
- All sub-graph values carry `FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC`.

## 9. B/C pre-action state differences (arrival graphs)

| run | action | seed | nodes | non-chain edges | J_arrival | return ΔJ |
| --- | --- | --- | --- | --- | --- | --- |
| B_Lminus_1 | L- | 44013 | 137 | 27 | 8.037 | ~0 |
| B_Lminus_2 | L- | 44013 | 135 | 24 | 7.521 | 0.011 |
| B_Lplus_1 | L+ | 44016 | 134 | 30 | 8.093 | ~0 |
| B_Lplus_2 | L+ | 44016 | 134 | 26 | 7.571 | 2.3e-4 |
| C_Lminus_1 | L- | 44026 | 130 | 47 | 9.108 | 0.030 |
| C_Lplus_1 | L+ | 44025 | 129 | 31 | 8.096 | 0.096 |
| C_Lplus_2 | L+ | 44025 | 133 | 40 | 8.131 | 0.177 |

Target clusters are tight (spread 1.04–1.35 m, centroid 0.53–0.80 m from the
robot). Seeds differ between directions at the same place (B 44016/44013,
C 44025/44026): **not** a same-state control.

## 10. Pre-action directional visibility (both directions)

- Swept sectors: 270° each, common 180°, exclusive 90° — from the real 180°
  sensor, wraparound-tested.
- History nodes visible: L+ 94–101, L− 95–99 of 108–114; exclusive counts
  0–4 (L+) and 1–7 (L−); visibility deltas mixed and uncorrelated with the
  executed direction's outcome. Novelty proxy deltas +2.0…−3.5 (m
  `GRAPH_NOVELTY_PROXY`).
- Conclusion: the collected geometry does **not** provide a pre-action
  discriminator; H1 stays a hypothesis without physical backing in this data.

## 11. Unresolvable counterfactual confounds

- Only one direction is executed per state; no `V(L-|s0)` exists.
- Seeded pairing is not state-matching; return-leg states differ (C_Lplus
  return ΔJ 0.096/0.177 vs C_Lminus 0.030).
- Karto rejection causes are not observable (`REJECTION_CAUSE_NOT_OBSERVABLE`).

## 12. Real task-benefit evidence

None found at this scale: corrected target map error does not improve
(<= 0.5 mm mean change, mixed sign), robot boundary localisation change is
mixed (mean +0.0098 m, 3 worsened / 1 improved at ±5 mm), costs are
approximately constant (rotation 3.40–3.83 rad, 34.6 s; B_Lplus_2 has 0.31 m
path). Information gain is a graph-information result, not a task-benefit
result.

## 13. Which competing explanation best fits

H3 (fixed L+ advantage) + H4 (no localisation benefit) fit the observed data
best; H1 (directional visibility) has no measured separation; H2 (pre-action
graph state) cannot be identified with n=2 per cell. See
`analysis/directional_competing_hypotheses.csv`.

## 14. Final research verdict

- Measurement: `SYNC_MEASUREMENT_REUSED_VALID`,
  `TARGET_GT_CORRECTION_VALID`, `PREACTION_FEATURE_INPUT_VALID` — all pass.
- Mechanism: `A HISTORICAL_ASSOCIATION_MECHANISM_SUPPORTED` (attribution to
  first-visit historic links), with the directional-visibility part explicitly
  not identified.
- `analysis/final_research_gate.json` records the full three-level decision.

## 15. Single recommended next step

**`A STOP_PURE_ROTATION_SELECTION`** — stop the pure rotation-direction
selection line as an independent paper direction. The mechanism remains valid
as an observation topic; the decision-relevant ingredient (a pre-action signal
with task benefit) is absent.

## 16. Scripts and test commands

```bash
# full offline pipeline (audit + analysis + gate)
PYTHONPATH=catkin_ws/python:tools/realizability_pilot /usr/bin/python3 \
  -m doc80_offline_review.run_all
# figures
/usr/bin/python3 tools/realizability_pilot/doc80_offline_review/figures.py \
  --suite-dir results/realizability_pilot/p1_doc80_offline_research_convergence_20261013
# doc-80 tests (27)
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/doc80_offline_review/test_doc80.py
# legacy regression (must stay green)
/usr/bin/python3 tools/realizability_pilot/doc79_sync_validation/test_doc79.py
PYTHONPATH=catkin_ws/python /usr/bin/python3 tools/realizability_pilot/continuous_revisit/test_continuous_revisit.py
PYTHONPATH=catkin_ws/python /usr/bin/python3 tools/realizability_pilot/continuous_boundary_review/test_boundary_review.py
```

## MOST_IMPORTANT_UNCERTAINTIES

1. **Scale of the task-benefit test**: the corrected target/robot GT changes
   are at or below the 2–5 cm TF-lag band; a genuinely small localisation
   benefit (mm–cm) cannot be excluded by this data even though none is
   detected. Longer horizon or lower-noise instrumentation could flip Q2/Q7.
2. **Statistical power for the pre-action features**: 7 runs with two
   directions at two places cannot exclude a weak visibility effect that only
   shows in exclusive-sector cases (0–7 nodes); the negative result is
   "no separation observed", not "no effect exists".
3. **Seeded, not state-matched pairing**: if a same-state counterfactual pair
   existed and showed a direction-dependent historic-link effect, the H3
   fixed-policy explanation would lose support and the STOP recommendation
   would need re-opening.

## INDEPENDENT_REVIEW_QUESTIONS

Q1. Does the corrected target GT genuinely use the four stage graphs (not the
    reused historic pose)? Verify in `analysis/corrected_target_map_gt.csv`
    that `node_laser_pose` differs per stage where displacement > 0 and that
    `target_gt_original_comparison.csv` cites both values.
Q2. Was the frozen target affected by the old topic graph or the base/laser
    lever arm? Check `audit/target_freeze_consistency.csv`: reproduction,
    sync-refreeze and laser-refreeze must all equal the original ids.
Q3. Does any unexcluded initial-state confound remain in the direction
    contrast? Confirm the seed pairing table (§9) and that no document claims
    same-state control.
Q4. Do the pre-action features really fail to separate L+/L−? Cross-check
    `analysis/directional_visibility_features.csv` and
    `feature_outcome_join.csv` (delta vs executed direction).
Q5. Is there any necessity to develop a method (predictor/rule) now? Weigh
    §10–§13 and the `STOP` criteria; state explicitly if any evidence
    contradicts the STOP recommendation.
Q6. Should the pure-rotation line continue, or pivot to localisation-
    degradation recovery? Evaluate §10.4 (reusable platform parts vs
    experiments not to repeat) against the gate's `what_would_change_this_verdict`.
