# Phase v11: Sweep--Dwell mechanism-dissection audit

## Material Passport

- Material ID: `ac-slam-v11-mechanism-audit-20260917`
- Type: offline source-and-record audit
- Status: `ANALYZED` (not confirmatory; not independently verified)
- Inputs: frozen v10 A0/A1/A2 recordings and replay graphs
- Output: `results/realizability_pilot/p1_mechanism_audit_v11_20260917/`
- Mutations: no v10 input changed; no ROS process or formal branch was run

This audit asks which constraint-generation mechanism produced the exploratory
v10 Sweep90--Dwell difference. It does not test a planner, claim an innovation,
or authorize the planned 12/18-branch experiment.

## A. LiDAR FOV

Verdict: **`LASER_FOV_LIMITED`**.

The actual map3 Stage model specifies a 25 m, 180 degree, 901-beam ranger
([hokuyo.inc](../../baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/hokuyo.inc#L8-L11))
mounted at `(x,y,z,yaw)=(0.2,0,-0.2,0)` in the robot frame
([p3at.inc](../../baseline/Graph-Based_SLAM-Aware_Exploration/world/map3/p3at.inc#L48-L49)).
The recorded scan confirms `angle_min=-pi/2`, `angle_max=+pi/2`, 901 beams,
`0.0034906585 rad = 0.2 deg` resolution, range `[0,25] m`, and frame
`base_laser_link`. The physical capture subscribes to `/base_scan`
([controlled_probe_capture.py](../../tools/realizability_pilot/controlled_probe_capture.py#L56-L60)).

The three actual named sweep endpoints were:

| endpoint | heading (rad / deg) | observable sector, unwrapped (deg) |
|---|---:|---:|
| Sweep -30 | -0.562743 / -32.24 | [-122.24, 57.76] |
| Sweep 0 | -0.069792 / -4.00 | [-94.00, 86.00] |
| Sweep +30 | 0.452674 / 25.94 | [-64.06, 115.94] |

Their heading span is 58.18 degrees, so their forward-sector union is about
238.18 degrees. Including the Sweep arm's +87.49-degree arrival, the action's
heading span is 119.73 degrees and its potential sector union is about 299.73
degrees. Therefore yaw changes physical observable coverage; it is not merely a
robot/scan-frame re-expression. Exact evidence is in
`lidar_sensing_geometry.json`.

## B. Karto keyscan rule

The actual replay launch uses `MinimumTravelDistance=1.0 m` and
`MinimumTravelHeading=0.52 rad`
([mapper.launch](../../results/realizability_pilot/p1_dwell_control_v10_20260917/branches/A2_sweep90/replay/mapper.launch#L8-L9)).
`MultiMapper` passes these values into OpenKarto
([MultiMapper.cpp](../../dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp#L87-L91)).

`OpenMapper::HasMovedEnough` compares current and last accepted **sensor poses**.
It first computes
`NormalizeAngle(current_heading-last_heading)` and accepts when its magnitude is
at least `MinimumTravelHeading`. Only if that fails does it test squared travel
distance against `MinimumTravelDistance^2-KT_TOLERANCE`
([OpenMapper.cpp](../../dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp#L3308-L3333)).
Thus the logic is **heading OR distance**, with heading checked first.
`KT_TOLERANCE=1e-6` applies to distance; the heading test has no explicit
tolerance ([Math.h](../../dependencies/navigation_2d/nav2d_karto/OpenKarto/source/OpenKarto/Math.h#L65-L71)).

The nominal 30-degree sweep step is 0.523599 rad, only 0.003599 rad (0.206
degrees) above the 0.52-rad threshold. `MinimumTravelHeading approximately
equals Sweep step angle` is therefore true. Actual endpoint transitions were:

| transition | normalized magnitude (rad) | endpoint alone crosses 0.52? |
|---|---:|---:|
| approach start -> +90 arrival | 1.629763 | yes |
| +90 arrival -> -30 | 2.089679 | yes |
| -30 -> 0 | 0.492951 | no |
| 0 -> +30 | 0.522466 | yes |

Acceptance occurs continuously during motion, not only at endpoints. Reapplying
the source predicate to every recorded scan exactly reconstructed the mapper's
post-prefix counts: A0=27, A1=27, A2=29. Full parameters, source semantics, and
transitions are in `keyscan_trigger_audit.json`.

## C. Extra-keyscan timeline

`keyscan_timeline.csv` contains all 83 post-prefix accepted keyscans with raw
index/time, nearest GT pose, raw and stitched laser odometry, Karto corrected
pose, distance/heading deltas, trigger, node, and every resulting constraint
with provenance.

The two count-exclusive Sweep keyscans are:

| node | raw sequence / time | action | GT yaw | delta heading | distance | trigger | edges |
|---:|---:|---|---:|---:|---:|---|---|
| 60 | 533 / 110.5 s | `sweep_-30deg` | -0.228063 | -0.520000 | 0.1028 m | heading | 81, 82 |
| 61 | 582 / 115.4 s | `sweep_+30deg` | 0.298956 | +0.527019 | 0.1042 m | heading | 83, 84 |

Both are unambiguously heading-triggered and far below the 1 m translation
threshold. Node 60 creates PREVIOUS edge 59--60 and RUNNING_SCAN_CHAIN edge
36--60. Node 61 creates PREVIOUS edge 60--61 and RUNNING_SCAN_CHAIN edge 59--61.
No NEAR_CHAIN, TRY_CLOSE_LOOP, or target-historical edge is produced by either.

## D. Sweep-only edge dependency

The 47--42 = 5 edge-count surplus decomposes as follows:

- 4/5 are directly incident to count-exclusive nodes 60/61: two PREVIOUS and
  two RUNNING_SCAN_CHAIN edges, all classified local.
- 0/5 are a later cascade after nodes 60/61; those are the terminal nodes.
- 1/5 appears earlier: A2 node 55 gains RUNNING chain edge 51--55, whereas A1
  node 55 has only its PREVIOUS edge. It is Sweep-affected but not dependent on
  nodes 60/61.
- The aggregate `+1 E_N` occurs at nonexclusive A2 node 58 via edge 20--58.
  A1 has local edge 46--58 at the corresponding node. Because A1/A2 are
  independent captures, this is a category shift plus an earlier count surplus,
  not a canonical one-edge subtraction.
- The aggregate `+4 local` equals the four edges incident to nodes 60/61 after
  earlier local-category differences cancel in count.
- Neither E_T edge depends on nodes 60/61.

The row-level ledger and explicit subtraction limitation are in
`edge_dependency_audit.csv` and `edge_dependency_summary.json`.

## E. Target factor identity/covariance comparison

Verdict: **Case T3**. All three arms create the same target endpoint identities
at the same edge indices: 14--36 (edge 45) and 17--37 (edge 47). Every factor is
`RUNNING_SCAN_CHAIN`; the cycles remain 5 and 6 edges. Maximum cross-arm GT
creation-pose dispersion is 0.0087 m and 0.0669 rad. The target factors are
created before the Sweep-only keyscans.

| arm | pair | response | insertion geodesic (m) | cycle edges | logdet information | factor D-opt |
|---|---|---:|---:|---:|---:|---:|
| A0 | 14--36 | 0.714625 | 9.2141 | 5 | 26.5657 | 7011.1 |
| A0 | 17--37 | 0.644807 | 9.0671 | 6 | 25.9080 | 5630.7 |
| A1 Dwell | 14--36 | 0.719962 | 9.2134 | 5 | 27.3940 | 9240.5 |
| A1 Dwell | 17--37 | 0.642133 | 9.0668 | 6 | 25.9040 | 5623.3 |
| A2 Sweep | 14--36 | 0.721801 | 9.2239 | 5 | 26.0572 | 5917.8 |
| A2 Sweep | 17--37 | 0.633119 | 9.0720 | 6 | 27.3194 | 9013.3 |

Relative measurements and covariances do vary across fresh captures, but target
identity/topology does not. Full measurements, 3x3 covariance/information
matrices, eigenvalues, responses, and physical creation poses are in
`target_factor_comparison.csv`; the classification is frozen in
`target_factor_mechanism.json`.

## F. Delta-U_T mechanism

Observed `Delta-U_T` is 507.6817 for Dwell and 543.2161 for Sweep, a +35.5345
(+7.00%) difference. Since the two endpoint pairs match exactly, an offline
target-covariance swap is identifiable without changing topology. The author's
utility and the linearised information diagnostic depend on edge information;
relative measurement values do not enter these two calculations.

| fixed topology | Dwell target covariance | Sweep target covariance | covariance effect |
|---|---:|---:|---:|
| Dwell | 507.6817 | 514.3387 | +6.6570 |
| Sweep | 539.7354 | 543.2161 | +3.4807 |

Holding Dwell covariance fixed leaves a +32.0538 topology/context difference;
holding Sweep covariance fixed leaves +28.8775. Equivalently, the two valid
decomposition paths assign only 9.8--18.7% of the observed gap to target
covariance and 81.3--90.2% to surrounding topology/context. Endpoint topology
explains none because it is identical. The best-supported account is therefore
a **combination dominated by surrounding graph structure and extra keyscans**,
not stronger or different E_T identity. This remains an offline diagnostic, not
a randomized causal estimate. See `counterfactual_target_covariance_swap.json`.

## G. Posterior mechanism

Sweep versus Dwell changes full target trace from 0.00208129 to 0.00190728
(-8.36%) and full current trace from 0.00143050 to 0.00125586 (-12.21%). With
Dwell target covariances held fixed, the corresponding reductions remain -7.82%
and -12.22%. Target covariance itself changes target trace by +1.12% on Dwell
topology or -0.59% on Sweep topology; its effect on current trace is at most
+0.55% in these swaps.

Removing E_T changes target trace by 0.00149484 in Dwell and 0.00144517 in Sweep
(-3.32%), so E_T impact on the target segment is not stronger in Sweep. The
current-pose removal effect increases, but A1 current node 59 and A2 current node
61 have different action semantics and surrounding topology, so it cannot be
read as intrinsic target-factor strength. Classification:
**`SURROUNDING_GRAPH_EFFECT_DOMINANT`**, while retaining a smaller
`TARGET_FACTOR_EFFECT`. Full values are in
`posterior_mechanism_decomposition.json`.

## H. Fourth-control decision

Decision: **`KEYSCAN_TRIGGER_CONTROL_REQUIRED`**.

Four of five net extra edges are created directly by the two
heading-threshold-only keyscans. Yet the 180-degree LiDAR proves that broader
viewpoint geometry is also physically real. The three-arm design cannot separate
these mechanisms, so it is not sufficient for confirmatory interpretation.

## I. Recommended confirmatory design

Add, but do not yet run, `A3_minimal_keyscan_oscillation`:

1. Follow A1 exactly through the Dwell arrival pose and heading `theta0`.
2. Rotate to `theta0 + alpha`, then return to `theta0`.
3. Use zero-twist dwell for the remaining Sweep time budget.

The amplitude is not guessed:

`alpha = 0.52 + 0.016954 + 0.007019 = 0.543973 rad = 31.167 deg`,

where the last two terms are the largest measured endpoint heading error and
the measured node-61 threshold overshoot. This creates two threshold-crossing
opportunities with a minimum added yaw excursion of 1.08795 rad. A forward
180-degree LiDAR then has a potential one-sided union of about 211.17 degrees,
smaller than the named Sweep endpoints' 238.18 degrees and the full Sweep
action's 299.73 degrees.

The preregistered engineering gate must require exactly two post-arrival
heading-triggered keyscans, no translation-triggered keyscan, and the existing
v10 distance/time/raw-scan budget tolerances. No limited-FOV rotation can create
a keyscan without changing some observed sector, so this control minimizes but
does not eliminate sensing change.

The confirmatory design becomes four common-prefix, balanced-order arms. Primary
contrasts are A2--A1 (total action), A3--A1 (minimal keyscan trigger), and A2--A3
(broader view). A former 12- or 18-branch three-arm plan scales to 16 or 24
branches at the same repetitions; sample size must be preregistered before any
formal run. The machine-readable design is in
`confirmatory_control_decision.json`.

## J. Candidate paper framing

**`MIXED_ACTION_CONSTRAINT_GENERATION_CANDIDATE`**.

Current evidence rules out a narrow “yaw matters” claim and does not show a new
target-factor topology. Sweep changes both physical scan coverage and Karto's
accepted-keyscan/factor-generation opportunities. The still-exploratory paper
question is whether an executed action produces a reproducibly different
**actually realized SLAM constraint set and realized information utility**, with
the fourth arm identifying how much is keyscan triggering versus broader view.
Innovation has not been established.

## K. Remaining fatal risk

The mechanism evidence comes from one fresh A1/A2 batch. The branches are
separate physical captures, so the fifth edge and category substitutions cannot
be paired edge-by-edge as if they were the same scan stream. More fundamentally,
a limited-FOV sensor makes heading-triggered keyscan creation inseparable from
some measurement-content change; A3 only reduces that coupling. If repeated
four-arm common-prefix experiments do not preserve the A2--A3 difference, there
is no evidence for a broader-view realizability mechanism beyond a
backend-specific keyscan threshold artifact. That is the remaining fatal risk.

Final gate: **`READY_TO_PREREGISTER_CONFIRMATORY_EXPERIMENT`**. No formal
experiment was started.
