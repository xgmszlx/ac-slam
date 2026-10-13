# Doc 79 review packet

`DOC79_SYNCHRONOUS_REVISIT_OBSERVATION_VALIDATION` — bounded prospective
technical + mechanism diagnostic. Branch `research/phase4c-formal`, review
baseline `cac55c4bb817705529bee6f39fbdf7cfb698677c`. All paths below are
relative to this results root unless prefixed.

Primary references

- research log: `docs/research_log/79_synchronous_revisit_mechanism_validation.md`
- frozen protocol: `protocol/preregistration.json`, `protocol/frozen_run_manifest.json`,
  `protocol/frozen_hashes.json`, `protocol/frozen_analysis_plan.md`
- final numbers: `analysis/final_gate.json`, `analysis/*.csv`
- figures: `figures/fig1..fig6` (png+svg)

## 1. What was tested

Within an 8-attempt budget, Doc 77's continuous-revisit direction contrast
(`L+` vs `L-` at places B and C) was re-measured with a synchronous
observation chain replacing the Doc 77/78 topic-silence snapshots:

1. native-scan processing barrier (mapper-side telemetry, same single-threaded
   executor as the scan callback),
2. serialized provenance flush + synchronous pose-graph dump in one service
   (`/Mapper/doc79_sync_boundary_export`),
3. 9 per-boundary export checks; old `/mapper/pose_graph` topic cache captured
   at the same instant **for structural comparison only**.

Questions answered: (a) did old topic graphs miss Karto-accepted
scans/constraints; (b) does the B/C direction contrast survive synchronous
measurement; (c) where do action differences first arise; (d) which constraints
carry the information; (e) is there pre-action explainability; (f) any
localization/cost value.

## 2. Headline results (raw values, no significance claims)

Direction-contrast under `SYNCHRONOUS_DUMP` measurement (action-stage `J_T`
increment):

| run | action | rotation rad | ΔJ_T action | historic links | attribution |
| --- | --- | --- | --- | --- | --- |
| B_Lminus_1 | L- | 3.401 | +0.02253 | 5 | +0.02253 |
| B_Lminus_2 | L- | 3.745 | +0.00993 | 5 | +0.00993 |
| B_Lplus_1 a02 | L+ | 3.800 | +0.28332 | 11 | +0.28332 |
| B_Lplus_2 | L+ | 3.429 | +0.34938 | 11 | +0.34938 |
| C_Lminus_1 | L- | 3.447 | +0.00237 | 5 | +0.00237 |
| C_Lplus_1 | L+ | 3.831 | +0.12441 | 6 | +0.12441 |
| C_Lplus_2 | L+ | 3.404 | +0.10642 | 4 | +0.10642 |

Per-pair L+−L−: B `0.2608 / 0.2734 / 0.3268 / 0.3394`; C `0.1220 / 0.1041` —
all positive.

Topic-cache deficit vs synchronous dump (all 28 boundaries): node deficit
0–4, edge deficit 0–10; **every** missing node/edge is tail-incident (newest
accepted keyframes); zero missing edges among old nodes; missing edges include
historic links (`[55,137] [56,138] [59,139] [70,132] [71,133] [72,136]`).

Verdict: `A CONDITIONAL_EFFECT_CANDIDATE` (restricted) — effect replicated in
both places; current form is a **directional asymmetry (L+ > L- everywhere
observed)**, not an observed place-switching effect. Worth developing a
minimal rule: **not yet** (no pre-action discriminator found). Single next
step recommendation: `MECHANISM_OBSERVATION_ONLY`.

## 3. Protocol freeze and deviations

- Freeze moment: protocol files were written and hashed before attempt 1
  (`protocol/frozen_hashes.json` original 7 files; `analysis.py`/`figures.py`/
  `checks.py` hashes were added after code completion and **before any result
  inspection**; no run configuration changed afterwards).
- Order fixed by `suite.py` `PLAN_ORDER`; seeds identical per condition
  (44016/44013/44026/44025); no parameter/threshold edits; no run deleted;
  failure kept as attempt_01 and retried as attempt_02.
- Storage policy: the repository-level `.gitignore` (existing convention, Doc
  77/78 inclusive) keeps all `results/**/*.jsonl`, `results/**/*.log`,
  `results/**/*.pgm`, `results/**/*.pickle` in the local archive. No file was
  force-added: 99 local-only files (381 MB, incl. the 8 `scan_stream.jsonl` at
  22–52 MB each) are listed with SHA-256 in `analysis/local_only_files.csv`.
  All non-ignored artifacts (graphs, manifests, specs, CSVs, trajectories,
  `pose_graph.g2o`, `final_map.yaml`, figures, protocol, analysis) are
  committed.
