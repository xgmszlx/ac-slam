# V14-T fixed-scan technical certification

Date: 2026-09-22

Scope: `V14_T_FIXED_SCAN_TECHNICAL_CERTIFICATION`. This is a controller,
measurement-budget, instrumentation, and analysis-protocol certification. It
is not a scientific confirmatory experiment.

## Provenance and immutability

- Branch: `research/phase4c-formal`
- Required base and preflight local/remote HEAD:
  `49cfff904954219f5be9425c714d6571c4cdd783`
- v14-T protocol SHA256:
  `0c5d70238cd9afc2934148a8fbcd5c86d25b34a3aaf9e03b7ba721e1d07fa96f`
- Scan-budget derivation SHA256:
  `532e703dea59deb1a0d3a416649422c05c45f7516b74c3cc9965d85e19e008bb`
- Frozen code-bundle SHA256:
  `00ff9d8089a879dd3734d93d5d5405713f932bec83af6e62425132afc50cab55`
- Original v13-C/post-hoc manifest SHA256:
  `bb4bdae0cdf2f01b561e79c4ba6fbb7aabdde59c9616ed2d12e827309de5d4e7`
- Original artefact verification after collection: passed, zero mismatches.
- Preserved v13-C gate:
  `CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`.
- Preserved post-hoc decision:
  `DIAGNOSTIC_SUPPORTS_ONE_PROSPECTIVE_RETRY`.

High-volume `.jsonl` streams and ROS logs remain in the local archive under
the result root and are excluded by the repository's existing publication
policy. Compact capture results, specifications, GT trajectories, ledgers,
CSVs, preregistrations, and decisions are published.

## Permanent future mechanism classifier

The shared future classifier now recognizes an explicit loop-closing record
only when one of `creation_provenance`, `creation_stage`, or `matcher_type` is
exactly `TRY_CLOSE_LOOP`. Substrings do not count. In particular,
`ADD_EDGES_BEFORE_TRY_CLOSE_LOOP`, `PREVIOUS_SCAN`, `RUNNING_SCAN_CHAIN`, and
`NEAR_CHAIN` all evaluate false. Frozen historical analyses were not edited.

Reclassification of the 967 existing factors used in this forensic gives:

- `PREVIOUS_SCAN`: 578
- `RUNNING_SCAN_CHAIN`: 358
- `NEAR_CHAIN`: 31
- exact `TRY_CLOSE_LOOP`: 0
- report label when zero: `NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED`

This removes the former false interpretation of 431 substring matches as
explicit TryCloseLoop events.

## Phase-resolved forensic

The audit attempted to map 578 accepted keyscans and 967 new factors from the
existing v13-C Target-A and frozen post-hoc Target-B FULL replays. The graph
snapshots do not store observed scan timestamps. The provenance `sim_time`
values are replay wall-clock epoch times, while stitched scan/action timestamps
are in the replay scan-time domain. There is no exact per-scan wall-clock map.

Consequently all 24 branches fail closed as:

- `PHASE_KEYSCAN_ATTRIBUTION_NOT_IDENTIFIABLE`
- `PHASE_FACTOR_ATTRIBUTION_NOT_IDENTIFIABLE`

No action phase, including any A2 phase, is assigned heuristically. In
particular, the data cannot establish whether A2 factors were created during
`ARRIVAL_PLUS90`, `SWEEP_90_TO_MINUS30`, `SWEEP_MINUS30_TO_0`,
`SWEEP_0_TO_PLUS30`, or `FINAL_HOLD_PLUS30`.

The non-phase comparison remains descriptive:

| Block/arm | All factors | Target history | Non-target history | Geodesic median m | Hops median | Match response mean | Information-eigenvalue median |
|---|---:|---:|---:|---:|---:|---:|---:|
| B-H1 A3 | 35 | 3 | 11 | 10.832 | 4.0 | 0.8635 | 3533.72 |
| B-H1 A2 | 44 | 3 | 15 | 10.258 | 4.0 | 0.8615 | 3848.53 |
| B-H3 A3 | 33 | 2 | 8 | 10.740 | 4.0 | 0.6529 | 2915.72 |
| B-H3 A2 | 42 | 3 | 12 | 10.366 | 4.5 | 0.7065 | 3848.69 |

