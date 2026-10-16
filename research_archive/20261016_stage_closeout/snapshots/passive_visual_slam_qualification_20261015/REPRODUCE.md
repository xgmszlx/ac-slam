# Reproduction notes

Use a **fresh copy/workspace**. Existing results are not overwritten by the runner. Do not rerun extraction/build helpers over these archived sources/results.

Pinned official ORB-SLAM3 commit and Pangolin v0.6 commit are in `audit/versions.json`; source archives are retained in `sources/`. `audit/orb_build_commands.json` and `audit/pangolin_build01.log` contain exact CMake commands. `code/build_orb.py` extracts the official archive selectively, changes only the OpenCV finder to 4.2, builds DBoW2/g2o and the RGB-D target, then extracts the vocabulary. The original CMake is retained; `patches/all_cmake_changes.patch` also shows the added independent example targets.

Native SLAM needs the existing system C++ dependencies and the locally built Pangolin. Evaluation used the existing default Python3.12 NumPy/SciPy/Pillow/Matplotlib environment; no packages were installed. `/usr/bin/python3` with system OpenCV4.2 was only used for input-color inspection. `code/evo_crosscheck.py` reads the preexisting evo package with bytecode writing disabled; it does not modify the old repository.

Data are the official TUM RGB-D `fr3/walking_xyz` and `fr3/sitting_xyz` tgz archives, kept in `data/`. URLs/range headers, byte counts, archive hashes and extraction budgets are in `audit/` and `protocol/`. `code/prepare_data.py <walking_xyz|sitting_xyz>` validates and extracts a previously completed archive in a fresh directory, constructs all unique RGB/depth matches within20ms and audits actual image reads. No GT is passed to the native executable. Its association text has no header because the original example does not skip comments.

The completed run commands are recorded verbatim in each `results/<sequence>/<run>/run.json`. In this workspace the normal run pattern was:

```bash
python3 code/run_native.py walking_xyz headless01 --headless
python3 code/run_native.py sitting_xyz headless01 --headless
```

These commands will refuse to replace the existing result directories. `rgbd_tum_headless.cc` differs from the official example only in the supported System viewer argument. Do not replace the failed default-viewer or observer directories with its results.

Offline evaluation example, using a **new evaluation destination** for any future re-analysis:

```bash
python3 code/evaluate.py data/rgbd_dataset_freiburg3_walking_xyz results/walking_xyz/headless01 results/walking_xyz/headless01/evaluation_reanalysis
python3 tests/test_evaluate.py
```

`code/diagnose.py` summarizes the one existing public-getter/GDB replay; it does not run SLAM. Its states belong to that replay only. `code/motion_review.py` compares GT and estimated motion over every evaluated1s pair, offline. The normal final trajectory, per-input observer states, and sparse keyframe trajectory have distinct semantics.

No additional native runs, masks, neural inference or method experiments are authorized by reproducing the report. The next-stage comparison remains the proposal in `NEXT_MINIMAL_COMPARISON.md`.
