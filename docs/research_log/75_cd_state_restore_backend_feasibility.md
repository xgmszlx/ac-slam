# CD-B0 — ROS 1 state-restore backend feasibility

## Material Passport

Task `CD_B0_STATE_RESTORE_BACKEND_FEASIBILITY`; technical architecture PoC; baseline `6a0a5b89227d560c5bda2a2b2ef6b58ca96b2ff3`; branch `research/phase4c-formal`. Preparation began 2026-10-08, frozen attempt and closeout 2026-10-09 (Asia/Shanghai). Inputs are one existing v13 technical scan history. Scientific endpoints are not part of this record. Verification status: **TECHNICALLY_INCOMPLETE**.

## Result and scope

The isolated ROS 1 slam_toolbox 1.5.7 source build and mapper/Ceres startup succeeded. The frozen technical matrix stopped during its first continuous row: the adapter set `publisher.impl.seq=0`, while the installed rospy publisher increments this counter before serialization. Its first scan therefore violated the prescribed global seq0 header contract and the worker's assertion stopped the run. This was an adapter implementation error. It is not evidence of backend state-save/restore infeasibility.

No full H+C graph, checkpoint, restored graph, or accepted historical loop constraint was collected. Main gate: **TECHNICALLY_INCOMPLETE**. Both restore comparisons are **NOT_EVALUABLE**. Additional gate: **HISTORICAL_MEASUREMENT_NOT_YET_VALIDATED**. Plan A readiness remains unverified. No automatic retry, parameter adjustment, input reselection or scientific experiment followed the stop.

## Baseline and provenance

