# Doc-79 frozen analysis plan (written before the first run)

All primary information values are computed from the **synchronous** dumps
(`graph_*_sync.json`).  The old-topic caches (`graph_*_topic.json`) are used
only for the topic-vs-sync comparison table.  Gains computed on any other
basis (including edge-removal or fixed-linearisation subgraphs) are labelled
`FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC` and never mixed with synchronous values
(guard enforced by `checks.check_gain_sources_agree`).

## Tables (analysis/)

| file | content |
| --- | --- |
| `run_ledger.csv` | every attempt: episode, attempt, run_id, started/finished, status, technical validity, run dir, budget counters |
| `technical_eligibility.csv` | per boundary: all checks, watermark, export/run_id/counts/sha, provenance state, ledger coverage |
| `scan_identity_audit.csv` | per run: seq duplicates/regressions, stamp monotonicity, received vs driver count deficit, accepted vs keyscan consistency |
| `boundary_integrity.csv` | per boundary: watermark stamp/seq, telemetry at export, topic cache age, sync counts, provenance record count |
| `topic_vs_sync_graph.csv` | per run x boundary: topic/sync node+edge counts, `nodes_only_in_sync`, `edges_only_in_sync`, publication lag |
| `constraint_provenance_audit.csv` | per run: record counts by provenance enum, duplicate sequences, edges without records, match-response coverage; rejection cause = `REJECTION_CAUSE_NOT_OBSERVABLE` |
| `action_mechanism.csv` | per run x stage: new edges in the sync difference, split by provenance enum and by "endpoint in previous graph" (historic link vs local-only), creation times, individual J_T contributions (diagnostic label included) |
| `per_episode_metrics.csv` | the core result table of section 9.2 (all fields, raw values per episode, no aggregation) |
| `place_direction_comparison.csv` | B/C x L+/L− : raw pairs, means, spreads, pre-state differences |
| `corrected_gt_metrics.csv` | SE(2) relative pose error (translation+rotation), robot GT error at arrival/action-end/final, frozen-target map error, alignment parameters, `GT_EFFECT_NOT_ESTIMABLE` markers |
| `pre_action_feature_audit.csv` | the two allowed pre-action candidates: historical direction overlap and residual rotation/translation to the keyframe gate, per run, with the post-action outcome kept in separate columns |
| `cost_quality_comparison.csv` | rotation, motion time, observation duration, information increment and GT change per run |

## Metric definitions

- `J_T`: target-state log-det score (`-logdet(marginal)/15`, five frozen target
  states, anchored at the lowest state id), identical to the frozen Doc-77
  implementation, applied to the synchronous graphs.
- Stage increments: `delta_J_return = J_T(arrival_sync) - J_T(before_sync)`,
  `delta_J_action = J_T(action_done_sync) - J_T(arrival_sync)`,
  `delta_J_tail = J_T(final_sync) - J_T(action_done_sync)`.
- SE(2) relative error `T_error = inv(T_rel_gt) * T_rel_est` with
  `T_rel = inv(T_anchor) * T_robot`; errors reported as translation norm and
  wrapped heading.  Frame consistency (map/odom/base/laser, GT point) is
  asserted before use; mismatches are reported, not patched.
- GT alignment: one rigid map->GT transform fitted on pre-action scans only
  (history + return), reused unchanged afterwards.

## Decision gate

1. Technical: `MEASUREMENT_VALIDATED` only if every run used for comparison
   passes `technical_check` (barrier, export, provenance, GT identity).
2. Science (after 1 passes): map the observed pattern onto
   A `CONDITIONAL_EFFECT_CANDIDATE` / B `MECHANISM_ONLY` /
   C `PURE_ROTATION_NOT_SUPPORTED` / D `TECHNICALLY_INCOMPLETE`, using the raw
   per-run values (two runs per condition, no significance testing), the two
   pre-action candidates, and the cost/quality table.
3. Forbidden inferences (section 9.4) are checked against the written text
   before the handoff packet is finalised.

## Figures

1. topic vs sync per boundary (nodes/edges lag, missing historic links)
2. B/C L+/L− synchronous information gains (every run shown)
3. mechanism: accepted keyframes, provenance-classified edges, historic vs
   local-only endpoints
4. zero-gain vs effective run contrast (real constraint endpoints)
5. GT error vs information increment (pre/post comparable positions)
6. decision-evidence summary (direction contrast, pre-action explanation
   power, cost)
