# 73 — CD-F2 prefix numerical reproducibility forensic

Date: 2026-10-08

Scope: `CD_F2_PREFIX_NUMERICAL_REPRODUCIBILITY`, `TECHNICAL_FORENSIC_ONLY`
Final technical gate: **`MULTISTABILITY_CONFIRMED_CAUSE_UNRESOLVED`**

## 1. Provenance and frozen scientific state

The source branch was `research/phase4c-formal` at `770fb1840ef1f918d831d803dcee5e21bd977116`. The original CD run and Amendment 1 retain `CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE`. The v14 scientific gate remains `V14_PROSPECTIVE_NO_SUPPORT`, and the universal broad-sweep hypothesis remains stopped. This forensic study did not publish treatment suffixes, read post-treatment scientific endpoints, compute `J_T` or dose contrasts, modify a planner, or start another CD scientific experiment.

All new files are in `results/realizability_pilot/p1_cd_prefix_forensic_f2_20261008/` and the new F2 scripts. The original CD tree's independently recomputed aggregate is **3,881 files / `0725778cbcd223cea69384350bcedefc965c2bb8c75a32a484e1e7e4d747fd4b`**, matching its frozen expectation. `git diff --exit-code` for original CD, Amendment 1, v14, and v14-H returned clean. Production mapper SHA-256 remained `7ab54496b4572e831d7f10d615ad3d700bec3a0b89c5abdb9c562616a67d92f6` after every stage. This tracked-file check and original-CD aggregate do not independently hash every ignored raw file in Amendment 1/v14; no F2 code writes to those directories.

## 2. Frozen evidence inventory

The nine H1 graphs are the three qualification `repeat_01–03` graphs and six Amendment 1 `graph_pre.json` graphs from D0/D1/D2 attempts 01/02. All are prefix-only snapshots for frozen `target_A_H1`, seed 101002, with **35 nodes and 41 edges**. Their canonical prefix semantic SHA is `5e93546711242a3372044181b9b2766807d6f9029d2d151de32d94cf55cee8ad`; normalized mapper configuration SHA is `511dcacb4ff58a99d0f434cbfd604198c95f453e2bd18e35c0b5e0533437825c`. All six failed formal attempts published and processed 35/35 prefix messages, saved a synchronous prefix graph, and published no suffix.

Inventory, pairwise structure/numerics, first differences, and source paths are machine-readable under `analysis/`. The frozen `technical/prefix_only_run_manifest.json` planned 24 runs before the first process launched; its SHA-256 is `823bd3409bf017d02f30a2502f29ab9e5be0ec9472d26e37d84b57c62eea47c5`.

## 3. Nine-graph cluster verification

The proposed four clusters were independently recovered using identical graph structure plus identical six-decimal serialized numerical node/edge payloads:

| Cluster | Frozen members | Graph SHA-256 prefix |
|---|---|---|
| Q | Q1, Q2, Q3 | `b5251781` |
| R1 | D0 attempt 01 | `7a5162f1` |
| R2 | D0 attempt 02, D1 attempts 01/02, D2 attempt 02 | `2ca0254e` |
| R3 | D2 attempt 01 | `d186475c` |

This is numerical equality **after six-decimal dump**, not C++ bitwise equality. `analysis/nine_graph_cluster_matrix.csv` includes every pair and all five frozen numerical comparison metrics; `analysis/nine_graph_cluster_summary.json` lists full hashes and paths. The six failed formal attempts span three non-Q clusters, rather than one deterministic branch output.

## 4. First divergence and affected state mapping

For five of six formal mismatch graphs, the first serialized node change is state 14, about 2.2 µm in translation; the first changed edge measurement and covariance are edge index 16, `[14,15]`. The Q edge measurement is `(dx,dy,dtheta)=(0.945057,-0.080550,-0.131929)`; the common mismatch is `(0.935238,-0.078657,-0.131929)`. Thus `Δdx=-0.009819 m`, and the full XY measurement difference is almost exactly 0.010000 m. The Q versus common-mismatch provenance `PREVIOUS_SCAN` response is `0.638793` versus `0.636842`. These are actual accepted sequential-match measurements, not merely post-hoc pose-export differences.

The exceptional D2 attempt 01 is different: its first changed covariance is on edge `[12,13]`; its first materially changed measurement is `[13,14]`, and state 14 moves about 0.08246 m. Therefore **scan 15 is not a proven universal origin** of the multistability. The saved final snapshot cannot reveal whether an earlier sub-µm internal perturbation was hidden by six-decimal rounding.