- C_Lminus_2 never executed (budget); treated as `NOT_STARTED`, not as missing
  data to be back-filled.
- Figures: `figures.py` had two x-tick alignment fixes (fig2, fig6) and one
  legend-color fix (fig6 panel B) applied after the first render, **before
  commit**; all plotted values are unchanged and every figure was regenerated.
  The updated hash is recorded in `protocol/frozen_hashes.json`
  (`figure_fix_note`).

## 4. Complete attempt ledger (8/8 budget consumed)

| # | episode | attempt | outcome | reason |
| --- | --- | --- | --- | --- |
| 1 | D79_B_Lplus_1 | attempt_01 | FAILED (physical) | MoveTo history_03 success but GT 0.771 m > 0.750 m |
| 2 | D79_B_Lplus_1 | attempt_02 | SUCCEEDED | 4/4 boundaries all_checks_passed |
| 3 | D79_B_Lminus_1 | attempt_01 | SUCCEEDED | 4/4 |
| 4 | D79_C_Lminus_1 | attempt_01 | SUCCEEDED | 4/4 |
| 5 | D79_C_Lplus_1 | attempt_01 | SUCCEEDED | 4/4 |
| 6 | D79_B_Lminus_2 | attempt_01 | SUCCEEDED | 4/4 |
| 7 | D79_B_Lplus_2 | attempt_01 | SUCCEEDED | 4/4 |
| 8 | D79_C_Lplus_2 | attempt_01 | SUCCEEDED | 4/4 |

`suite_state.json`: `PAUSED_ON_TECHNICAL_FAILURE`, halt reason
`budget exhausted (8 attempts)`; 7 technically validated runs.

## 5. Eligibility thresholds and failure records

Technical qualification (`run_manifest.json` / `boundary_manifest.json`):
watermark satisfied; `mapper_received >= driver_scans`; mapper accepted count
== driver keyscan events; export success; path match; flush complete; file
parses; run_id match; counts match. All 28 boundary exports passed; per-run
scan identity: 0 duplicates/regressions (3489–3778 scans, 134–142 keyscans
matched by `PHASE2C_KEYSCAN_ACCEPTED`). Physical gate (unchanged from Doc 77):
`goal_position_tolerance_m 0.75` / heading tolerance; failure record path
`runs/D79_B_Lplus_1/attempt_01/episode_result.json`.

## 6. Core data paths

- runs: `runs/<episode_id>/attempt_NN/` (spec, route, params, streams,
  `boundary_manifest.json`, `graph_*_sync.json`, `graph_*_topic.json`,
  `karto_edge_provenance.jsonl`, `native_processing_ledger.jsonl`,
  `run_manifest.json`, ros logs, result)
- analysis: `analysis/run_ledger.csv`, `technical_eligibility.csv`,
  `boundary_integrity.csv`, `scan_identity_audit.csv`, `topic_vs_sync_graph.csv`,
  `constraint_provenance_audit.csv`, `action_mechanism.csv`,
  `per_episode_metrics.csv`, `place_direction_comparison.csv`,
  `corrected_gt_metrics.csv`, `pre_action_feature_audit.csv`,
  `cost_quality_comparison.csv`, `final_gate.json`, `local_only_files.csv`
- code: `tools/realizability_pilot/doc79_sync_validation/` (suite, driver,
  runner, checks, analysis, figures, tests), overlay `doc79_ws/`
  (patch diff: `audit/observability_patch.diff`)

## 7. Primary vs diagnostic boundary

Primary: synchronous dumps only (`gain_source=SYNCHRONOUS_DUMP`);
provenance-attributed historic-link contributions.
Diagnostic (excluded from primary columns):
`FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC` sub-graph/edge-removal values; topic
caches used **only** for the structural topic-vs-sync comparison; GT families
computed only with pre-action alignment; rejection causes marked
`REJECTION_CAUSE_NOT_OBSERVABLE`. `checks.check_gain_sources_agree` guards
mixing.

## 8. Local-only files (SHA-256 in `analysis/local_only_files.csv`)

99 files (381 MB) covered by the repository `.gitignore`: 8 ×
`scan_stream.jsonl` (22–52 MB each, full LaserScan payloads), 8 ×
`gt_stream.jsonl`, 8 × `keyscan_stream.jsonl`, 8 × `loop_events.jsonl`, 8 ×
`karto_edge_provenance.jsonl`, 7 × `native_processing_ledger.jsonl`, 38 logs
(`rosout.log`, `roslaunch.log`, `roscore.log`, `driver.log`, `map_saver.log`),
7 × `final_map.pgm`, 7 × `author_outputs/prior_map_*.pickle` (4,579 bytes each;
identical SHA-256 `332033d1...` across completed runs). The registry file
itself is committed. Everything not listed there is committed.

## 9. Regression runs

