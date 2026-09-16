# Controlled Constraint-Realization Pilot Protocol

Date: 2026-09-16

## Decision and scope

The proposed pilot is feasible, but the first executable gate is intentionally
smaller than the proposed 96--192 episode screen. It asks one causal question:
after a freshly reset mapper builds a deterministic history, can one controlled
revisit action create a new Karto pose-graph constraint to a target scan set that
was frozen before the action?

This phase does not modify the graph-based planner, loop objective, prior graph,
skip logic, navigation controller, or Karto matching thresholds. It also does not
claim that map3 represents room, corridor, turn, or intersection semantics. map3
is an open synthetic grid; its first target is an infrastructure/debug target.
No predictive model or new active-SLAM score is authorized by this preflight.

## P0 provenance result

The current runtime is not a pristine copy of the author's repository. It is an
experimental superset whose relevant nested-repository layers are recorded by
`tools/realizability_pilot/audit_provenance.py`:

- author original: `675299330dff0460d42c0ffd87a2f1f7f9f959da`;
- minimal runtime compatibility: `5a11667`;
- deterministic TSP control: `2cfe168`;
- active-loop observer: `211642d`;
- optional matcher diagnostics: `547ea24`;
- experimental modes through the current baseline head: `7993bf8`.

All experimental planner modes are disabled for this pilot (`oracle_mode=0`).
That default-off property is compatibility evidence, not proof that the checkout
is bit-identical to the author version. The provenance audit records exact heads,
origin heads, tracked modifications, and untracked-file counts without ingesting
old result files into the manifest.

## Intervention unit

One CSV row is one independent episode. Each episode starts a fresh ROS master,
Stage world, robot, Karto mapper, and navigation stack. It then:

1. calls the existing initial-mapping action;
2. executes the same non-self-intersecting history route;
3. freezes the nearest historical anchor and its contiguous 2.5 m scan segment;
4. records the pre-action pose graph;
5. executes exactly one controlled revisit action;
6. records the post-action pose graph and ground-truth probe trajectory;
7. terminates the whole ROS process tree.

An episode is excluded from causal analysis if an accepted closure occurs before
the target is frozen. Navigation failure is retained as a failed attempt and the
suite stops fail-closed; it is never silently retried.

## Preflight design

The first target is `map3_grid_anchor_01`, with fixed start
`[-28, -28, 0]`, fixed history waypoints, zero injected odometry noise, and one
of four probe conditions:

| Condition | Heading offset | Lateral offset | Maneuver | Matcher diagnostics |
| --- | ---: | ---: | --- | --- |
| baseline_diag_off | 0 deg | 0.0 m | pass | off |
| baseline_diag_on | 0 deg | 0.0 m | pass | on |
| align60_diag_on | 60 deg | 0.0 m | align | on |
| sweep90_diag_on | 90 deg | 0.0 m | sweep | on |

The diagnostics-off/on baseline pair is mandatory because earlier project notes
conflict on whether synchronous per-attempt JSONL logging perturbs Stage/ROS
timing. A negative or divergent sentinel result blocks the larger screen.

## Outcome definition

The low-frequency `/Mapper/loop_closed` event now carries the exact historical
scan selected by `LinkChainToScan`, current scan, relative SE(2) measurement, and
the transformed covariance that Karto supplies to the solver. This is
observation-only and does not change candidate generation, coarse/fine tests, or
graph optimization.

`target_constraint=true` requires all of the following:

1. the matcher accepted during the bounded probe interval;
2. the event's exact historical endpoint belongs to the pre-frozen target set;
3. the post-action pose graph contains a newly observed edge from that historical
   scan to the event's current scan.

Matcher acceptance without the corresponding new edge is recorded separately.
Wrong-target constraints are also retained. Geometric false-constraint labels
remain `UNKNOWN` until a separate consistency audit is defined; they are not
inferred automatically.

## Scaling gate

The larger factorial screen (4 heading offsets x 2 lateral offsets x 3 maneuvers)
is only justified after the four-episode preflight establishes:

- repeatable history-route and target freezing;
- at least one newly confirmed target constraint under the positive revisit;
- consistent exact event-to-edge identity;
- no material diagnostics-on/off execution divergence.

If these checks fail, the next task is diagnosis of the harness, map geometry,
navigation, Karto, or instrumentation. It is not parameter tuning or a predictive
model.

## Reproducible lifecycle

The runner supports `plan`, detached `start`, `status`, verified process-group
`stop`, and append-only resume. Each attempt has a 2700 s hard timeout, 30 s
process/node/RSS monitoring, separate stdout/stderr logs, and an atomic state
file. Partial attempt directories are never reused.

