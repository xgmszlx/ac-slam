# Doc-79 audit — source execution path

Verified read-only on 2026-10-13 against HEAD `cac55c4b` (production sources
unchanged; hashes in `production_integrity.json`).

## Native scan entry

```
stage_ros publishes /base_scan
  -> Mapper node (nav2d_karto/mapper = MapperNode.cpp, single-threaded:
     ros::Rate(10) loop { publishTransform(); ros::spinOnce(); })
     -> MultiMapper::receiveLaserScan()          [subscribed to 'scan',
        launch remap: <remap from="scan" to="base_scan"/>]
        1. state check (ST_WAITING_FOR_MAP -> drop)
        2. first call creates karto::LaserRangeFinder from the message
        3. TF lookup offset_frame -> laser_frame at scan stamp (fallback latest)
        4. LocalizedLaserScan = createFromRosMessage + odometric/corrected pose
        5. mMapper->Process(laserScan)           [synchronous, same callback]
           - accept/reject gate: MinimumTravelDistance 1.0 m or
             MinimumTravelHeading 0.52 rad (param/mapper.yaml)
           - accept: AddVertex/AddEdges, TryCloseLoop / CorrectPoses
             (all inside Process)
           - on success: PHASE2C_KEYSCAN_ACCEPTED unique_id/state_id/sim_time
        6. map/slam publishers, /others RobotPose, callback returns
```

Every step above runs inside one callback on one queue; the mapper has **no
deferred scan-processing thread**. The only extra thread is
`instrumentationMaintenanceLoop()` (provenance flush), which is inert when
`instrumentation_flush_period_s = 0` (Doc-79 value).

## What the pre-existing counters actually mean

- `/Mapper/get_processed_localized_scan_count` counts **only**
  `receiveLocalizedScan()` calls (the multi-robot `karto_in` path). It does not
  count native `/base_scan` callbacks and it counts every call, not only
  accepted keyframes. Doc-79 therefore does **not** use it as process proof.
- `/Mapper/dump_pose_graph_now` writes the complete graph via
  `OpenMapper::WritePoseGraphJson()` (nodes: state_id/unique_id/pose; edges:
  endpoints + unique ids + relative measurement + 3x3 covariance). It runs in
  the same callback queue.

## Services and topics used by Doc 79

| name | type | role |
| --- | --- | --- |
| `/Mapper/get_native_scan_telemetry` | `std_srvs/Trigger` (added) | JSON counters and watermarks of the native callback path |
| `/Mapper/doc79_sync_boundary_export` | `std_srvs/Trigger` (added) | serialized provenance flush + synchronous pose-graph dump to `/Mapper/pose_graph_dump_path`, returning one JSON payload |
| `/slam_pose_graph_full` | `cpp_solver/PoseGraph` | old-topic graph cache (kept for the topic-vs-sync comparison only) |
| `/others` | `nav2d_msgs/RobotPose` | accepted keyframe pose stream (no state_id; identity comes from the accept log) |

## Why a barrier is legitimate here

`MapperNode.cpp` uses one `ros::spinOnce()` loop and one callback queue, and
`MultiMapper` advertises all services on that same queue. Callbacks are
processed in arrival order, so a service handler executes **after every scan
callback that was queued before it**. Doc-79 uses this in the safe direction:
it first observes (via the telemetry service) that the mapper has already
processed a scan with `stamp >= watermark`, and only then calls the export
service. Any scan callback queued between those two observations is also
already processed before the export runs. The export itself calls
`FlushEdgeProvenance()` before `WritePoseGraphJson()`, so the dump cannot
contain an edge whose creation record is still buffered.

Limits of the guarantee (recorded, not hidden):

- it covers scans that **reached the mapper's queue**; delivery gaps between
  publishers/subscribers are detected by the receive/accepted counters and the
  scan-identity audit, and degrade the boundary to `MEASUREMENT_NOT_VALIDATED`
  when inconsistent;
- `LaserScan.header.seq` behaviour is verified empirically per run
  (`scan_identity_audit`); identity is judged by the joint
  `(seq, stamp, frame_id)` and the stamp watermark, never by seq alone.