- `tools/realizability_pilot/doc79_sync_validation/test_doc79.py`: 31/31 OK
- `tools/realizability_pilot/continuous_revisit/test_continuous_revisit.py`: 19/19 OK
- `tools/realizability_pilot/continuous_boundary_review/test_boundary_review.py`: 13/13 OK
- production binaries unchanged before/after (`audit/production_integrity*.json`)
- Doc 77/78 roots and v14/CD artifacts untouched (`git status` limited to
  Doc-79 paths + the two pre-existing user-modified `tools/realizability_pilot`
  files which were **not** committed)

## 10. Unresolved questions / possible counterexamples

- No causal control: return-leg (pre-action) states differ between paired runs
  (C_Lplus_2 return contribution +0.1772 vs C_Lminus_1 +0.0298); a matched
  pre-action reproduction is not available in this protocol.
- No place with L- ≥ L+: the "conditional switching" framing may be wrong;
  alternative explanation (global directional asymmetry for this sensor/map
  family) is live.
- Topic-staleness magnitude effect on Doc 77's exact numbers is unquantified
  here (structural deficit only).
- Pre-action features tested are two candidates only; other pre-action
  observables could exist (untested = unknown, not non-existent).
- n=2 per (place,direction) cell; C L- n=1; one episode unexecuted.

## INDEPENDENT_REVIEW_HANDOFF

Reviewer instructions: verify each item from the committed artifacts before
accepting §2; report contradictions with file+line references.

1. **Protocol and freeze moment** — `protocol/preregistration.json` (decision
   & stop rules, forbidden inferences), `frozen_run_manifest.json`,
   `frozen_hashes.json` (hashes: suite/driver/runner/checks + analysis/figures
   added pre-inspection), `frozen_analysis_plan.md`. Confirm order, seeds,
   budget semantics.
2. **Code/build changes** — `audit/observability_patch.diff` (188 lines,
   observation-only), `audit/build_manifest.json`, `audit/runtime_provenance.json`;
   overlay is isolated (`doc79_ws/`), production hashes unchanged
   (`audit/production_integrity.json` vs `..._after.json`).
3. **Attempt ledger completeness** — `suite_state.json`, per-attempt
   `run_state.json`/`episode_result.json`/`run_manifest.json`; the failed
   attempt_01 is preserved (no deletion/numbering gaps).
4. **Eligibility and failure records** — `analysis/technical_eligibility.csv`,
   `analysis/boundary_integrity.csv` (all_checks_passed, failed_checks),
   `analysis/scan_identity_audit.csv`.
5. **Core data paths** — §6 above; every figure is regenerable by
   `analysis.py` + `figures.py` from committed files only.
6. **Primary/diagnostic boundary** — `analysis/per_episode_metrics.csv`
   (`gain_source`), `action_mechanism.csv` (`diagnostic_label`), checks guard
   in `checks.check_gain_sources_agree`.
7. **B/C per-run results** — table in §2 vs `analysis/place_direction_comparison.csv`
   and `per_episode_metrics.csv`; verify signs of every L+−L− group.
8. **Local-only files** — `analysis/local_only_files.csv` (paths, bytes,
   SHA-256); ask the author for the files themselves if bit-level verification
   is required.
9. **Unresolved questions** — §10; check that no document claims causality,
   place-conditioning, GT benefit, or predictability.
10. **Counterexamples / falsifiers** — find any run where a missing topic edge
    is NOT tail-incident (`topic_vs_sync_graph.csv`), any boundary failing
    `all_checks_passed`, or any historic-link attribution gap
    (`closure_contribution != historic_contribution` beyond 1e-12).

**Reviewer questions (please answer explicitly):**

1. Does the synchronous chain as implemented actually close the Doc 78
   measurement gap (late-published edges / missing dumps), or does any
   residual channel remain (e.g., topic cache used anywhere in primary values)?
2. Is the tail-only deficit pattern (0–4 nodes / 0–10 edges, all tail-incident)
   sufficient to conclude the old topic graphs "missed Karto-accepted
   scans/constraints", and is any stronger claim made anywhere?
3. Given return-leg asymmetry between paired runs, is the label
   `A CONDITIONAL_EFFECT_CANDIDATE` (restricted) the strongest supportable
   verdict, or should it be downgraded/upgraded?
4. Is `MECHANISM_OBSERVATION_ONLY` the right single next step versus
   `TEST_MINIMAL_PRE_ACTION_RULE`, given the pre-action features show no
   separation?
5. Does the budget accounting (8/8 consumed; C_Lminus_2 NOT_STARTED) and the
   storage policy (existing `.gitignore` convention: 99 ignored files incl. all
   raw streams/logs, registered with SHA-256; no force-adds) meet the Doc 79
   constraints?
