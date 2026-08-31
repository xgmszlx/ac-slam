# Phase 4C-1 Environment Gate

Date: 2026-08-31

## A Repository

The verified starting checkpoint was
`cbd86bb29524d4ad3cbaaff37314addb8e0f4704` on
`research/phase4c0-scientific-audit`. Phase 4C-1 adds only external-map sources,
deterministic conversion/prior tooling, offline opportunity evidence and protocol
documentation. No formal performance run was started.

## B Frozen M2

`map8`: **PASS**, fixed at `3,3,3,3,3` planned opportunities (15 total).

## C External Candidates

Four traceable Radish/StachnissLab indoor maps were converted. All conversions and
prior round trips pass; Intel and Freiburg fail scale, while CSAIL and Mexico pass
scale. All failed candidates remain recorded.

## D Prior Construction

Automatic and reproducible. Parameters and two-run byte-stability are documented
in `43_phase4c1_prior_construction_protocol.md`. The selected Mexico prior is
connected, traversable, author-reader-compatible and fixed at 165 vertices,
192 edges and cycle rank 28.

## E Opportunity Adequacy

CSAIL/Intel/Freiburg: `0,0,0,0,0`, FAIL. Mexico: `11,11,11,11,11`, total 55,
PASS under the unchanged >=2 per-seed AND >=10 total criterion.

## F Selected M3

`radish_mexico`, sourced from the public Acapulco Convention Center Radish map. It
is the only candidate passing provenance, conversion, prior, scale and opportunity
gates and is topologically distinct from map3/map8 by the frozen metric audit.

## G Scientific Neutrality

- selection occurred before any M3 A/B/C outcome;
- the prior was generated and frozen before performance;
- the offline gate observed no closure, accuracy, cost or map-quality output;
- no online method, 4 m proxy, 7-scan H*, 12 m/24-waypoint/0.5 m repair setting,
  Karto, D-opt, TSP objective, frontier or navigation parameter changed;
- target attribution and 5 m method-neutral ROI remain frozen.

## H Formal Matrix Ready

**YES, protocol-ready but not started.** On later authorization: reuse map3
Phase4B raw runs through the neutral evaluator; run 15 new map8 and 15 new M3
counterbalanced A/B/C trials. This yields 3 maps x 5 seeds x 3 methods.

## I Remaining Risks

Target-attributable closures may remain rare; only Karto is tested; CSAIL/Mexico
raster scale includes inference; the external Stage geometry is a conversion from
a SLAM occupancy rendering rather than surveyed ground truth; Mexico's 165-node
prior increases exact-TSP/runtime load; the 4 m proxy remains uncalibrated; and
Stage/navigation stochasticity remains. Opportunity PASS is not evidence of
execution or closure success.

## J Decision

**READY_FOR_PHASE4C_FORMAL**

# STOP
