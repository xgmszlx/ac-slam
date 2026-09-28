# 67 — V14 prospective fixed-scan confirmatory validation

## Status

- **FACT:** The immutable v14 prospective run is stored at `results/realizability_pilot/p1_v14_confirmatory_20260928/`.
- **FACT:** Its preregistered final gate is `V14_PROSPECTIVE_NO_SUPPORT`.
- **FACT:** Its frozen next-step recommendation is `STOP_CURRENT_CONFIRMATORY_INTERVENTION_AND_ANALYZE_HETEROGENEITY`.
- **FACT:** The run contains 32 fresh qualification histories, 8 frozen canonical-history blocks, 24 technically valid physical captures, and 24 technically valid backend replays.

## Canonical artefacts

- Preregistration: `results/realizability_pilot/p1_v14_confirmatory_20260928/preregistration/v14_confirmatory_preregistration.json`
- Physical lock: `results/realizability_pilot/p1_v14_confirmatory_20260928/collection/PHYSICAL_COLLECTION_LOCK.json`
- Backend lock: `results/realizability_pilot/p1_v14_confirmatory_20260928/collection/BACKEND_REPLAY_LOCK.json`
- Primary block table: `results/realizability_pilot/p1_v14_confirmatory_20260928/analysis/primary_block_table.csv`
- Primary summary: `results/realizability_pilot/p1_v14_confirmatory_20260928/analysis/primary_summary.json`
- Final decision: `results/realizability_pilot/p1_v14_confirmatory_20260928/decision/final_gate.json`
- Full A–K report: `results/realizability_pilot/p1_v14_confirmatory_20260928/V14_FINAL_REPORT.md`

## Frozen interpretation

- **MEASURED OBSERVATION:** `D_sweep > 0` occurred in 4/8 blocks: Target A 0/4 and Target B 4/4.
- **MEASURED OBSERVATION:** Mean `D_sweep` was `-0.0168477`; the target-stratified bootstrap 95% interval was `[-0.0687043, 0.0333040]`.
- **INFERENCE:** The universal broad-sweep hypothesis did not pass its preregistered support gate.
- **UNKNOWN:** The complete target-dependent sign reversal does not, by itself, identify action dose, backend measurement realization, pre-graph context, or scene geometry as the causal moderator.

This file is only a research-timeline index. It does not recompute, amend, or reinterpret the frozen v14 scientific result. Any subsequent mechanism audit must use a separate result root and must remain labelled `POST_CONFIRMATORY_EXPLORATORY`.
