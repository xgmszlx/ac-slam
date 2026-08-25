# Phase 4B Protocol Freeze

Date frozen: 2026-08-25

Status: **FROZEN BEFORE FORMAL RUNS**. No Phase 2C or Phase 3A run may be reused as
a Phase 4B performance observation. The first complete Phase 4B seed may serve as
the pipeline pilot and remain formal only if no scientific or evaluation parameter
is changed afterwards.

## 1. Scientific question and conditions

The experiment tests whether an already-selected informative active-loop action is
more often realized as a backend-accepted constraint under selective execution, and
whether that changes trajectory or mapping outcomes without paying the full
Always-Trace cost.

| label | directory | `oracle_mode` | execution |
|---|---|---:|---|
| A | `A_original` | 0 | author's original V0 reliable-loop path |
| B | `B_always_trace` | 1 | unconditional V1 contiguous history trace |
| C | `C_selective` | 2 | frozen span-gated bounded repair with attributable-closure early stop |

The **only condition variable is `oracle_mode`**. It selects a pre-existing Phase
4A execution branch; it does not alter high-level loop selection, TSP, D-opt, prior
graph, frontier/skip logic, navigation or Karto matching.

## 2. Frozen common configuration

- map/world: `map3/map3`; Stage world width 74.0 m
- initial pose: `[-28.0, -28.0, 0.0]` in Stage world
- strategy: `MyPlanner`; `only_use_tsp=false`
- TSP: Concorde, per-run seed equal to the formal seed
- sensor/robot/navigation/mapper: repository files at the frozen source hashes
- simulation noise: `need_noise=false`, `variance=0`
- local planner: enabled (launch default)
- diagnostics: `enable_loop_diagnostics=false` for A/B/C
- online forbidden inputs: coarse/fine response, candidate chain, variance,
  rejection reason and ground truth
- Always-Trace common parameters: before=8, after=8, densify=0.5 m
- Selective prototype parameters (passed identically in A/B/C): span gate=4.0 m,
  max repair length=12.0 m, max waypoints=24, densification=0.5 m,
  direction lambda=1.0
- exploration wall timeout may be enlarged; robot speed, tolerances, physics and
  planning parameters may not be changed to compensate for slow Stage execution

The 4.0 m gate is a **configuration-inspired lightweight prototype heuristic**.
It is not a theoretical Karto threshold and is not mathematically derived from
`LoopMatchMinimumChainSize`: that parameter is a scan count, not metres. The gate
and all repair bounds are frozen, not claimed optimal, and will not be tuned from
Phase 4B outcomes.

## 3. Accepted-closure and instrumentation policy

Formal acceptance is the observation-only `/Mapper/loop_closed` message emitted
only after OpenKarto accepts a closure. Each message records sequence, current scan,
chain endpoints and emission time. Active attribution requires its timestamp to lie
inside an active-loop execution interval. `Add one Loop closure.` and pose-graph
edge changes remain corroborating evidence; waypoint completion alone is not a
closure.

The passive observer may read topics and write run artifacts. It may not publish,
call planner services, read Karto matching diagnostics, or affect control. Ground
truth is evaluation-only. Formal runs use the same observer and logging policy.

## 4. Seeds and counterbalanced order

| seed | order |
|---:|---|
| 21001 | A -> B -> C |
| 21002 | B -> C -> A |
| 21003 | C -> A -> B |
| 21004 | A -> C -> B |
| 21005 | B -> A -> C |

No additional seed may be selected in response to pilot outcomes.

## 5. TSP fairness gate

For each seed, A/B/C independently launch from a fresh ROS/Stage process with the
same Concorde seed. Before `/StartMapping`, the runner saves and compares:

- solver and seed;
- `initial_tsp_path` and `full_tsp_path`;
- predicted TSP and full-TSP lengths;
- byte-level SHA-256 of `tsp_record.json`.

If the three records differ, the paired seed is **INVALID** and the runner stops
before starting the mismatched condition. It must not silently continue or alter the
objective.

## 6. Outcomes

Primary groups:

1. active-loop acceptance rate = attributable accepted active loops / active loops
   whose execution started;
2. active-loop distance and time, plus repair distance/time and early-stop savings
   when observable;
3. APE SE(2) translation RMSE, RPE translation and rotation under the existing
   pinned evo protocol;
4. occupied-space IoU and occupied-boundary F1 under doc 27.

Secondary outcomes are total exploration distance/time, repair/NO_REPAIR/early-stop
counts, planned/executed waypoint counts and map unknown ratio. Pose-graph counts
are reported only when the existing observer captures them reliably.

## 7. Validity and attempt retention

- `TECHNICAL_INVALID`: launch/node/runner/filesystem/residual-ROS failure. A new
  attempt is allowed only after diagnosis; every failed attempt remains on disk.
- `EXPERIMENTAL_FAILURE`: navigation/exploration failure or timeout under a normally
  running system. It is a real method outcome, is not deleted, and is not rerun merely
  because it is unfavorable.

The runner refuses to overwrite any existing run directory. Source and configuration
hashes, launch command, version information, wall/sim timing and raw logs are stored
per run. The top-level `protocol_manifest.json` is generated from the clean formal
code checkpoint during preflight.

## 8. Analysis freeze

The unit of paired inference is the seed (`n=5`), not individual loops. Report raw
points and seed-wise C-A, B-A and C-B differences using mean, median and range. Any
bootstrap, if used, resamples seed clusters. P-values are not the sole criterion.

Mapping and trajectory outcomes are interpreted separately. Increased closure
acceptance without improved map scores is reported only as improved loop realization,
not improved mapping.
