# Phase 4C-1 Prior Construction Protocol

Date: 2026-08-31

## Role

The builder is evaluation infrastructure only. It does not alter the online
Graph-Based planner, loop objective, Karto, navigation, D-opt, frontier logic, or
execution policies. A/B/C will consume the identical frozen XML for a map.

## Automatic pipeline

1. classify source pixels as free at gray >= 250;
2. remove one-pixel ray artefacts with a radius-1 binary opening and objects below
   16 pixels;
3. retain the largest 8-connected free component;
4. require 0.45 m robot clearance and compute a seeded medial axis;
5. sample a 1.0 m prior grid, cluster non-degree-2 skeleton pixels, and remove
   terminal branches shorter than 2.0 m;
6. split graph paths so straight prior segments do not exceed 12.0 m and validate
   every segment against traversable space;
7. choose the start at the prior node nearest the arithmetic mean of prior-node
   pixels;
8. emit Stage PNG/world/yaml and draw.io-compatible XML, then read the XML through
   the author's `read_drawio_to_nx` implementation.

Medial-axis RNG seed is 0. All parameters are serialized in
`prior_builder_validation.json` and each candidate `conversion_manifest.json`.

The 12 m infrastructure segment cap was frozen from the author priors before the
external opportunity gate: map3 and map8 median straight prior-edge lengths are
12.33 m and 14.29 m. An early 4 m builder prototype produced a 281-node Mexico
prior and a baseline Concorde problem that remained incomplete after more than
five minutes on seed 21001. No Mexico loop count or performance outcome existed at
that point. That prototype was discarded for baseline-scale incompatibility. The
12 m cap is unrelated to, and does not change, the frozen 4 m online active-loop
proxy.

## Validation

| candidate | nodes / edges / rank | connected | all edges traversable | author-reader round trip | start free | result |
|---|---:|---|---|---|---|---|
| CSAIL | 8 / 7 / 0 | yes | yes | exact | yes | PASS |
| Intel | 2 / 1 / 0 | yes | yes | exact | yes | PASS |
| Freiburg 079 | 2 / 1 / 0 | yes | yes | exact | yes | PASS |
| Mexico | 165 / 192 / 28 | yes | yes | exact | yes | PASS |

Two consecutive full rebuilds produced the same aggregate environment/source hash
`e491154b246d1b10fe86a222a7c87334dd67510447312a60d9ed1675557a355d`.
The opportunity outputs likewise reproduced byte-for-byte; after serializing all
frozen metrics/settings, their aggregate hash is
`7d037214c69ff58307ef1147014c3eb2d66b22c964e88d336b89e07e3e525f5b`.

Reproduction commands:

```bash
env -u PYTHONPATH /home/wcqw/anaconda3/bin/python \
  tools/build_phase4c1_external_environments.py
env -u PYTHONPATH \
  PATH=/home/wcqw/ac-slam/catkin_ws/tools/concorde:$PATH \
  /home/wcqw/anaconda3/bin/python tools/audit_phase4c1_opportunities.py
```

Offline builder environment: Python 3.12.7, NumPy 1.26.4, SciPy 1.13.1,
NetworkX 3.3, Pillow 10.4.0 and scikit-image 0.24.0. Runtime ROS remains Noetic;
the offline builder does not import the catkin runtime.

## Stage compatibility smoke

`radish_mexico.world` loaded in Stage 4.3.0 / `stage_ros` 1.8.0. `/stageros`
published scan, odometry, TF and ground-truth pose; observed start was
`(-6.25, -1.60, 0)`. This was a stationary startup-only check, not exploration.
Evidence is in `results/phase4c1/stage_smoke.json`.
