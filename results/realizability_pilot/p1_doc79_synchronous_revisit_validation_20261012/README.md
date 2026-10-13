# Doc-79 — synchronous revisit observation validation (results root)

`DOC79_SYNCHRONOUS_REVISIT_OBSERVATION_VALIDATION`.
Bounded prospective technical + mechanism diagnostic on the frozen continuous
revisit protocol (Doc 77/78), branch `research/phase4c-formal`, baseline
`cac55c4bb817705529bee6f39fbdf7cfb698677c`.

Everything in this directory is new. The Doc-77 suite
(`results/realizability_pilot/p1_continuous_revisit_actions_20261010/`) and the
Doc-78 review root
(`results/realizability_pilot/p1_continuous_boundary_review_20261012/`) are
frozen and are only read, never written.

## Layout

```
protocol/   preregistration.json, frozen_run_manifest.json, frozen_hashes.json,
            frozen_analysis_plan.md
audit/      source_execution_path.md, native_scan_pipeline.md,
            snapshot_barrier_design.md, provenance_integrity_design.md,
            observability_patch.md, observability_patch.diff,
            build_manifest.json, runtime_provenance.json,
            production_integrity.json
runs/       <episode_id>/attempt_NN/  (spec, streams, sync+topic graphs,
            provenance JSONL, ledger, manifests, rosout, driver log, result)
analysis/   run_ledger.csv ... final_gate.json  (written by analysis.py)
figures/    fig1..fig6 (png+svg, produced by figures.py)
```

## Observation chain (isolated build)

The mapper runs from the overlay workspace `doc79_ws` (patched copy of
`nav2d_karto` with observation-only telemetry + a serialized boundary export
service). The production binaries in `catkin_ws/devel` are untouched
(`production_integrity.json`, `build_manifest.json`). Every boundary performs:
native-scan watermark -> serialized provenance flush + synchronous pose-graph
dump -> file/run-id/hash verification -> old-topic cache snapshot -> manifest +
ledger entry.

## Reproduction

```bash
# plan / run (8-attempt budget, fixed order, policy stop)
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/doc79_sync_validation/runner.py plan
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/doc79_sync_validation/runner.py run --policy stop

# analysis + figures
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/doc79_sync_validation/analysis.py \
  --suite-dir results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012
/usr/bin/python3 tools/realizability_pilot/doc79_sync_validation/figures.py \
  --suite-dir results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012

# observation-chain regression tests (pre-run qualification)
/usr/bin/python3 tools/realizability_pilot/doc79_sync_validation/test_doc79.py
```

## Documents

- research log: `docs/research_log/79_synchronous_revisit_mechanism_validation.md`
- review packet: `REVIEW_PACKET.md` (includes `INDEPENDENT_REVIEW_HANDOFF`)
- status: `STATUS.md`
