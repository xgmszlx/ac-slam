# Doc-79 audit — observability patch (isolated build)

## Scope

Patch confined to `MultiMapper.h` / `MultiMapper.cpp` in the **isolated**
workspace `doc79_ws/src/nav2d_karto` (copy of
`dependencies/navigation_2d/nav2d_karto`). The production tree and the
production binaries in `catkin_ws/devel` are untouched (hashes before/after in
`production_integrity.json` and `build_manifest.json`).

## What the patch adds (observation only)

1. Native-scan counters and watermarks updated inside `receiveLaserScan()`
   (received, waiting-map drops, TF failures, processed, process exceptions,
   accepted, last scan seq/stamp/frame, last accepted state/unique id, last
   callback-complete time).
2. `/Mapper/get_native_scan_telemetry` service returning those fields plus
   graph node/edge counts and `pending_edge_provenance`.
3. `/Mapper/doc79_sync_boundary_export` service: serialized provenance flush +
   `WritePoseGraphJson()` to `/Mapper/pose_graph_dump_path`, returning a JSON
   payload with write result, path echo, flush state, callbacks times and the
   telemetry snapshot.

## What the patch does NOT touch

- no change to `Process()`, scan matching, thresholds, loop-closure logic,
  pose-graph optimisation, navigation or any publisher;
- no new thread and no new file writer in the maintenance thread;
- no change to message types, topics or parameters used by the frozen
  pipeline.

## Build and verification

- built in `doc79_ws` against the frozen underlay
  (`catkin_ws/devel`), `-DCMAKE_BUILD_TYPE=Release`;
- artifacts and hashes recorded in `audit/build_manifest.json`
  (`libMultiMapper.so` carries the new symbols; the `mapper` executable links
  it);
- unified diff: `audit/observability_patch.diff`;
- runner sets the overlay paths first (`ROS_PACKAGE_PATH`, `CMAKE_PREFIX_PATH`,
  `LD_LIBRARY_PATH`, `PYTHONPATH`) and records the resolved binary/library
  hashes per suite start in `audit/runtime_provenance.json`.
