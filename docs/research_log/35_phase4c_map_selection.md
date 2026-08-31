# Phase 4C Blind Map Selection

> **Topology selection remains historically valid, but formal authorization is
> superseded by documents 40--41.** map4 and map7 both fail the subsequently frozen
> active-loop opportunity-adequacy gate.

Date frozen: 2026-08-31

## Inventory and selection rule

Author-provided map3, map4, map7, and map8 were inventoried before any new-map A/B/C
performance observation. Each has a Stage world, GT bitmap/YAML, author prior XML,
supported launch path, consistent size, and a free start cell. No new prior graph
was drawn.

Selection used only six structural features: aspect ratio, known-cell obstacle
fraction, free-space skeleton junction density, skeleton cycle count, median
corridor width, and prior-graph cycle rank. Features were population-z-scored over
the four author maps. With M1 fixed to map3, the pair maximizing
`d(M1,M2)+d(M1,M3)+d(M2,M3)` was selected. The medial-axis RNG is fixed to zero;
two reruns produce byte-identical inventory and selection files.

| map | size m | prior V/E/cycle | skeleton length m | junction density /100m | skeleton cycles | median width m |
|---|---|---|---:|---:|---:|---:|
| map3 | 74.0 x 74.0 | 36/60/25 | 1689.35 | 5.98 | 101 | 8.00 |
| map4 | 39.8 x 56.7 | 16/19/4 | 501.24 | 6.38 | 12 | 6.99 |
| map7 | 138.2 x 66.4 | 23/35/13 | 2278.04 | 9.17 | 127 | 6.40 |
| map8 | 86.8 x 69.36 | 39/58/20 | 1634.78 | 8.32 | 71 | 5.60 |

The frozen selection is **M2=map4, M3=map7**. The deterministic diversity score is
13.2162. Labels such as corridor-heavy or room/loop-rich are only descriptive; the
selection does not force those interpretations.

## Technical smoke

After selection was committed, a startup-only smoke was run once for map4 and
map7. For both maps, world launch, robot spawn, prior load, Concorde TSP generation,
core nodes/services, `/StartMapping`, `/map/info`, and map saving passed. The smoke
script never called `/StartExploration`; both records state
`formal_performance_run=false` and `exploration_started=false`.

- map4 seed-21001 predicted TSP length: 199.9384 m.
- map7 seed-21001 predicted TSP length: 380.9408 m.

These values are compatibility evidence only and were not used to choose the maps
or estimate A/B/C performance. All formal cells remain `NOT_STARTED`.

## Decision

Map/prior selection is **READY**. Selection occurred before all M2/M3 performance
runs, used no outcome, and requires no planner or prior modification.
