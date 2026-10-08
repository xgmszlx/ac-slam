# CD-A0 deployment-cost observation

Technical input: v13 `target_A/seed_81001/canonical_prefix.jsonl` (33 localized scans), not any CD-A1 history. Frozen mapper parameters from its `attempt_01/mapper_params.yaml`; 20 Hz prefix publisher; fresh ROS master and mapper; synchronous callback-count barrier and graph dump. No suffix.

| Run | Binary | Wall time | CPU | Memory |
|---|---|---:|---:|---:|
| Pure serial smoke | `14ee1688...` | 7.41 s external `/usr/bin/time` | 2.97 s user + 0.47 s system for process tree | 73,684 KiB maximum child RSS reported by `/usr/bin/time` |
| Observed serial final smoke | `d5fe41a0...` | 7.199 s runner wall | mapper 0.47 s user + 0.01 s system | mapper peak 47,013,888 bytes (50 ms sampling) |
| Historical production F2 prefix-only runs | production binary `7ab54496...` | 24-run median 7.596 s, range 7.435–7.875 s | not available on the same basis | not available on the same basis |

The F2 histories have different prefix contents/counts from the A0 smoke, and the two A0 CPU/RSS measurements use different scopes. These numbers show only that the isolated backend processed a short prefix at modest local cost. They are **not** a speedup, slowdown, or scientific effect estimate. The observed build's `doSPA(40)` log and 38 provenance rows show the optimizer and constraint-recording path is operational, but the smoke did not produce a true Karto `TRY_CLOSE_LOOP` constraint.
