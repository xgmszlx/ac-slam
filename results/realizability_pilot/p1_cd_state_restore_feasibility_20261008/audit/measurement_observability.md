# Measurement and provenance observability

[Code] ROS 1 1.5.7 `LoopClosureAssistant::publishGraph` exports visualization markers with vertex poses and edge endpoint positions. It does not publish a full numerical measurement/covariance/provenance message equivalent to newer ROS 2 pose-graph APIs. Markers alone are inadequate evidence.

[Code] The saved SDK graph retains actual LinkInfo measurements/covariances. The isolated read-only dump enumerates Graph vertices and ordered edges, including unique/state IDs, scan readings, odometric/corrected/sensor poses, endpoints, measurement and all nine covariance entries at 17-digit precision. Nodes are matched to exact input range vectors, never JSON index or arbitrary backend IDs. Ordered insertion vector is compared as well as structure and numbers; input indices identify historical vs C scans.

[Code] SDK has ordinary sequential, running-chain, near-chain and accepted-loop paths. All store LinkInfo without a persistent origin enum. A non-adjacent edge is not proof of accepted loop closure. This minimal patch logs accepted `TryCloseLoop` and optimizer Compute calls, and logs the selected processor type for each processed scan. It does not add a full constraint provenance system.

[Unknown] For a future certification, the minimal additional observation would record edge creation at the sequential/running/near/accepted-loop callsites with source/target and insertion index. No such larger change is made in B0. This small technical input may contain no accepted historical non-local association; in that case the required label is `HISTORICAL_MEASUREMENT_NOT_YET_VALIDATED`, independent of restore repeatability. Optimizer execution alone cannot satisfy it.
