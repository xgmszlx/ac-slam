# Phase v12b: technical repair and fresh confirmatory rerun

## Material Passport

- Material ID: `ac-slam-v12b-technical-repair-20260918`
- Result root: `results/realizability_pilot/p1_confirmatory_v12b_20260918/`
- Verification status: `ANALYZED` for technical state only
- Final gate: `CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`
- Scientific analysis executed: no
- v12 Target-A role: `DESCRIPTIVE_PRIOR_EVIDENCE_NOT_POOLED`
- Pre-amendment and v12 blocks pooled into v12b: no

v12b asked the same frozen action-to-constraint question as v12 under a
target-specific sensing budget and repaired replay wrapper. It did not deliver
the preregistered four usable histories per target. The run therefore closes on
technical robustness, not on an action-effect estimate.

## Part I — Technical repair

### Timing and raw-scan root cause

In v12 Target B, A2 exceeded the within-block A1/A3 mean by 3.6--3.7 s and
36.0--37.5 scans. The implied surplus rate was 9.73--10.14 scans/s, consistent
with the measured 10 Hz `/base_scan` stream. Residual prediction error was at
most one scan. Verdict: `RAW_SCAN_MISMATCH_IS_DURATION_MEDIATED`.

Phase timing localized the target dependence to arrival/stabilization: mean
13.925 s on Target A and 19.100 s on Target B. The three post-arrival sweep
phases were stable at 9.300 and 9.325 s. Relative-yaw and +/-pi tests passed;
no absolute-yaw or wrap bug was found.

### Target-specific Stage-only calibration

The backend was not launched and no graph endpoint was read. Three repeats per
target froze the following durations:

| target | A1 dwell | A3 residual dwell | A2 residual dwell |
|---|---:|---:|---:|
| A | 7.1 s | 2.6 s | 0.0 s |
| B | 11.4 s | 7.0 s | 0.0 s |

All six target/repeat blocks passed the original gates: distance range <=0.10
m, duration range <=1.5 s, and raw-scan relative spread <=3%. No threshold was
relaxed.

### Prefix wrapper repair

The v12 canonical and branch wrappers had different periodic provenance flush
periods. v12b set both to zero. Two independent Target-B technical histories,
each replayed three times, had exact input and graph identity across nodes,
poses, edge order, measurements, covariances, and target mapping. All five
Phase-R gates passed as `TARGET_B_TECHNICAL_READY`.

### Technical amendment 01

The first formal start exposed an outcome-blind instrumentation lifecycle bug.
With periodic flush disabled, the maintenance thread that polled post-prefix
pose-graph dump requests was also disabled. The dump appeared only at mapper
shutdown, after the 30 s timeout.

The minimal repair keeps dump polling live whenever a dump path is configured,
but still performs no periodic provenance flush at zero. Catkin build, 18 unit
tests, and a zero-flush two-dump replay smoke test passed. The entire initial
attempt was archived and excluded, and all eight blocks restarted fresh. The
frozen analysis hash did not change.

During diagnosis, aggregate node/edge counts from the excluded shutdown dump
were viewed. This incident is recorded in the amendment. No J_T, covariance,
edge attribution, provenance outcome, or arm contrast was read. Exclusion and
fresh restart prevent the incident from entering the confirmatory sample.

## Part II — Frozen preregistration

- Protocol: `p1_confirmatory_v12b_20260918`
- Preregistration SHA-256: `bb5b53655793e7800c492df63ad15abe1e3420d9738376f05b35652391b2791d`
- Frozen analysis SHA-256: `bbdcc6ae4957ef08efa1ebc2ea16e38858e552bf65b5a1bc3b24de5ad490eebf`
- Primary seeds: Target A 71001--71004; Target B 72001--72004
- Reserve seeds: Target A 71005--71006; Target B 72005--72006
- Planned sample: 8 independent histories and 24 matched branches
- Statistical unit: canonical-history block, never branch

Scientific endpoints remained prohibited until `COLLECTION_LOCKED`. That marker
was never generated.

## Part III — Collection ledger

| block | final technical state | budget | branch state |
|---|---|---|---|
| Target A H1 | COLLECTED | PASS | 3/3 replayed |
| Target A H2 | COLLECTED | PASS | 3/3 replayed |
| Target A H3 | COLLECTED | PASS | 3/3 replayed |
| Target A H4 | COLLECTED | PASS | 3/3 replayed |
| Target B H1 | COLLECTED | PASS | 3/3 replayed |
| Target B H2 | TECHNICAL_INVALID_PREFIX | PASS | A2 failed prefix twice |
| Target B H3 | PROTOCOL_NOT_ROBUST | not reached | reserves exhausted |
| Target B H4 | PENDING | not reached | collection stopped |

Usable blocks were 5/8: Target A 4/4 and Target B 1/4. The history audit found
six `TARGET_REFERENCE_MATCH_INVALID` failures and four non-exact canonical
history replays.

Target B H2 eventually obtained a valid history with reserve 72006, but its A2
branch reproduced the same wrong prefix hash on both allowed replay attempts.
Target B H3 then exhausted the protocol's finite history resources.

The audit also found a reserve-accounting implementation defect: reserve 72005
was attempted under H2, superseded by 72006, and then selected again for H3.
The allocator checks only siblings' current `active_seed`, not all previously
consumed reserve seeds. No duplicate accepted history entered the sample, but
the behavior violates the preregistered one-use reserve rule.

## Part IV — Primary analysis

Not executed. There is no `COLLECTION_COMPLETE` or `COLLECTION_LOCKED` marker,
and the frozen analyzer correctly refuses to run. The four Target-A and one
Target-B valid blocks are not an eligible confirmatory sample. No D_view,
D_trigger, D_total, bootstrap interval, or sign statistic is reported.

## Part V — Mechanism analysis

Not executed. Fresh v12b keyscan, E_T/E_N, factor identity, covariance,
geodesic, cycle, Delta U, and history-removal outcomes remain unopened.

## Part VI — Replication comparison with v12

v12 Target A remains external descriptive evidence only:

- A2-A3: 4/4 positive, mean +0.07087
- A3-A1: 3/4 positive, mean +0.05767
- A2-A1: 4/4 positive, mean +0.12854

Because v12b never locked, no fresh replication comparison is permitted. v12
and v12b are not pooled.

## Part VII — Final gate

`CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`

This is specifically a recurrence of Phase-R target robustness problems:

1. physical target-reference matching is not reliable enough on Target B;
2. canonical/branch prefix identity is not robust across fresh Target-B
   histories;
3. the finite reserve protocol and its allocator did not deliver four
   independent usable Target-B blocks.

The run provides no evidence for or against D_view or D_trigger. It does show
that the current controlled-measurement protocol is not yet a reliable basis
for a general scientific claim. No predictor, planner integration, second
backend, or new control is justified from v12b.

Reproducible technical closeout artifacts:

- `technical_closeout/block_ledger.csv`
- `technical_closeout/technical_closeout.json`
- `COLLECTION_TERMINATED_TECHNICALLY_INCOMPLETE.json`
