# v14 Design If Authorized: Fixed Treatment Scan Budget

Status: design only; not authorized or executed.

The v13-C post-hoc Target-B diagnostic supports one fresh prospective retry,
but it does not authorize collection. The next controller should replace
transported target-level dwell calibration with a fixed treatment scan budget.

## Proposed prospective controller

1. Complete the unchanged common pre-treatment approach.
2. At `probe_arrival.start_time`, reset a treatment `LaserScan` counter.
3. Execute the arm-specific maneuver unchanged.
4. After maneuver completion, command zero twist and remain static.
5. End treatment only after both the maneuver-complete condition and exactly
   the frozen treatment budget `N` have been observed.
6. Require `N_A1 = N_A3 = N_A2 = N` within every canonical-history block.
7. Record wall-clock duration, traveled distance, angular motion, scan timing,
   dropped/duplicate timestamps, and post-maneuver static scans as technical
   diagnostics. Retain motion/time as a separate planner cost; do not hide it
   inside exposure matching.

Any arm that has not completed its maneuver before scan `N` is a technical
failure. It must not silently extend the scientific sample or trigger a
replacement run.

## Deterministic selection of N

Do not choose `N` from a future backend endpoint or by an arbitrary round
number. Before a future preregistration, use only the already existing Target-B
technical capture streams and controller timestamps:

- For every v12b calibration and v13-C B-H1--H4 arm, count treatment scans from
  `probe_arrival.start_time` through the arm-specific final maneuver completion
  (`probe_arrival` for A1, `min_trigger_return` for A3, `sweep_+30deg` for A2).
- Set `M` to the maximum observed action-completion scan count across those
  captures.
- Set a safety-tail count `S` to the minimum number of scans actually observed
  during the existing common six-second zero-twist final hold across the same
  captures. This derives the tail from existing technical behavior rather than
  an endpoint.
- Freeze `N = M + S`, the exact source-file hashes, timestamp inclusion rule,
  and the computed `M`, `S`, and `N` before any new collection.

This construction ensures that the historical worst-case maneuver completes
before the exposure budget while retaining a data-derived static tail. It does
not guarantee a future run will remain within that envelope, so maneuver
completion by scan `N` remains a preregistered technical gate.

## Minimum future protocol safeguards

- Fresh histories and a frozen seed/order manifest; no reuse of the present
  post-hoc blocks as confirmatory samples.
- Same canonical-prefix, processed-count, synchronous graph-dump, and exact
  zero-tolerance prefix gates.
- No endpoint access before the future collection lock.
- The statistical unit remains the history block, with no branch-level
  pseudoreplication.
- Preserve the same five-state estimator and declare motion/time-cost analysis
  separately before collection.
- Predefine missing/invalid-run handling without replacements selected after
  seeing backend outcomes.

No v14 process or collection has been started by this document.
