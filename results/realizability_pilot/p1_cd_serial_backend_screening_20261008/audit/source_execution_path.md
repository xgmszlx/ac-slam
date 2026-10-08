# CD-A0 source execution path audit

Source baseline: `32b295d7599531bc913d7a19fb0c7de09a1ce495`. The production `MultiMapper.cpp:71` constructs `karto::OpenMapper(true)`; the isolated pure candidate changes exactly that argument to `false`. The observed candidate also adds read-only mode/optimizer logs and uses `max_digits10` **only for graph JSON export**. No matching threshold, scan input, optimizer, or planner was changed.

`OpenMapper.h:1683` returns the constructor's `m_MultiThreaded` flag. In `OpenMapper.cpp` the flag affects every following branch (line numbers refer to production source):

| Site | `true` with `USE_TBB` | `false` |
|---|---|---|
| `ScanMatcher::Create` ~585 | Allocates a 10-grid `ScanMatcherGridSetBank` as well as the ordinary grid set. | Allocates only the ordinary grid set. |
| `ScanMatcher::MatchScan` ~601, 634, 713 | Checks a grid set out of the bank and returns it, including early empty-scan return. | Uses its own `m_pScanMatcherGridSet`; no bank checkout/return. |
| `ScanMatcher::CorrelateScan` ~887 | Executes `Parallel_CorrelateScan` via `tbb::parallel_for(blocked_range3d)`. | Executes the lexicographic Y/X/angle scalar fallback. |
| `GetCorrelationGrid`, `GetSearchGrid` ~1390, 1402 | Throw: only accessible in single-threaded mode. | Return the ordinary grid objects. |
| `MapperGraph::LinkNearChains` ~2106 | Parallel matches eligible near chains, then links successful chains in index order. | Iterates near chains serially and immediately links each successful chain. |

`USE_TBB` remains enabled in both isolated builds. The false path therefore changes grid ownership, correlation execution and near-chain timing/order, not merely a worker-count limit. The two paths are distinct backends for scientific purposes; old multi-threaded numerical graphs cannot be a serial pass gate.

The scan-processing path is `MultiMapper::receiveLocalizedScan` → `OpenMapper::Process` → sequential scan match → `MapperGraph::AddEdges` → `TryCloseLoop` → `CorrectPoses` if no loop optimized it already. `MapperGraph::LinkObjects` calls `SpaSolver::AddConstraint` and `RecordNewConstraint`; `MapperGraph::CorrectPoses` calls `SpaSolver::Compute`. The latter is throttled by a 2 s ROS-time check before `doSPA(40)`, so a short scan smoke must not infer that numerical optimization ran solely from edge creation.

The isolated `seed_81001` A0 smoke (not one of A1's three histories) processed 33/33 scans, dumped 33 nodes and 38 edges via the synchronous callback service, and wrote 38 `constraint_created` provenance rows (32 `PREVIOUS_SCAN`, 6 `RUNNING_SCAN_CHAIN`, all with solver-add recorded). In the observed-build run, a one-shot log confirms `SpaSolver::Compute` reached `doSPA(40)`. No `TRY_CLOSE_LOOP` constraint was produced in this smoke; the audit **does not** claim a true loop closure was exercised.

Evidence: `technical/smoke_pure/`, `technical/smoke_observed_final/` (local raw directories), the observed ROS stdout log, `audit/serial_mode_evidence.md`, and the frozen source diff in `audit/serial_candidate.patch`.
