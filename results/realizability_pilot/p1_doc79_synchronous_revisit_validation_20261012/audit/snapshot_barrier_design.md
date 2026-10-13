# Doc-79 audit — synchronous snapshot design

## Four boundaries, eight files

| boundary | synchronous file | old-topic file |
| --- | --- | --- |
| G_before_return | `graph_before_return_sync.json` | `graph_before_return_topic.json` |
| G_arrival | `graph_arrival_sync.json` | `graph_arrival_topic.json` |
| G_action_done | `graph_action_done_sync.json` | `graph_action_done_topic.json` |
| G_final | `graph_final_sync.json` | `graph_final_topic.json` |

The synchronous files are written **by the mapper** (`WritePoseGraphJson`) with
one distinct path per boundary (the driver sets
`/Mapper/pose_graph_dump_path` before each export and verifies the echo and the
file hash). The old-topic files are the driver's cache of
`/slam_pose_graph_full` at the export instant, including the message count and
the last receipt time, so the comparison is honest about publication lag.

## Manifest fields (per boundary)

`watermark` (stamp/seq/index/driver counts), `telemetry_before_export`,
export response JSON (`written`, `dump_path`, flush state, wall/ros times,
counters), `sync_file` (path/sha256/node/edge counts),
`provenance_record_count_after_flush`, `topic_cache`
(received_ros_time/message_count/node_count/edge_count/scan_index_last),
`checks` and `all_checks_passed`.

## Checks performed

1. export service success and `written == true`;
2. dump path equals the requested per-boundary path;
3. `pending_edge_provenance == false` after the serialized flush;
4. file parses, `run_id` equals this run's provenance id;
5. node/edge counts equal the telemetry counts returned by the same callback;
6. sha256 computed by the driver and stored in the manifest (re-verified by
   the runner's technical check and by the analysis);
7. boundary paths are unique (guard function + test);
8. old-topic cache snapshotted at the same wall moment.

## What a valid dump does NOT claim

- It does not claim that all scans published before the boundary are inside
  the graph: acceptance is gated by 1.0 m / 0.52 rad, and the epoch is defined
  by the mapper's processed watermark, not by the driver's scan count.
- It does not claim the four dumps share one identical backend state: each is
  taken after its own motion segment and hold, and the action-pre state
  differences are quantified in the analysis.
