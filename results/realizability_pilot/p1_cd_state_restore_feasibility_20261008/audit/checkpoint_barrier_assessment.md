# Barrier assessment after frozen runtime stop

Status: **IMPLEMENTED_BUT_NOT_RUNTIME_VALIDATED**.

The isolated build has counters and synchronized dump checks described in `restore_lifecycle.md` and `observation.patch`. This candidate compiled and its mapper/solver loaded. The input worker asserted on the first publish because its frozen rospy sequence initializer was off by one. Therefore no exact prefix-completion barrier was reached, no checkpoint was written, and none of the counters qualify as a validated drain measurement. `technical/checkpoint_barrier.json` explicitly records NOT_EXECUTED.

No fixed sleep is cited as drain evidence. The 0.2s scan pacing and 0.5s library-startup wait are unrelated to barrier certification. No queue clear operation was called. No pending scan was removed to satisfy a count. No new runtime trial was started after the failure.

Remaining implementation caveat: snapshot locks mapper and queue, and counts show expected filter callbacks; a future completed trial must still confirm the promised publisher/wire count equality and absence of further input. The designed protocol alone cannot establish these facts.

[Code] Callback threading was checked against the installed `/opt/ros/noetic/include/tf2_ros/message_filter.h`: the selected NodeHandle constructor stores `nh.getCallbackQueue()`, and `messageReady` dispatches a `CBQueueCallback` into that queue. This mapper uses `ros::spin()` on the global queue. Thus the scan callback and observation service are serialized in this lifecycle; the entry counter cannot be observed by the service midway through that same main-thread callback. The worker's in-flight flag covers the separate processing thread. This source check is not a substitute for the unexecuted runtime barrier test.