Commands are documented in `tools/realizability_pilot/README.md`. The aggregate
script emits one row per successfully completed independent episode.

## 2026-09-16 v1 technical invalidation and v2 repair

The first v1 diagnostics-off episode was technically invalid. The four history
actions returned action state `SUCCEEDED`, but their reported/final SLAM poses
remained near `(-5.9, -6.3)` rather than the requested Stage-world coordinates.
The navigator had projected unreachable, outside-current-map goals to the known
map boundary. The frozen target was therefore a boundary artifact, and the probe
timed out after repeated `Robot cannot move further in this direction!` warnings.
No constraint-realization outcome is selected from that attempt.

Protocol v2 makes two observation/harness-only repairs:

1. the same route shape is expressed as offsets from the actual mapper pose at
   episode start and resolved into the current Karto map frame;
2. every action result is independently checked using the latest `/slam_path`
   pose with frozen 0.75 m position and 0.35 rad heading tolerances.

The old suite remains immutable evidence under
`results/realizability_pilot/p1_preflight_20260916`. Because the coordinate
contract changed, v2 uses a new suite rather than retrying the v1 episode in an
`attempt_02` directory.

## 2026-09-16 v2 technical invalidation and v3 repair

The v2 diagnostics-off episode correctly executed and independently confirmed
the first three history goals. At the fourth goal, Nav2D reported `SUCCEEDED`
and a final pose within roughly 0.1 m of the requested target, while the last
pose in `/slam_path` was 1.95 m away. Inspection of `MultiMapper.cpp` established
that `/slam_path` is the complete corrected keyscan trajectory published from
`sendMap()`; it is not a continuous robot-pose stream. The v2 verifier therefore
used the wrong measurement construct and the episode is `TECHNICAL_INVALID`, not
a navigation or constraint-realization failure.

Protocol v3 uses live `map -> base_link` TF plus Stage ground truth as the joint
execution gate. The mapper's `/others` accepted-keyscan pose and `/slam_path`
endpoint remain recorded with age/error diagnostics, but neither can veto a
navigation action merely because no fresh keyscan/path publication has arrived.
The fixed geometric tolerances remain unchanged; this is a construct correction,
not a relaxation. v3 again receives a new suite directory.

## 2026-09-16 v3 technical invalidation and v4 repair

v3 confirmed the corrected arrival construct: all four history moves passed both
live TF and Stage-GT gates, with TF position errors 0.07--0.27 m and GT errors
0.16--0.26 m. The stale `/slam_path` discrepancy grew to 1.81 m without causing
a false navigation failure. This validates the v3 execution measurement change.

The episode nevertheless remained technically invalid because its driver began
subscribing to the incremental `/slam_pose_graph` topic only after initial
mapping. The planner had already advanced the mapper-wide publication cursor, so
the pilot could not reconstruct the historical graph and stopped at target
freeze. In addition, resolving route offsets using the variable heading at the
end of `GetFirstMap` rotated otherwise paired histories (`0.083` rad in v2 versus
`-0.617` rad in v3).

Protocol v4 starts the passive driver/subscribers before `StartMapping`, holds
action execution behind a ROS parameter gate, and opens that gate only after the
mapping action succeeds. The route origin uses the first Karto path pose XY with
a fixed map-axis heading of zero; GT targets use the frozen simulator start pose.
This preserves a common absolute history geometry across diagnostics conditions.

## 2026-09-16 v4 technical invalidation and v5 repair

v4 executed all four history moves correctly, but its canonical target nodes
still came from `/slam_pose_graph`. That topic is incremental and its start
indices are controlled by the mapper's shared publication cursor. The pre-probe
snapshot therefore contained only node IDs 1--8 even though the simultaneously
recorded full `/slam_path` contained 33 Karto vertices. v4 selected node 1 near
`(1.00, -0.11)` for an intended target at `(6.20, 0.00)`. The robot accurately
reached that wrong map-frame target (0.033 m TF error), while Stage GT correctly
showed a 5.069 m mismatch. This is a target-identity harness failure; the episode
is `TECHNICAL_INVALID` and supplies no constraint-realization outcome.

Protocol v5 uses `/slam_path` as the canonical full corrected Karto vertex
sequence. Inspection of `MultiMapper::sendMap()` confirms that it iterates the
complete `MapperGraph::VertexList` in order, so the path list index is the same
state ID used by pose-graph edges. `/slam_pose_graph` remains the incremental
edge stream and is retained separately for audit. Before a probe can start, a
frozen outcome-blind gate now requires: at least 20 full-history nodes, at least
three contiguous target scans, an anchor no farther than 1.0 m from the intended
history waypoint, and an anchor ID acquired after the route-start node count.
Failure of any check aborts before intervention; it does not relax the route,
matcher, target, or outcome definition.

