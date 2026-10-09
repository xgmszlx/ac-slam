# Serialized state inventory

All code statements refer to pinned ROS 1 1.5.7, not the current ROS 2 branch.

| State | Saved / restored evidence | Limitation |
|---|---|---|
| Mapper `.posegraph` | `serialization.hpp:38-45`; `Mapper::SaveToFile/LoadFromFile`, SDK Mapper.cpp | Boost binary archive, not a map image |
| Dataset `.data` | `Dataset::serialize`, Karto.h | Sensor lookup, historical data/scans, laser objects and dataset metadata |
| Graph vertices/edges | `Graph::serialize`; Mapper.h | Vertex scan objects, edge vector/order and endpoint pointers |
| Constraint values | `LinkInfo::serialize`; Mapper.h | Pose1, pose2, relative measurement and 3x3 covariance |
| Historical scan contents | `LocalizedRangeScan` / sensor data serialization | Range readings, odometric/corrected state and scan IDs; scan ROS header/per-beam timing is not reconstructed from this |
| Running scan manager | ScanManager and MapperSensorManager serialization | Running scans, last scan, next IDs and buffer settings are present in archive |
| Matching state | Mapper and ScanMatcher serialization | Matchers/grids/parameters included, but `LoadFromFile` sets initialized=false and deserialized=true; next `Initialize` rebuilds matching machinery |
| Solver object | Not archived as full optimizer memory | `solver_->Reset`, AddNode/AddConstraint, SetScanSolver and `Compute` rebuild solver state |
| ROS queues/filter bookkeeping | Not archived | Sync `q_`, TF MessageFilter pending queue, `shouldProcessScan` function-static last pose/time and ROS sequence state absent |
| Session transform and first-frame mode | Not archived | `map_to_odom`, `reprocessing_transform`, first measurement and processor type initialized anew |
| UI scan holder / caches | Not archived as ROS state | `lasers_` metadata repopulated from an incoming scan; visualization holder not a full history restore |

[Code] `serialization::write` catches archive exceptions and returns void; the ROS save callback returns true regardless. `serialization::read` checks `.posegraph` and catches archive exceptions; deserialize callback can return transport success even on a failed read. Consequently PoC validation checks both archive files, their hashes, successful restored graph content and continuation; service transport success alone is insufficient.

[Code] Mapper and Dataset are read from separate archives. Object relationships are serialized within each archive, not a global shared pointer registry across both files. The restored graph and restored dataset can therefore contain distinct scan instances. Their semantic agreement is assessed through saved scan contents and graph values; arbitrary memory addresses are never used as equality evidence.

[Inference] The archive is rich enough to recover historical graph measurements, but the stock lifecycle does not represent a complete process checkpoint. Whether this yields repeatable and continuous-equivalent outcomes remains the separately reported PoC result.