Result root: `results/realizability_pilot/p1_cd_state_restore_feasibility_20261008/`. Permanent independent build: `/home/wcqw/ac-slam_cd_b0_ws`. Selected official ROS 1 tag 1.5.7 is commit `1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0`; observed noetic-devel head `8a754bb37485c598064dd1e5d00057ece4e3891d`. Source package hash and official-tag file comparisons are in `audit/upstream_source_provenance.json`. Sources: [official release repository](https://github.com/SteveMacenski/slam_toolbox-release), [pinned mapping source](https://github.com/SteveMacenski/slam_toolbox/tree/1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0/slam_toolbox), [ROS package metadata](https://index.ros.org/p/slam_toolbox/).

## ROS 1 compatibility and isolated build

Ubuntu 20.04 / Noetic / Python 3.8.10 / GCC 9.4.0. Dependencies were downloaded and extracted locally, without sudo or system installation. A Ceres imported absolute glog path initially prevented linking; only the extracted dependency's path was relocated. Subsequent build completed all targets. The real build log is `technical/build_check.log`. Compiler, source, package, executable and library hashes are in `audit/isolated_build_manifest.json`.

Actual process mappings confirm `libkartoSlamToolbox`, `libtoolbox_common`, `libsync_slam_toolbox` and the Ceres plugin were loaded from the independent devel tree; Ceres/glog came from independent extracted dependencies. No production catkin library path was loaded. Evidence: `technical/runs/continuous/loaded_libraries.json`. Candidate observations add counters, synchronized graph export, first-frame-mode log, optimizer log and accepted-loop log only. Patch is `audit/observation.patch`; matcher, optimizer and acceptance parameters remain the official config.

## Serialized state and restore lifecycle

The stock `.posegraph` archive contains graph nodes/edges, measurements, covariance, scans and substantial mapper state; `.data` contains dataset/scans/sensor metadata. Full ROS queues, keyframe filter function statics, session transforms and first-frame mode are not a process checkpoint. Restore resets/rebuilds the optimizer, recomputes it, repopulates laser metadata from an incoming scan, marks first measurement anew and routes the first continued scan through dock/near-region matching. SDK load also forces matching reinitialization. Detailed evidence is in `audit/serialization_state_inventory.md` and `audit/restore_lifecycle.md`.

These source facts justify separating restore-to-restore from restore-to-continuous. They do not establish the outcome of either comparison without the missing runtime trials.

## Input adapter and frozen experiment

v13 technical `target_A/seed_81001/canonical_prefix.jsonl` has 33 scans, SHA `4eddfa84d601f04bf4b86f52dca819c4ccd83c5476fdb48cf1e48f0c76255bde`. Scan ranges/geometry are retained; base odom is algebraically recovered from recorded laser odom with the documented 0.2m offset. Coordinate roundtrip maximum is `1.3877787807814457e-17`. Empty frame IDs receive a declared logical laser name. Existing canonical time normalization is preserved with a +10s origin shift. Original scan/odom latency and per-beam timing are unknown; no hardware timing fidelity is claimed. Original files are unmodified.

Frozen H=[0,20), C=[20,33). Official sync configuration is unchanged. Fixed row order: continuous, checkpoint, restore1, restore2, restore3, each fresh master/process. Restore mode START_AT_GIVEN_POSE; first C is intended to supply metadata and continuation exactly once. Initial pose rule uses last H corrected/odom pose and first C base odom, with no fitted alignment. Graph correspondence uses exact scan contents, and measurement/covariance/pose comparisons have zero numerical tolerance.

Preregistration `protocol/frozen_technical_experiment.json` SHA **`7af241866c002e5844cf74817a392c45784d85c848dea184fd2e9a5337b052d1`**. Frozen code/config/binary hashes are inside it. Four static tests passed before launch, including sensor-offset inversion, state-anchor algebra, arbitrary ID remapping and retention of tiny measurement differences. These tests missed the publisher counter's pre-increment behavior. Frozen scripts have remained byte-identical after the attempted run.

## Checkpoint barrier and matrix completion

The compiled observation service checks expected post-filter callbacks, accepted/processed count equality, empty queue and no in-flight worker before reading the graph under queue+mapper mutexes. Saving was to be bracketed by identical graph snapshots and no input publication. The runtime stopped before this gate, so the barrier is **not validated** and no checkpoint manifest can attest a save. Placeholders record NOT_EXECUTED; no queue clearing or fixed-sleep drain claim is made.

| Row | Runtime status | Graph / checkpoint |
|---|---|---|
| Continuous H+C | Stopped on first publish header assertion | No final graph |
| Checkpoint H | Not executed by frozen stop rule | No archive |
| Restore 1–3 | Not executed by frozen stop rule | No restored graph |

Real row timestamps: 2026-10-09 16:56:21–16:56:28 Asia/Shanghai. Mapper startup is observed; no `CD_B0_PROCESS` or optimizer/accepted-loop log is present before shutdown. A published scan is not proof it was processed. No separate runtime wire capture survived the assertion. Read-only source inspection and an offline test of the installed `_PublisherImpl.publish` implementation establish the sequence pre-increment mechanism; no ROS master or backend replay is used by that forensic test. Logs are under `technical/runs/continuous/`; evidence is `audit/publisher_failure.json` and `technical/publisher_forensic_tests.log`.

## Comparison and measurement observability

Restore-to-restore: no pairs evaluated. Restore-to-continuous: no pairs evaluated. The frozen comparison implementation is available for review but has produced no measured equality/inequality here. `analysis/final_gate.json` uses null for unmeasured comparisons; the older generated `technical_verdict.json` false fields denote unmet completion gates, not failed restore measurements.

SDK constraint values are accessible in the observation interface, whereas ROS 1 visualization markers alone lack measurements and covariance. The SDK does not persist full ordinary/running/near/accepted-loop edge-origin labels. Minimal accepted-loop logging was compiled; no complete provenance patch or positive-control expansion was attempted. Historical association remains **HISTORICAL_MEASUREMENT_NOT_YET_VALIDATED**. Optimizer invocation is not a substitute for a historical constraint.

## Integrity and limitations

Before/after full-tree byte hashing covers v14, v14-H, CD-T, original CD, Amendment1, CD-F2 and CD-A0/A1, including currently present ignored raw files; no scientific endpoint was parsed. Production mapper/OpenKarto/MultiMapper hashes are also compared. Reports: `audit/integrity_before.json`, `audit/integrity_after.json`. This verifies this task's invariance; it does not create a historical certification of unrecorded past files. No production binary was rebuilt or overwritten. All task processes were stopped after the fixed failure.

Runtime save/read success, strict barrier, resumed history constraints, repeated restore equality and uninterrupted equivalence are all still unknown. This is a small normalized technical input and cannot answer scientific treatment effects or multi-history reliability even if a later PoC succeeds.

## One recommended next action

Create a separate outcome-blind adapter technical amendment that fixes only rospy sequence initialization (`first_index-1`) and tests the installed publisher's actual serialization before freezing. Keep the same H/C split, input, configuration, matching mode, comparison rules and row order. Preserve this failed frozen B0 attempt, and require a new protocol ID/hash before another runtime matrix. No new scientific collection is authorized by this recommendation.

## Reproduction commands

Use `technical/environment.sh` for the independent overlay. `technical/source_evidence.py` reconstructs source/patch evidence. `technical/test_b0.py` and `technical/test_publisher_forensic.py` are offline tests. `technical/b0_tools.py analyze` is read-only with respect to old experiments. **Do not execute `b0_run.py` to retry this sealed matrix**: it refuses existing row directories and the fixed original bug remains preserved.

Logs, graph comparison program, converted inputs and compact manifests are committed. Build/package binaries and ROS internal logs remain local and are identified by hashes; no checkpoint binaries exist.
