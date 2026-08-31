# Phase 4C-0 Handoff Audit

Date: 2026-08-31

## Repository state

- Root repository: `/home/wcqw/ac-slam`
- Phase 4C-0 branch: `research/phase4c0-scientific-audit`
- Phase 4B handoff commit: `cd2b8b54488a65b3f9f4dc9bcf76a1eea0194e8d`
- Frozen online baseline: `7993bf8b93e503b352d89e3992b8e5d7b08e4459`
- Frozen navigation/Karto dependency: `062283d364d891603a546b83e557ab638ffaa163`
- Root remote was inspected but nothing was pushed.

The two nested repositories have no tracked modifications. They contain historical
untracked author outputs, including the two Phase 4C-0 smoke artifacts; these were
not deleted, added to the root experiment dataset, or interpreted as performance
runs.

## Phase 4B artifact verification

The four handoff documents (26--29), all five formal seed directories, raw logs,
maps, trajectories, manifests, and aggregate files were checked. The formal map3
dataset contains 15/15 completed and valid A/B/C runs. The raw artifacts agree with
the reported counterbalanced order, frozen commits, diagnostics-off policy, and
per-seed byte-identical TSP records. The interrupted seed-21004/C attempt and the
excluded seed-21001 pipeline pilot remain clearly separated from formal data.

Evidence priority for Phase 4C is frozen as:

1. immutable raw run artifacts and per-run manifests;
2. regenerated tables from those artifacts;
3. narrative handoff documents.

No raw Phase 4B artifact was overwritten. New mapping results are stored under
`aggregate_v2`, not the original `aggregate` directory.

## Handoff correction required by the audit

Phase 4B's old accepted-active-loop definition used event timing inside an active
interval. That definition is reproducible but is not strong enough to establish
that the matched historical chain was the active action's intended target. The raw
logs contain current-keyscan acquisition records and accepted chain IDs, so all 15
runs can be reanalysed with the stronger Phase 4C definition. The resulting change
is documented in document 31; old tables remain intact as historical evidence.

## Frozen method and terminology

No online planner, prior, TSP, frontier/skip rule, D-opt objective, Karto threshold,
or navigation parameter was changed during Phase 4C-0. The 4.0 m signal is called a
**configuration-inspired lightweight prototype proxy**, never a theoretical Karto
threshold. Runtime repair semantics are recorded as a **nominal 12 m
repair-extension budget with possible terminal-segment overshoot**. Formal records
must store `nominal_budget`, `actual_generated_length`, and
`actual_executed_length`.

## Audit conclusion

The Phase 4B dataset is usable as M1 and supports a uniform strong-attribution
offline reanalysis. The handoff is verified, with the old temporal attribution and
map-IoU interpretation explicitly superseded for Phase 4C claims.