The input has 35 published scans, the graph has 35 sequential accepted state/unique IDs, and the callback barrier reports 35 processed messages. This is strong one-to-one/order evidence that state 15 corresponds to zero-based input record 15 (stamp 1.5 s, odometric x 5.079041 m), and state 14 to record 14 (stamp 1.4 s). It is **not a receiver-side raw-message-index ledger**, so the mapping is recorded as an inference, not direct callback-payload proof. See `analysis/affected_state_mapping.json`, `analysis/node_difference.csv`, `analysis/edge_difference.csv`, and the three real-data PNG figures.

## 5. Serialization precision audit

Production `OpenMapper.cpp` defines `LoopDiagDouble(kt_double)` with `snprintf("%.6f")` and uses it for corrected node poses, edge relative measurements, and covariance in `WritePoseGraphJson`. The Python comparator parses this JSON into binary64 floats and tests decoded differences against zero. A displayed 1e-6 difference can be a rounding-boundary effect; a ~1e-2 m edge difference cannot be **explained solely by serialization**. Conversely, identical six-decimal values do not establish identical internal doubles or search-grid state. `analysis/serialization_precision_audit.json` and `analysis/numerical_observability_limitations.md` record the exact limitation. The old zero-tolerance protocol is unchanged.

## 6. Qualification versus branch lifecycle audit

The archived H1 qualification and all six formal attempts have byte-identical copied canonical prefixes, identical scan stamps, identical recorded production mapper binary and normalized configuration hashes, identical normalized launch semantics after removing only output paths, 35/35 publisher and callback counts, subscriber connection, no fixed sleep drain barrier, and a synchronous graph-dump service. Different launch-file SHA-256 values arise from per-run output destinations, not observed parameter differences. Qualification mode omits the reference gate; formal mode checks it **after** the prefix snapshot. No logged semantic ROS parameter or callback-barrier difference explains the graph split.

The archived records do **not** include receiver-side scan payload hashes, historical process-environment snapshots, CPU affinity, runtime TBB state, or hashes of *all dependent shared libraries*. Current `libOpenKarto.so` and `libMultiMapper.so` modification times predate September 30, but that is not a historical binary-hash certification. Hidden execution differences cannot be excluded. F2 captured current session-level CPU affinity and shared-library *paths*; sessions 1 and 2 match after removing `ldd`'s randomized ASLR load addresses. Early F2 per-run environment hashes included those ASLR addresses and are **not valid semantic-comparison hashes**; `technical/normalized_session_environment.json` is the corrected comparison. F2 mode B faithfully applies the branch's frozen prefix-reference check, but deliberately does not stage or publish treatment suffix data; it therefore tests the prefix gate, not every pre-launch CPU/cache side effect of a full branch replay. See `analysis/lifecycle_equivalence_matrix.csv` and `analysis/lifecycle_equivalence_report.json`.

## 7. Matched technical controls

Control selection was frozen by role, not by scientific outcome: Target A H2 (same Target) and Target B H1 (cross Target). Their six archived first-attempt branch prefix graphs, D0/D1/D2 for each history, are **6/6** six-decimal equal to their respective qualification reference graphs, with structural equality. See `analysis/matched_control_comparison.csv` and `analysis/history_specificity_report.json`. Two controls do not prove all other histories are stable.

## 8. Prefix-only reproducibility: 24/24 completed

Two separate runner invocations each completed 12 preordered runs. Each run owned a fresh ROS master and fresh production mapper process. The experiment was 3 histories × 2 modes × 2 sessions × 2 repeats = **24/24**, with **0 suffix messages**, exact published/processed prefix counts, and structural graph equality in every same-history pair. The plan was not adapted after any observed result.

| History | P qualification-style | B branch-prefix-gate | All current runs equal to old Q |
|---|---:|---:|---:|
| Target A H1 | 0/4 | 1/4 | **1/8** |
| Target A H2 | 4/4 | 4/4 | **8/8** |
| Target B H1 | 4/4 | 4/4 | **8/8** |

H1 produced four distinct serialized graphs in the eight new runs: old Q once, R1 twice, R2 four times, and one new graph (`61ba943f…`) once. Combining nine frozen and eight new H1 graphs gives **five** observed numerical clusters. Both P and B reach non-Q graphs, so branch-only mismatch is contradicted; a single B run reaches Q, so branch mode is not deterministically incompatible with Q. The apparent P/B proportions are too small and not a causal mode effect. See `technical/repetition_results.csv`, `technical/reproducibility_matrix.csv`, `technical/prefix_cluster_membership.json`, and `technical/session_effect_summary.json`.

## 9. One isolated internal matcher trace

Because archived provenance localizes a changed `PREVIOUS_SCAN` response, one focused isolated forensic build was made outside the repository production workspace. Its mapper SHA-256 was `3ea511fb6c5b94fefb2dd8aa9088dda52a3c0d957508e9fad0ec037263506e82`; production stayed `7ab54496…`. The isolated source modification only logs scan-15 coarse/fine search center, search resolution, best and second response, selected pose, and covariance at `max_digits10` precision **after** the original matching/covariance calculation. The four predeclared instrumented prefix-only runs returned three previously seen graph clusters: new `61ba943f…`, R1 `7a5162f1…`, and Q twice. All have two trace records, and none published suffix.

