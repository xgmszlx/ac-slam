# Phase 4C-1 Environment Selection

Date: 2026-08-31

## Selected set

- M1: `map3` (unchanged);
- M2: `map8` (frozen; 3 opportunities per seed, 15 total);
- M3: `radish_mexico` (Acapulco Convention Center geometry source).

## Blind decision rule

Eligibility required source/licence traceability, deterministic conversion, prior
validation PASS, frozen scale PASS and frozen opportunity PASS. Among eligible
candidates, the prespecified tie-breaker maximizes the minimum standardized
topology-feature distance to map3 and map8. Mexico was the only eligible external
candidate, so no performance-based tie breaking occurred.

Mexico's standardized topology distance is 3.906 to map3 and 3.678 to map8 using
aspect ratio, free fraction, skeleton length/free area, junction density,
log skeleton cycles, median corridor width and log prior cycle rank. Its geometry
is longer, narrower-corridor and substantially more locally branched than the two
author maps; its prior is also much larger (165 nodes) while retaining cyclic
structure (rank 28).

Selection was completed before any Mexico A/B/C exploration. The only online
action was a stationary Stage-loading smoke test. No performance outcome was
generated or consulted. `results/phase4c1/selected_environment.json` is the
machine-readable decision record.

## Frozen future protocol

If authorized later, map8 and M3 use:

| seed | order |
|---:|---|
| 21001 | A -> B -> C |
| 21002 | B -> C -> A |
| 21003 | C -> A -> B |
| 21004 | A -> C -> B |
| 21005 | B -> A -> C |

Each run must store selection sequence/order/timestamp and initial/full TSP hashes.
The high-level selection algorithm/objective—not numeric target identity—is the
held-fixed claim unless sequences match. Primary analysis unit remains map-seed;
loops are descriptive.
