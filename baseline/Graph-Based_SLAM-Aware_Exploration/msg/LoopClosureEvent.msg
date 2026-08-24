# Phase 4A: observation-only online loop-closure event.
# Published by the mapper exactly once per Karto-accepted loop closure.
# Only carries already-available Karto state ids; no matcher internals.
int32 seq            # per-mapper event sequence id (1, 2, 3, ...)
int32 loop_count     # total accepted closures in this mapper (mCountLoop)
int32 current_scan   # Karto state id of the scan that closed the loop
int32 chain_start    # Karto state id of the first scan of the matched chain
int32 chain_end      # Karto state id of the last scan of the matched chain
time  stamp          # ROS time at emission (sim time when use_sim_time)
