# Phase 4C Radish Mexico Results

Date: 2026-09-14

## Completion status

All 15 selected Mexico runs are retained `EXPERIMENTAL_FAILURE` outcomes. Fourteen
returned Explore action status 4; seed 21004/B reached the frozen 18,001 s hard
timeout. Required ROS processes, Stage, Karto, and artifact writers launched, so
these outcomes do not satisfy the frozen technical-invalid definition.

## Planned versus executed loops

The append-only `events.csv` records eleven `LOOP_INSERTED` events per run.
Consequently each method planned 55 active loops across five seeds, while none
became an executable active-loop interval:

| Method | Planned | Executed | TARGET_ATTRIBUTABLE | R_target |
| --- | ---: | ---: | ---: | --- |
| A Original | 55 | 0 | 0 | N/A |
| B Always-Trace | 55 | 0 | 0 | N/A |
| C Selective | 55 | 0 | 0 | N/A |

The denominator for `R_target` is executed loops. It must therefore remain N/A,
not zero. The zero active distance/time values are also structural consequences
of never entering loop execution and must not be interpreted as efficient loop
behavior.

All A/B/C initial TSPs, full TSPs, and recovered planned-loop sequences matched
within each seed. Seeds 21001--21004 planned vertices
`[59,41,82,69,58,166,87,106,100,64,65]`; seed 21005 replaced vertex 64 with
153. Thus the failure is downstream of high-level selection divergence.

## Failure evidence

The runs accumulated long ordinary exploration trajectories and passive Karto
events before failing. Aggregate passive/unrelated accepted events were 58 for
A, 50 for B, and 59 for C, but no accepted event can be attributed to an active
interval because no such interval occurred.

Representative terminal evidence is:

```text
Navigator: No way between robot and goal!
Navigator: Exploration has failed!
```

The same logs repeatedly show `path_planner.handle_edge_distance` callbacks
receiving negative vertex identifiers not present in the prior graph, raising
`networkx.exception.NodeNotFound`. This is a real runtime anomaly that plausibly
contributed to replanning instability, but the present data do not isolate it as
the unique cause of all failures. No planner or skip logic was modified after
observing it.

## Descriptive partial-run metrics

Trajectory and map files exist and were evaluated consistently, but because all
runs failed before completing the intended experiment, these values describe
different partial trajectories and are not valid evidence of method superiority.
For transparency, method means were:

| Method | APE (m) | RPE trans. (m) | RPE rot. (deg) | Boundary F1 | Sym. boundary dist. (m) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 7.260 | 0.07340 | 3.653 | 0.1607 | 1.526 |
| B | 0.175 | 0.03458 | 1.772 | 0.1546 | 1.586 |
| C | 2.039 | 0.04961 | 3.847 | 0.1462 | 1.830 |

A and C include severe seed-level outliers; aggregating the means as if they
were complete matched trials would be misleading.

## Interpretation boundary

Mexico strongly demonstrates an execution-stage generalization failure of the
full experimental system: planned loop actions never became executed actions.
It does not test whether Always-Trace or Selective execution changes Karto loop
formation, because neither intervention was reached.
