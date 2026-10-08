# CD-A0 ELF symbol and library audit

The CMake target structure duplicates OpenKarto definitions in `mapper` and `libOpenKarto.so`; `libMultiMapper.so` has an undefined reference to `karto::OpenMapper::OpenMapper(bool)`. `nm -DC --defined-only` and `readelf -Ws` confirm the constructor and `ScanMatcher::CorrelateScan` are exported by both executable and OpenKarto library. This is a potential interposition/maintenance risk, not by itself proof of an ODR defect.

`readelf -d` shows the candidate mapper needs `libMultiMapper.so`, with RUNPATH set to the *isolated* `devel/lib` and `/opt/ros/noetic/lib`. `libMultiMapper.so` needs `libOpenKarto.so` and `libSelfLocalizer.so`. `ldd` resolves all three to the isolated workspace; the observed smoke's live `/proc/<pid>/maps` independently confirms those exact isolated paths plus system TBB/CHOLMOD and ROS libraries. No production `catkin_ws/devel/lib` shared library appears in the mapper's mapped paths. The production generated `cpp_solver/PoseGraph.h` was used only as a C++ header during build because the copied `nav2d_karto` package does not declare that generated dependency; this is a build-isolation limitation, not a runtime library load.

A separate diagnostic process with fresh ROS master and `LD_DEBUG=bindings` (local log `technical/ld_bindings.103012`) showed:

- `libMultiMapper.so`'s `_ZN5karto10OpenMapperC1Eb` bound to the isolated `mapper` executable;
- `libOpenKarto.so`'s `OpenMapper::Process`, `Reset`, destructor, and `ScanMatcher` references also bound to the isolated executable.

Thus symbol origin is observable in this launch and the duplicate definitions are from the same isolated copied source variant. It does **not** establish binary-level equivalence across other load orders or prove that duplication is harmless in general. The diagnostic process exited via a 6-second timeout (code 124) after successful initialization; it was a symbol-binding probe, not a replay result.

The pure and observed candidate builds are separately hashed. Only the observed build's ROS log directly records `IsMultiThreaded=0`; the pure build has the same one-line false construction and was separately smoke-tested, but no direct in-process flag log. Neither result proves TBB caused the old CD-F2 multistability.
