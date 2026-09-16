# Controlled constraint-realization pilot

This harness tests whether a complete revisit action can causally change a
target-attributable Karto constraint.  It does not alter the graph-based planner,
Karto thresholds, prior graph, or skip rules.

The first profile intentionally contains one map3 infrastructure target.  map3 is
an open synthetic grid, so the target is not mislabelled as a room/corridor class.
Additional map8 targets are admitted only after this route and the target identity
telemetry pass the preflight.

Protocol v7 resolves the fixed history route from the first Karto path pose XY
and a canonical map-axis heading, with Stage GT targets anchored at the frozen
simulator start. It never mixes Stage-world coordinates with Karto's local map
frame or rotates the route with a variable post-mapping robot heading. Every
`MoveTo` success is independently checked against the latest
live `map -> base_link` TF and Stage ground truth; an action-server `SUCCEEDED`
status alone is insufficient. `/slam_path` and `/others` are recorded with
freshness metadata as Karto diagnostics, not treated as continuous robot pose.

The canonical historical-node sequence comes from the full corrected Karto
vertex list on `/slam_path`; list indices are graph state IDs. The incremental
`/slam_pose_graph` stream remains the edge/event observation source, but is not
allowed to truncate historical node identity when another subscriber advances
its shared publication cursor. Before any probe, an outcome-blind gate requires
at least 20 historical nodes, a target segment of at least three scans, an
anchor within 1.0 m of the intended history waypoint, and an anchor ID acquired
after the initial-mapping route start. A failed gate aborts before intervention.

v6 also preserves two distinct outcomes. `target_constraint` still means an
explicit `TryCloseLoop` acceptance confirmed by the event/edge chain.
`target_backend_measurement` additionally recognizes a newly appearing,
target-attributable non-sequential edge from Karto's full `closure_edges` marker,
resolved to `/slam_path` state IDs with at most 0.05 m endpoint error. Such a
marker-only edge is reported as `target_nonexplicit_marker_constraint`; it is
never silently relabelled as an explicit loop because OpenKarto also places
ordinary `LinkNearChains` constraints in that marker.

v7 adds a separate, default-off `/slam_pose_graph_full` observer topic. It
publishes the complete Karto vertex/edge set with exact IDs and covariance while
leaving the planner's cursor-controlled `/slam_pose_graph` untouched. Pilot runs
enable it explicitly and fail closed if its node set disagrees with `/slam_path`.
The full graph is authoritative for `target_backend_measurement`; the marker is
retained only as an independent cross-check.

The observer is published from the same successful `sendMap()` path as
`/slam_path`. Publishing it only from the periodic incremental-graph path is not
valid in this stack because `get_map` service traffic can reset the shared map
update timer and leave that topic stale.

## Lifecycle

Create a four-episode preflight queue:

```bash
/usr/bin/python3 tools/realizability_pilot/run_pilot.py plan \
  --profile preflight \
  --suite-dir results/realizability_pilot/p1_preflight
```

Start one episode in a detached process:

```bash
/usr/bin/python3 tools/realizability_pilot/run_pilot.py start \
  --suite-dir results/realizability_pilot/p1_preflight \
  --max-episodes 1
```

Inspect or interrupt it safely:

```bash
/usr/bin/python3 tools/realizability_pilot/run_pilot.py status \
  --suite-dir results/realizability_pilot/p1_preflight

/usr/bin/python3 tools/realizability_pilot/run_pilot.py stop \
  --suite-dir results/realizability_pilot/p1_preflight
```

Resume remaining episodes:

```bash
/usr/bin/python3 tools/realizability_pilot/run_pilot.py start \
  --suite-dir results/realizability_pilot/p1_preflight
```

A partial attempt is never reused.  Resume creates a new `attempt_NN` directory.
A failed attempt is fail-closed and requires `--retry-failed`.

Aggregate completed episodes:

```bash
/usr/bin/python3 tools/realizability_pilot/aggregate_episode_table.py \
  --suite-dir results/realizability_pilot/p1_preflight
```

Validate exact full-graph/marker agreement for a completed v7 attempt:

```bash
/usr/bin/python3 tools/realizability_pilot/validate_full_graph_observer.py \
  --run-dir results/realizability_pilot/p1_preflight_v7_20260916/episodes/0001_baseline_diag_off_r01/attempt_02
```

## Scientific boundaries

- One CSV row is one independently reset episode, never one matcher attempt.
- The historical target scan set is frozen before the probe.
- Target success requires both the exact historical endpoint selected by Karto
  and the corresponding new `(historical_scan, current_scan)` pose-graph edge.
  A matcher-accepted event without that new edge is retained as an anomaly, not
  counted as a realized backend constraint.
- `false_constraint` remains unknown until a separate geometric consistency audit
  is implemented; it is never silently labelled false.
- The preflight contains a diagnostics-off/on sentinel pair because synchronous
  diagnostics I/O may perturb real-time execution even though it does not alter
  Karto decision logic.
