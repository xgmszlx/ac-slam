# doc79_ws — isolated observation overlay (Doc 79)

This workspace is a **doc-79-only overlay** of `nav2d_karto`. It exists so the
synchronous-boundary observation code runs *without touching* the production
`catkin_ws` build. The production mapper binary and `libMultiMapper.so` are
byte-identical to the pre-Doc-79 hashes recorded in
`../results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012/audit/production_integrity.json`.

Contents of the patch (observation only, no planner/mapping behaviour change):

- `/Mapper/get_native_scan_telemetry` — read-only counters/timestamps for the
  native scan callback path (`receiveLaserScan`), including
  `native_scan_received / processed / accepted`, last stamp/seq/frame id and
  callback-completion ROS times.
- `/Mapper/doc79_sync_boundary_export` — serialized export: flushes the edge
  provenance buffer, requests a synchronous pose-graph dump to
  `/Mapper/pose_graph_dump_path`, and returns counts/paths/flags.

Full diff: `../results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012/audit/observability_patch.diff`.

Rebuild (exact flags used for the frozen run):

```bash
cd doc79_ws
catkin_make -DCMAKE_BUILD_TYPE=Release \
  -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  -DPYTHON_INCLUDE_DIR=/usr/include/python3.8 \
  -DPYTHON_LIBRARY=/usr/lib/x86_64-linux-gnu/libpython3.8.so
```

The Doc-79 runner prepends this overlay to `ROS_PACKAGE_PATH`,
`CMAKE_PREFIX_PATH`, `LD_LIBRARY_PATH` and `PYTHONPATH` before launching, so
the production workspace keeps running the old code. `build/` and `devel/`
are intentionally not tracked.
