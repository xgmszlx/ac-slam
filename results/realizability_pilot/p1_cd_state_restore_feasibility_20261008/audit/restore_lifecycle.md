# Restore lifecycle and checkpoint semantics

[Code] Common callback acquires mapper mutex, reads Mapper and Dataset, resets optimizer, inserts all recovered nodes and constraints, sets the solver, replaces working mapper/dataset, applies current ROS parameters, registers a serialized laser and waits for an incoming `/scan` to recreate laser metadata. It calls `solver_->Compute()`. After returning it sets `first_measurement_=true` and selects a new first-scan mode. Sync rejects the localization mode.

[Code] `START_AT_FIRST_NODE` uses `ProcessAtDock`; `START_AT_GIVEN_POSE` uses `ProcessAgainstNodesNearBy`, overrides the first scan's initial pose, clears the running chain, seeds it with a nearest historical scan, then updates session `reprocessing_transform`. Following scans use normal `Process`. Localization mode cannot serialize and is not the selected continuation backend.

[Code] `shouldProcessScan` stores `last_pose`, `last_scan_time` and minimum distance in function statics, outside the archive. The first restored scan bypasses normal filtering. The global scan sequence remains relevant (`header.seq < 5` rejects early non-first scans); the adapter preserves the original global sequence rather than restarting C at seq0.

[Inference] Restoration may be internally repeatable while differing from an uninterrupted process, even with the same C scans. The specific first-scan handling, optimizer reconstruction and matcher initialization are candidate explanations; the PoC does not change these paths or claim a unique root cause.

## Frozen lifecycle

Each matrix row starts a fresh ROS master and fresh mapper. The isolated synchronous mapper has read-only counters for post-TF-filter callbacks, accepted/enqueued scans, completed processing attempts and successful scans. A queue pop sets an in-flight flag under the queue mutex; completion clears it under that mutex. Publisher completion plus callbacks==published proves no input scan remains pending in the TF filter/main subscription; accepted==processed, empty q and false in-flight establishes drain. The dump service checks this condition under queue mutex and reads graph under mapper mutex. No queue is cleared.

Checkpoint H is dumped, saved via stock serialization, and dumped again at the same no-input barrier; exact before/after graph equality and archive hashes are recorded. Saving occurs once. Restoration sends first C once after both normal mapper and stock `waitForMessage` subscribers are connected. That same publication supplies laser metadata and first continuation input. It creates no extra bootstrap scan. No input is sent during graph dump/save.

The initial map->base pose is fixed by `T_corrected_last_H * inverse(T_odom_last_H) * T_base_first_C`. This is a preregistered state/odom extrapolation, with no fit to final outcomes. All three restores use the same recorded pose and same checkpoint archive bytes.
