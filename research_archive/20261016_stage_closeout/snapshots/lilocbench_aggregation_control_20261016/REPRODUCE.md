# Executed one-run control and offline checks

This run budget is CLOSED: max1, used1, no retry. Do not execute another estimator as part of this task.

Read-only sources:
- `/home/wcqw/lilocbench_amcl_validation_20261016`: fixed official source/build, map, original and certified topic-alias bag, GT, baseline outputs.
- `/home/wcqw/lilocbench_amcl_recovery_control_20261016`: exact executable dependency/PF log library, A1-R0/A2-R0, evaluator/collector code.
- `/home/wcqw/lilocbench_likelihood_audit_20261016`: frozen candidate definitions and numerical results.

Before any estimator launch:
1. `source /opt/ros/noetic/setup.bash` and system `/usr/bin/python3 code/read_inputs.py` read original bag for physical beam / odom identity.
2. Existing Python/scipy `code/provenance.py` confirmed candidate provenance from all four existing trajectories.
3. `code/prepare_run.py` copied only runner/collector/evaluator scripts; no native compilation. It asserted the only parameter-field differences to A1-R0 are model and max_beams conversion, loaded the exact prior PF library and froze hashes.

One actual run (record only; not an authorization to rerun):

```bash
source /opt/ros/noetic/setup.bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 code/run.py A0_91_R0
```

Native executable is the prior official-source binary, `--run-from-bag` against the same full `lt_changes_0_native_topics02.bag`. Runner's `LD_LIBRARY_PATH` explicitly prioritizes the old recovery-control PF library then the original v2 libraries. Actual command/env/rpath/parameters, Gaussian seed1702, resource log and cleanup exits are retained. No new native patch, source build, bag or simulator was created. No online GT access; original registered initialization params reused.

Executed offline after run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 code/evaluate_one.py A0_91_R0
PYTHONDONTWRITEBYTECODE=1 python3 code/analyze.py
PYTHONDONTWRITEBYTECODE=1 python3 code/final_checks.py
```

Full evaluator math is an unchanged copy of the prior frozen evaluator; no spatial alignment. Full official endpoint padding remains. Early supplement uses common native-supported GT samples <=10s. Additional raw-output error and odom step checks have no spatial GT fit and no extrapolation. Inspection-only `particle_and_step_stats.json` summarizes existing native log quantities; it does not reconstruct ancestry. Its standalone generator is `code/particle_and_step_stats.py`, retained from the executed inline calculation.

New raw output is under `results/A0_91_R0`; raw original data/GT remain in the old source directory. Main comparisons use actual seed1702 A1-R0; old A0-102-ON is reference only. The user requested a complete run this turn, explicitly superseding the prior short-only recommendation.

`protocol/attempts_final.json` closes the one-run budget. Protection hashes cover listed historical files and git state; not an unbounded assertion about every old image. Running derived evaluation commands again would overwrite this new directory's derived files, so preserve the delivered snapshot for independent reproduction.
