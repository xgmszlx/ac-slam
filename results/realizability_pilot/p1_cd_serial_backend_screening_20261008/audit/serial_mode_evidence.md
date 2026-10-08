# CD-A0 serial-mode evidence

The isolated pure build changes only `MultiMapper.cpp:71` to `new karto::OpenMapper(false)`. `OpenMapper.h:1683` returns the constructor flag without transformation. The pure build SHA is recorded in `isolated_build_manifest.json` and its independent A0 prefix-only replay completed 33/33 callbacks.

The separately identified observed build adds `ROS_INFO` immediately after construction. Its final A0 technical smoke log contains `CD_A0_SERIAL_MODE_EVIDENCE IsMultiThreaded=0` and `CD_A0_OPTIMIZATION_EVIDENCE SpaSolver::Compute executed doSPA(40)`. The latter is emitted only after the actual call to `m_Spa.doSPA(40)`; unlike a mere `CorrectPoses()` source path, this verifies an optimizer invocation in that run. This was not a `TRY_CLOSE_LOOP` event.

The observed smoke's live mapper PID was captured in `unified_replay_result.json`; `/proc/<pid>/maps` contains only the isolated `mapper`, `libMultiMapper.so`, `libOpenKarto.so`, `libSelfLocalizer.so` plus ROS/system libraries. Source/ELF binding evidence is in `symbol_and_library_audit.md` and `runtime_library_provenance.json`.

On the same non-A1 `seed_81001` technical prefix, pure and observed builds each produced 33 nodes and 38 edges. Rounding the observed build's graph JSON floats to the original `%.6f` representation yields exact JSON-semantic equality with the pure build. This is a **single smoke input**, not a general instrumentation-equivalence certificate. Observation-only logs and `max_digits10` output can change timing or instruction layout, so future A1 results on the observed build must not be silently ascribed to the pure binary.
