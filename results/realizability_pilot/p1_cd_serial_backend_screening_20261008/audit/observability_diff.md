# Observed-build delta from pure serial candidate

The pure candidate's only behavior change from production is `OpenMapper(true)` → `OpenMapper(false)`. The observed build was copied from the pure candidate, compiled in its own `isolated_catkin_observed` workspace, and carries these additional read-only changes:

1. `MultiMapper.cpp`: one `ROS_INFO` immediately after construction reports `mMapper->IsMultiThreaded()`.
2. `OpenMapper.cpp`: a `GraphDumpDouble` helper serializes **only `WritePoseGraphJson` node poses, edge measurements and covariance** using `std::numeric_limits<kt_double>::max_digits10` (`%.*g`). Other diagnostics, matcher decisions and provenance retain the original `LoopDiagDouble("%.6f")` implementation.
3. `SpaSolver.cpp`: one `ROS_INFO_ONCE` after `m_Spa.doSPA(40)` confirms the optimizer was actually invoked.

Reproduce the exact source diff locally with:

```bash
diff -u results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin/src/navigation_2d/nav2d_karto/src/MultiMapper.cpp results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin_observed/src/navigation_2d/nav2d_karto/src/MultiMapper.cpp
diff -u results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin/src/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin_observed/src/navigation_2d/nav2d_karto/OpenKarto/source/OpenMapper.cpp
diff -u results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin/src/navigation_2d/nav2d_karto/src/SpaSolver.cpp results/realizability_pilot/p1_cd_serial_backend_screening_20261008/isolated_catkin_observed/src/navigation_2d/nav2d_karto/src/SpaSolver.cpp
```

Those two source copies are local ignored build inputs; their hashes are committed in `isolated_build_manifest.json`. Applying `serial_candidate.patch` to baseline source reconstructs the pure variant; the three deltas above reconstruct the observed variant. The observed binary is `d5fe41a093669d62608667895591912c282c1e4e89f32f53362340c5df207ee0`; the pure binary is `14ee1688c828ebc152aef2932697ba8ab0300d40b0cde48e9cd9e5b7cd955b70`. They are not interchangeable. This instrumentation's timing/compilation impact is not proven absent by one A0 smoke.
