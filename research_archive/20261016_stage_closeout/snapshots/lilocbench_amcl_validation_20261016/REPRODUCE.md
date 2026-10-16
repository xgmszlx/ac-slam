# Executed commands and artifacts

All runs are completed records, not instructions to expand the matrix. Each `results/<id>/run.json` contains exact commands and exits; `parameters.json` and `parameters_after.json` hold actual ROS parameters. Existing result directories are exclusive-create and cannot be overwritten by these scripts.

Official evaluation (unmodified):

```bash
PYTHONPATH=sources/eval_deps MPLBACKEND=Agg python3 \
  sources/LILocBench-68e86f33ae3ff660444b92093fb98ca4d5633b46/src/evaluate.py \
  --config-file sources/LILocBench-68e86f33ae3ff660444b92093fb98ca4d5633b46/config/config_public.yaml \
  --gt-poses-dir data/gt --localizer-dir data/example \
  --output-dir results/official_example
```

Effective native input is the original raw serialized `/tf` plus front scan, only topic aliases `tf` / `base_scan`; integrity proof in `audit/native_bag_topic_mapping.json`. Installed executable run, e.g.:

```bash
/opt/ros/noetic/lib/amcl/amcl --run-from-bag \
  /home/wcqw/lilocbench_amcl_validation_20261016/data/static_0_native_topics02.bag \
  __name:=amcl
```

This command had a dedicated master at11331, map_server with official yaml, parameters set before construction, use_sim_time=false, observer ready, and process resources measured. Refer to `code/run_native_offline.py` for exact setup/cleanup; the command alone without that setup is not the experiment. Neither runner nor observer reads GT files. The one permitted GT initial-pose projection is prewritten in frozen parameters.

Diagnostics v1 source/build patch and v2 Gaussian-seed correction are separate and hashed. Original native algorithms and formulas are retained. v1 nominal seeds are not the actual initial Gaussian seed; use `audit/effective_seed_register.json`, not directory names. `audit/gaussian_seed_test.json` checks the actual reseed point. `results/processing_variability.json` records accepted scan-update identities; not every same-seed run has the same native threshold-selected update set.

Analysis commands executed after estimators stopped:

```bash
source /opt/ros/noetic/setup.bash
/usr/bin/python3 code/export_scan_samples.py
MPLBACKEND=Agg python3 code/analyze_results.py
```

Main metrics are official planar no-alignment APE at GT stamps, with explicit endpoint-padding and support audits. CSV includes all16 valid native offline runs; earlier failed/invalid launches remain outside the scientific table and are preserved. Full beam events and sensor-update identities are in individual run folders. `observations.jsonl` includes sampled particle clouds and observed TF caller identity. No globally sampled pose/GT stream is used for initialization beyond the registered single first pose.
