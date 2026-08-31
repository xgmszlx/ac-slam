# Phase 4C-1 Candidate Topology Audit

Date: 2026-08-31

## Frozen scale gate

Before opportunity results, primary-M3 eligibility required width >= 45 m,
height >= 30 m and free area >= 500 m2. This rejects tiny point-navigation layouts
without relaxing the opportunity criterion.

| environment | size m | free m2 | skeleton m | junctions / 100 m | skeleton cycles | median width m | prior V/E/rank | scale |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| map3 (reference) | 74.0 x 74.0 | 4612.6 | 1689.3 | 5.98 | 101 | 8.00 | 36/60/25 | frozen M1 |
| map8 (reference) | 86.8 x 69.36 | 5357.0 | 1634.8 | 8.32 | 71 | 5.60 | 39/58/20 | frozen M2 |
| Radish CSAIL | 48.2 x 66.8 | 649.8 | 258.5 | 28.24 | 31 | 1.70 | 8/7/0 | PASS |
| Radish Intel | 28.95 x 29.05 | 467.1 | 151.1 | 44.99 | 25 | 1.61 | 2/1/0 | FAIL |
| Radish Freiburg 079 | 45.55 x 18.40 | 318.4 | 29.9 | 43.46 | 12 | 2.09 | 2/1/0 | FAIL |
| Radish Mexico | 101.55 x 53.85 | 3873.2 | 2225.4 | 39.23 | 1307 | 3.71 | 165/192/28 | PASS |

The external-map skeleton metrics are computed after the documented raster
cleaning and 0.45 m clearance operation. They should not be interpreted as an
architectural census: noisy mapped boundaries inflate local skeleton junction and
cycle counts. Selection uses the same deterministic metric implementation for all
external candidates; map3/map8 remain reference points from the frozen Phase 4C-0
inventory.

CSAIL passes scale but its simplified prior is a tree with only eight nodes. Intel
and Freiburg fail physical scale and produce two-node priors. Mexico has the only
large, multi-region, cyclic external prior in this inventory.

Machine-readable values are in `results/phase4c1/topology_metrics.csv` and
`candidate_inventory.csv`.