Both blocks add nine total factors from A3 to A2, yet the already observed
`D_sweep` differs (`+0.00806884` for B-H1 and `+0.39820407` for B-H3).
B-H1's pre-graph has 42 nodes, 57 edges, and cycle rank 16; B-H3 has 34
nodes, 40 edges, and cycle rank 7. The frozen five target nodes in both have
the same aggregate local incident/internal counts (9/2), but realized
historical endpoints and factor information differ. These are mechanism
hypotheses only: factor count alone is insufficient, while pre-existing global
redundancy and endpoint/information identity may matter. The missing exact
phase timestamps prevent a causal phase-mediation conclusion.

## Outcome-blind fixed-scan budget

The timestamp convention is closed at both treatment start and maneuver
completion: `start <= scan.stamp <= completion`. The static-tail convention is
also closed. All 42 source streams have unique, strictly increasing timestamps.
The canonical JSON contains each full source path and both capture/stream
SHA256 hashes.

| Source | Target | Block/history | Arm | Completion index | Static tail |
|---|---|---|---|---:|---:|
| V13C | A | A-H1 | A1 | 161 | 61 |
| V13C | A | A-H1 | A3 | 210 | 60 |
| V13C | A | A-H1 | A2 | 232 | 61 |
| V13C | A | A-H2 | A1 | 162 | 61 |
| V13C | A | A-H2 | A3 | 206 | 61 |
| V13C | A | A-H2 | A2 | 230 | 61 |
| V13C | A | A-H3 | A1 | 165 | 61 |
| V13C | A | A-H3 | A3 | 213 | 61 |
| V13C | A | A-H3 | A2 | 234 | 60 |
| V13C | A | A-H4 | A1 | 158 | 61 |
| V13C | A | A-H4 | A3 | 204 | 61 |
| V13C | A | A-H4 | A2 | 228 | 61 |
| V12b calibration | A | repeat 01 | A1 | 164 | 61 |
| V12b calibration | A | repeat 01 | A3 | 208 | 61 |
| V12b calibration | A | repeat 01 | A2 | 231 | 61 |
| V12b calibration | A | repeat 02 | A1 | 164 | 61 |
| V12b calibration | A | repeat 02 | A3 | 210 | 60 |
| V12b calibration | A | repeat 02 | A2 | 234 | 61 |
| V12b calibration | A | repeat 03 | A1 | 163 | 60 |
| V12b calibration | A | repeat 03 | A3 | 212 | 60 |
| V12b calibration | A | repeat 03 | A2 | 234 | 61 |
| V13C | B | B-H1 | A1 | 175 | 61 |
| V13C | B | B-H1 | A3 | 222 | 61 |
| V13C | B | B-H1 | A2 | 274 | 61 |
| V13C | B | B-H2 | A1 | 175 | 61 |
| V13C | B | B-H2 | A3 | 222 | 61 |
| V13C | B | B-H2 | A2 | 273 | 61 |
| V13C | B | B-H3 | A1 | 175 | 61 |
| V13C | B | B-H3 | A3 | 220 | 61 |
| V13C | B | B-H3 | A2 | 273 | 61 |
| V13C | B | B-H4 | A1 | 167 | 61 |
| V13C | B | B-H4 | A3 | 211 | 61 |
| V13C | B | B-H4 | A2 | 282 | 61 |
| V12b calibration | B | repeat 01 | A1 | 170 | 60 |
| V12b calibration | B | repeat 01 | A3 | 216 | 60 |
| V12b calibration | B | repeat 01 | A2 | 287 | 61 |
| V12b calibration | B | repeat 02 | A1 | 172 | 61 |
| V12b calibration | B | repeat 02 | A3 | 218 | 61 |
| V12b calibration | B | repeat 02 | A2 | 286 | 61 |
| V12b calibration | B | repeat 03 | A1 | 171 | 60 |
| V12b calibration | B | repeat 03 | A3 | 218 | 60 |
| V12b calibration | B | repeat 03 | A2 | 285 | 60 |

Therefore `M=287`, `S=60`, and the frozen rule gives `N=M+S=347`.

## Fixed-scan controller semantics

- The treatment counter resets at the exact `probe_arrival.start_time`.
- Scans stamped before that reset remain raw/debug data and cannot enter the
  treatment stream.
- The scientific stream is the exact first 347 treatment scans by index.
- Raw recording may continue briefly and exceed 347 without contaminating the
  scientific stream.
- Original A1/A3/A2 waypoints are unchanged. There is no target-specific dwell
  equalization.
