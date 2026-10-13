# Doc-79 audit — native scan pipeline and processing barrier

## Pipeline (verified in source)

1. driver `on_scan()` records **every** `/base_scan` message: index, stamp,
   header seq, frame_id, wire ranges, TF-resolved odom/map poses.
2. mapper `receiveLaserScan()` (single queue) increments
   `native_scan_received`, stores the arrival identity, then either drops
   (state), skips (TF), or reaches the synchronous `mMapper->Process()`.
3. `native_scan_processed` increments when `Process()` returns (accept or
   reject); `native_scan_accepted` only for accepted keyframes, which are also
   logged as `PHASE2C_KEYSCAN_ACCEPTED unique_id/state_id/sim_time` and
   published on `/others` (pose only).
4. `native_scan_process_exceptions` counts thrown Karto exceptions;
   `native_scan_tf_failed` counts scans skipped for missing TF.

## Barrier protocol per boundary (driver side)

```
stage motion end (actionlib result / hold)          [physical evidence]
record watermark = last driver scan (stamp, seq, index)
poll telemetry (0.1 s) until
    last_native_scan_stamp >= watermark.stamp  AND  native_scan_processed > 0
cross-checks (all recorded in the boundary manifest):
    native_scan_received >= driver scan count
    native_scan_accepted == driver keyscan events (/others)
    scan identity stream: duplicates / regressions audited per run
set /Mapper/pose_graph_dump_path = graph_<boundary>_sync.json
call /Mapper/doc79_sync_boundary_export
    -> mapper flushes provenance, writes the dump, returns telemetry JSON
verify: service success, path echo, parseable JSON, run_id match,
        node/edge counts equal to telemetry counts, sha256 stored
snapshot the old-topic graph cache at the same moment (graph_<b>_topic.json)
append manifest + native_processing_ledger entries
```

## Explicit non-claims

- Comparing `driver.valid_scan_count` with accepted keyframes is **not** used
  (most scans are legitimately rejected by the 1.0 m / 0.52 rad gate).
- "Last processed sequence > X" alone is **not** accepted as proof: the
  received/accepted counters, the identity audit and the watermark stamp check
  run together, and any inconsistency fails the boundary.
- A fixed sleep is never used as a completion proof.
- If the watermark cannot be reached within 30 s, the boundary fails and the
  episode is `MEASUREMENT_NOT_VALIDATED` (budget still consumed).

## Stationary scans

Stage keeps publishing while the robot holds. The barrier therefore waits for
the mapper to have processed the *scan that existed at the stage-end instant*;
later stationary scans may be processed between the watermark check and the
export call, and this is recorded (the export telemetry shows the true
`last_native_scan_stamp` at dump time, which is >= the watermark).
