# Phase 4C-0.5 Attribution Neutrality

Date: 2026-08-31

## Blocking finding

The Phase 4C-0 attribution target was not neutral. It replayed the actual
`oracle_mode` branch: A used the original V0 scan set, B used the enlarged
Always-Trace window, and C repair used its bounded enlarged segment. Consequently
B/C could obtain a larger intersection target solely because treatment enlarged
execution. The previous definition and its A=0, B=2, C=2 result are superseded.

## Frozen method-neutral H*

For each planned loop action, H* is constructed before the execution-policy branch:

1. take the method-neutral high-level selected loop vertex;
2. reproduce the original baseline anchor: among pre-loop historical scans assigned
   to that vertex, choose the scan closest to the prior-vertex position;
3. take exactly seven chronological pre-loop Karto keyscans beginning at that
   anchor.

`K=7` and forward direction come from the author's V0 reliable-loop rule and predate
Phase 3A/4A/4B. Accepted Phase 4B chains were not used to choose K. H* never reads
`oracle_mode`, repair decisions, actual replay length, or accepted-chain identity.
All 63 Phase 4B action targets have size seven.

Because A/B/C are independent stochastic runs, numeric scan IDs cannot literally
be shared across runs. Neutrality therefore means the same selected vertex,
pre-branch anchor operator, direction and fixed cardinality—not equal numeric IDs.
This residual cross-run history variation remains explicit; it is not treatment-
specific target expansion.

## Neutral Phase 4B reanalysis

| event | neutral H* result |
|---|---|
| A/21002 v8, chain 15--19 | temporal; H*=0--6 |
| C/21003 v21, chain 506--511 | target; H*=505--511 |
| B/21004 v15, chain 161--164 | temporal; H*=171--177 |
| B/21004 v22, chain 548--551 | temporal; H*=554--560 |
| C/21004 passive chain 349--352 | passive/unrelated |
| C/21005 v26, chain 413--418 | temporal; H*=406--412 |
| C/21005 v8, chain 15--18 | temporal; H*=0--6 |

Final action-level target-attributable counts are:

- A Original: **0/21**;
- B Always-Trace: **0/21**;
- C Selective: **1/21**.

Across accepted events there is one target-attributable, five temporal-only, and
one passive/unrelated event. This result was retained despite removing both B target
events and one C target event from the prior table.

## Local ROI neutrality

Local consistency uses a 5.0 m circle centred on the high-level prior-graph loop
vertex. It never uses actual V0/Always-Trace/repair paths. Phase 4B loop-vertex and
ROI sequences are identical across A/B/C for all five seeds; ROI neutrality is
PASS.

Machine-readable outputs are in
`results/phase4c0/attribution_neutrality/`.
