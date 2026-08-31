# Phase 4C-0.5 Opportunity Adequacy

Date: 2026-08-31

## Audit method

The author XML prior, start pose, fixed covariance/D-opt wiring, seeded Concorde
solver, `connect_tsp_path`, and `offline_evaluate_tsp_path` were replayed without
Stage exploration. For map4/map7 seed 21001, the offline initial/full TSP exactly
matched the prior startup-only smoke records. No A/B/C execution or performance
outcome was observed.

The frozen gate is: every seed must contain at least two initial planned active-loop
actions, and the five seeds for a map must contain at least ten total opportunities.

## Selected-map results

| map | 21001 | 21002 | 21003 | 21004 | 21005 | total | gate |
|---|---:|---:|---:|---:|---:|---:|---|
| map4 | 1 | 1 | 1 | 1 | 1 | 5 | FAIL |
| map7 | 1 | 1 | 1 | 1 | 1 | 5 | FAIL |

map4 always selects initial loop vertex 14; map7 always selects vertex 13. Both
fail both parts of the gate. Subsequent online local replanning might create more
actions, as observed on map3, but counting that would require the prohibited full
exploration and would make adequacy depend on execution outcomes. It is therefore
not used to rescue either map.

## Blind fallback inventory

The next remaining author map/prior candidate, map8, was evaluated by the same
offline method without performance execution:

| map | per-seed counts | total | loop vertices | gate |
|---|---|---:|---|---|
| map8 | 3,3,3,3,3 | 15 | 20,38,35 | PASS |

map8 can replace one inadequate selected map. There is no second unselected author
map/prior candidate satisfying the gate: the inventory contains only map3, map4,
map7 and map8, with map3 already fixed as M1. Thus two adequate new environments
cannot currently be formed without expanding the map pool or revising the frozen
adequacy design. Neither action is authorized in this blocking audit.

All detailed paths, hashes and vertex sequences are stored under
`results/phase4c0/opportunity_adequacy/`.
