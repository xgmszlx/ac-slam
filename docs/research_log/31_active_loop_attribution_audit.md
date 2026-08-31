# Active-Loop Attribution Audit

Date frozen: 2026-08-31

## Final definitions

The measurement, not callback arrival, determines attribution. No grace period or
spatial threshold is used.

- `TARGET_ATTRIBUTABLE`: the accepted event's current keyscan acquisition time is
  inside exactly one active-loop execution interval, and its accepted historical
  chain overlaps the exact intended history scan IDs reconstructed by replaying the
  frozen reliable-loop selection.
- `TEMPORALLY_ASSOCIATED`: current-keyscan acquisition is inside exactly one active
  interval, but intended historical identity does not overlap or cannot be
  established.
- `PASSIVE_OR_UNRELATED`: the current-keyscan measurement is not inside exactly one
  active interval.

The formal primary rate is the number of executed active-loop actions containing
at least one `TARGET_ATTRIBUTABLE` accepted constraint divided by the number of
executed active-loop actions. Multiple events from one action do not inflate the
numerator.

## Phase 4B compatibility

Compatibility is **YES**. `rosout.log` records
`PHASE2C_KEYSCAN_ACCEPTED unique_id state_id sim_time` for current scan acquisition;
typed accepted events provide current and historical chain IDs; observer artifacts
provide active intervals; prior maps and pose-graph snapshots permit frozen
reliable-loop replay. All 63 planned paths were reconstructed within `1e-4 m`
(63/63 pass), and intended history IDs were available for all six temporally active
accepted events.

## Accepted event reclassification

| Condition/seed | loop vertex | current -> history chain | class | decisive evidence |
|---|---:|---|---|---|
| A/21002 | 8 | 280 -> 15--19 | TEMPORALLY_ASSOCIATED | intended IDs 0--6; no overlap |
| C/21003 | 21 | 760 -> 506--511 | TARGET_ATTRIBUTABLE | intended IDs 505--511 overlap |
| B/21004 | 15 | 273 -> 161--164 | TARGET_ATTRIBUTABLE | intended trace overlaps 163--164 |
| B/21004 | 22 | 937 -> 548--551 | TARGET_ATTRIBUTABLE | intended trace overlaps 548--551 |
| C/21004 | none | 482 -> 349--352 | PASSIVE_OR_UNRELATED | no active interval |
| C/21005 | 26 | 490 -> 413--418 | TEMPORALLY_ASSOCIATED | intended IDs 399--412; no overlap |
| C/21005 | 8 | 728 -> 15--18 | TARGET_ATTRIBUTABLE | intended IDs 0--23 overlap |

Thus seven accepted constraints split into four target-attributable, two temporal
only, and one passive/unrelated event. The old six temporally attributed events are
not silently retained as target successes.

## Strong Phase 4B descriptive baseline

| Method | target-attributable loops / executed | pooled descriptive rate | seed-rate mean / median |
|---|---:|---:|---:|
| A Original | 0/21 | 0% | 0% / 0% |
| B Always-Trace | 2/21 | 9.52% | 8% / 0% |
| C Selective | 2/21 | 9.52% | 9% / 0% |

Seed-level C-A differences are positive in 2/5 blocks and tied in 3/5; B-A is
positive in 1/5 and tied in 4/5. Events remain rare, so pooled loop counts are
descriptive, not independent inferential samples.

Strong target attribution is **READY** for Phase 4C and uses the same definition on
M1, M2, and M3. Machine-readable evidence is under
`results/phase4c0/attribution/` and `results/phase4c0/statistics/`.