- A2 remains `theta0 -> +90 -> -30 -> 0 -> +30`, with final heading `+30`.
- Completion after scan 347 fails closed and never changes N automatically.

## 24-capture no-backend Stage preflight

All runs used a fresh ROS master and fresh Stage process. No Karto backend was
started and no scientific backend endpoint was read.

| Block | Arm | N | Complete | Margin | Duration s | Distance m | Yaw rad | Dup/nonmono | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| A-H1 | A1 | 347 | 164 | 183 | 34.7 | 4.239 | 3.094 | 0/0 | valid |
| A-H1 | A3 | 347 | 212 | 135 | 34.6 | 4.239 | 4.159 | 0/0 | valid |
| A-H1 | A2 | 347 | 232 | 115 | 34.6 | 4.238 | 4.713 | 0/0 | valid |
| A-H2 | A3 | 347 | 203 | 144 | 34.7 | 4.120 | 4.132 | 0/0 | valid |
| A-H2 | A2 | 347 | 230 | 117 | 34.7 | 4.128 | 4.727 | 0/0 | valid |
| A-H2 | A1 | 347 | 161 | 186 | 34.6 | 4.128 | 3.072 | 0/0 | valid |
| A-H3 | A2 | 347 | 238 | 109 | 34.6 | 4.433 | 4.721 | 0/0 | valid |
| A-H3 | A1 | 347 | 166 | 181 | 34.7 | 4.439 | 3.086 | 0/0 | valid |
| A-H3 | A3 | 347 | 213 | 134 | 34.6 | 4.433 | 4.133 | 0/0 | valid |
| A-H4 | A1 | 347 | 157 | 190 | 34.6 | 3.962 | 3.067 | 0/0 | valid |
| A-H4 | A2 | 347 | 228 | 119 | 34.7 | 3.974 | 4.738 | 0/0 | valid |
| A-H4 | A3 | 347 | 205 | 142 | 34.6 | 3.966 | 4.121 | 0/0 | valid |
| B-H1 | A3 | 347 | 220 | 127 | 34.6 | 5.683 | 3.222 | 0/0 | valid |
| B-H1 | A1 | 347 | 174 | 173 | 34.7 | 5.676 | 2.171 | 0/0 | valid |
| B-H1 | A2 | 347 | 274 | 73 | 34.7 | 5.684 | 5.639 | 0/0 | valid |
| B-H2 | A2 | 347 | 273 | 74 | 34.7 | 5.717 | 5.645 | 0/0 | valid |
| B-H2 | A3 | 347 | 220 | 127 | 34.7 | 5.708 | 3.219 | 0/0 | valid |
| B-H2 | A1 | 347 | 175 | 172 | 34.6 | 5.709 | 2.161 | 0/0 | valid |
| B-H3 | A1 | 347 | 173 | 174 | 34.7 | 5.687 | 2.168 | 0/0 | valid |
| B-H3 | A3 | 347 | 219 | 128 | 34.7 | 5.688 | 3.230 | 0/0 | valid |
| B-H3 | A2 | 347 | 271 | 76 | 34.7 | 5.688 | 5.635 | 0/0 | valid |
| B-H4 | A3 | 347 | 212 | 135 | 34.7 | 5.756 | 2.622 | 0/0 | valid |
| B-H4 | A2 | 347 | 282 | 65 | 34.7 | 5.755 | 6.238 | 0/0 | valid |
| B-H4 | A1 | 347 | 166 | 181 | 34.7 | 5.757 | 1.571 | 0/0 | valid |

Summary: 24/24 technically valid; minimum/median/maximum completion margin
`65/134.5/190`; exact scientific count 347 for every branch; zero duplicate
and nonmonotonic scientific timestamps; zero controller exceptions; no
post-N contamination. The minimum margin exceeds the frozen required margin
of 60 by five scans.

## Verification and gate

The full `tools/realizability_pilot/test_*.py` suite passed with 170 tests and
4 intentional skips. Tests cover the exact classifier, false-substring
regression, counter reset, exact first-N/raw-tail isolation, completion index
and fail-closed behavior, timestamp integrity, A+B deterministic budget,
phase-boundary ambiguity, frozen GT gauge, target-state errors, original
artefact hashes, and original gates.

Technical gate: `V14_FIXED_SCAN_TECHNICALLY_READY`.

No v14 confirmatory collection was started.