Crucially, the **coarse search center entering scan 15 already differs**: x is 4.9995501169 m in I1, 4.9125080810 m in I2, and 4.9192083148 m in both Q runs I3/I4; the scan-15 odometric input x is 5.0790410042 m in all four. The fine selected responses are 0.6465488544, 0.6368422494, and 0.6387925318 respectively. In Q, the best versus second-best fine response margin is only about `1.34e-5`, but the trace records one best candidate, not a tie. A close runner-up may indicate sensitivity; it does not prove the root cause. Different search centers show that at least one relevant internal state diverged **before** scan-15 candidate selection. The trace does not record the earlier state, complete received scan bytes, or a causal thread interleaving.

Machine-readable outputs: `technical/matcher_divergence_trace.json`, `technical/threading_comparison.json`, and four `instrumented_result.json` files. The observation logic and build details are preserved in `tools/realizability_pilot/cd_f2_matcher_trace_snippet.md`. The original source uses CRLF; the snippet is reproducible in behavior but does not promise byte-identical C++ source or binary. The isolated binary is a diagnostic instrument, **not** an equivalent scientific backend. The generic `unified_replay_result.json` inside these four instrumented directories still describes the production binary path; the `instrumented_result.json` and `instrumented_plan.json` explicitly carry the actual isolated SHA and supersede that one provenance field.

## 10. Competing explanations

| Hypothesis | Supporting evidence | Contradicting/limiting evidence | Causal status |
|---|---|---|---|
| H1: matcher candidate branching | Multiple serialized graph and accepted-match outcomes; different scan-15 search centers and responses | Search center already differs before scan-15 candidate choice; upstream first cause unlogged | Matching-state divergence observed; exact cause **unknown** |
| H2: parallel execution sensitivity | Production uses `OpenMapper(true)` and TBB `parallel_for`; multistability appears with that configuration | No single-thread counterfactual; code writes per-candidate indexed slots; no demonstrated race | **Unknown**, not attributable to TBB |
| H3: qualification/branch lifecycle mismatch | Archived runs differ in nominal mode and output paths | Semantic launch/parameter/input/barrier checks match; both P and B produce multistability; B once returns Q | Branch-only cause **not supported**; hidden state unknown |
| H4: numerical state/serialization | Six-decimal export masks smaller internal changes; Q fine runner-up is close | ~1 cm accepted edge change and distinct responses are real at output precision; pure JSON rounding cannot create them | Pure serialization **not supported**; upstream numerical sensitivity unresolved |

None of these observations establishes a deterministic implementation bug, a thread race, or a 0.01 m-resolution cause. The 0.01 m fine search step is **consistent with** one common difference, not its causal proof. No single-thread build or altered matcher was used as a scientific backend.

## 11. Final technical gate and uncertainties

**`MULTISTABILITY_CONFIRMED_CAUSE_UNRESOLVED`** is the narrowest defensible gate: the same frozen H1 prefix, recorded production mapper binary/configuration, fresh ROS lifecycle, and exact callback barrier led to multiple numerical graph snapshots; two matched controls remained stable. The forensic trace places divergence in or before scan-matching state, but does not identify the initiating variable. We stopped after the planned 24 production prefix runs and one four-run isolated instrumentation pass. No additional repeats were added based on favorable results.

Remaining uncertainties include exact receiver-side message equality; whether sub-six-decimal earlier state differences are amplified by search-grid quantization; the contribution, if any, of TBB scheduling; archived qualification-era environment parity; and the extent to which this H1 sensitivity generalizes to other histories. `target_A_H1` cannot be silently replaced under the frozen CD design. The 45 successful Amendment 1 backend replays do not rescue a missing complete block or authorize the original interaction estimate.

## 12. Recommendation only — no scientific continuation executed

The current exact-prefix Karto design should stay stopped. A later, separately authorized **technical certification** could first establish deterministic graph-state initialization or a different controlled backend/replay architecture, then requalify the complete frozen design under a new protocol ID. If it changes matcher, parallel execution semantics, optimizer, or numerical tolerance, it is a **different backend/measurement protocol** and must not mix outcomes with old CD science. An independently measured numerical envelope would require new same-input/same-config/same-lifecycle repeats and evidence that the allowed prefix variation cannot mask the intended interaction; this F2 failure set is not calibration data. If stable equivalence cannot be achieved with bounded effort, stop this Karto exact-prefix route and evaluate a more controllable experimental carrier.

No third CD science run, planner change, predictor, or post-treatment endpoint analysis was started.