## 2026-09-16 v5 preflight result and v6 measurement-boundary audit

All four v5 episodes completed independently and passed the target-identity,
navigation, GT, keyscan, and contamination gates. Every probe generated new
keyscans in the frozen target neighborhood, but all four had zero explicit Karto
loop events and zero explicitly confirmed target constraints. The three
diagnostics-enabled runs emitted only `loop_search_no_chain`; every search ended
at candidate generation with `ALL_CANDIDATES_NEAR_LINKED`, so neither coarse nor
fine loop matching ran. The larger 24-condition screening is therefore blocked.

Code inspection establishes an unresolved outcome-definition boundary.
`MapperGraph::AddEdges` calls `LinkNearChains` before `TryCloseLoop`.
`LinkNearChains` can accept scan matching and insert a graph constraint to a
historical chain; `TryCloseLoop` then sees that history as graph-near-linked and
excludes it from explicit loop candidates. `/Mapper/closure_edges` contains both
these ordinary near-chain links and explicit loop edges. Consequently, the v5
result is a valid negative for *explicit TryCloseLoop realization*, but it does
not yet prove that the backend accepted no target-attributable measurement of
any kind.

Protocol v6 leaves planner, route, map, actions, Karto parameters, and the
explicit-loop outcome unchanged. It adds passive capture of the existing full
`/Mapper/closure_edges` marker, resolves endpoints against the complete
`/slam_path` vertex list, and reports a separate `target_backend_measurement`
outcome. Marker-only target edges are explicitly labelled non-explicit/unknown
kind rather than loop closures. This is a measurement-chain audit, not an
algorithmic intervention or a post-hoc widening of `target_constraint`.

The first v6 diagnostics-off episode passed every execution gate and again had
zero explicit loop events, but its marker delta contained three new edges from
the frozen target scans to post-freeze scans: `17--40`, `14--41`, and `15--49`.
All marker endpoints resolved to full-path state IDs with zero positional error.
Thus the episode is positive for a target-attributable backend graph measurement
while negative for explicit `TryCloseLoop` acceptance. The remaining v6
conditions are intentionally paused because the original dependent variable is
incomplete.

A post-hoc re-audit of the 21 Phase 2A active loops using their already-saved
before/after marker snapshots found 14 target-attributable new graph edges in
4/21 loops (pair/loop 1/1, 3/3, 4/1, and 5/2), despite 0/21 explicit callbacks.
This does not turn marker edges into loop closures: their exact construction
path and covariance were not saved, and marker endpoint attribution is geometric.
It does invalidate the stronger statement that all 21 actions produced zero
backend constraints. The reproducible table and details are under
`results/realizability_pilot/historical_measurement_reaudit_20260916/`.

Protocol v7 therefore adds a new, default-disabled full pose-graph observer
topic. It publishes the complete Karto graph with exact node IDs, edge IDs, and
covariance independently of the planner-controlled incremental cursor. The
existing topic, planner, graph construction, matching thresholds, and marker are
unchanged. One v7 episode is required to cross-check the v6 marker finding before
any action-intervention comparison resumes.

## 2026-09-16 v7 observer validation

The first v7 attempt was technically invalid and is retained as such. The new
observer had initially been emitted only from `publishPoseGraph()`. In this
runtime, repeated `get_map` service calls invoke `sendMap()` and reset the same
map-update timer, so `/slam_path` advanced to 43 nodes while the latched full
graph remained at 9 nodes. This mismatch triggered the pre-registered fail-closed
gate before the probe; no scientific outcome is selected from attempt 01.

The outcome-blind repair moved only the default-off observer publication into
the same successful `sendMap()` path as `/slam_path`. It did not call the
existing incremental publisher, change its shared cursor, or alter Karto graph
construction, matching, navigation, route, seed, or action logic. Attempt 02
then had matching full node counts before (32/32) and after (48/48) the probe.

The exact full graph grew from 36 to 70 edges. Three new non-sequential edges
joined frozen target scans to post-freeze scans: `16--38` (edge 49), `13--39`
(edge 51), and `14--47` (edge 69). All three pairs independently appeared in
the closure-edge marker with zero endpoint-resolution error, and the exact graph
record preserved their covariance matrices. There were still zero explicit
`TryCloseLoop` events and zero explicit target constraints.

This single fresh episode confirms the v6 measurement-boundary finding:
`target_constraint=false` and `target_backend_measurement=true` can coexist.
The evidence status is **ANALYZED, not independently verified**. The suite is
paused with three sentinel conditions pending; no larger factorial screen is
authorized. The machine-readable decision is
`results/realizability_pilot/p1_preflight_v7_20260916/observer_validation_decision.json`.
