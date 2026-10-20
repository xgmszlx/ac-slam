# Offline reproduction

Environment: existing `/home/wcqw/anaconda3/bin/python` (NumPy 1.26.4, SciPy 1.13.1, Matplotlib 3.9.2). No install, SLAM invocation or estimator compilation.

The fixed input paths and SHA256 values are in `protocol/analysis_frozen.json` and `protocol/protection_before.json`. Original logs are from `passive_rgbd_combo_20261019/e2e_20261020` and `passive_rgbd_deletion_ablation_20261020`; equivalent published logs are archived beside this directory under `20261020_rgbd_combo_e2e` and `20261020_rgbd_deletion_ablation`. GT must remain the original Bonn groundtruth file matching the registered hash. No raw RGB-D, GT, models or binaries are republished.

On the original workstation, within this analysis directory:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/analyze.py
PYTHONDONTWRITEBYTECODE=1 /home/wcqw/anaconda3/bin/python code/test_analysis.py
```

On another machine, first copy this directory and update only the input path entries in a copy of the JSON and `gtpath` in a copy of the script; verify all original file hashes. Do not overwrite the archived protocol. `freeze.py` documents the initial registration and is not part of rerunning analysis.

`aligned_frames.csv`: all 589 same-stamp frames; blank ATE/RPE means no legal saved-evaluator support, not zero error. RPE is forward 1s from the row timestamp. `windows.csv`: all ten fixed windows, including unfavorable/unchosen cases; counts cover the full physical window, RPE pairs have both endpoints within it. The reported three cases are outcome-selected exploratory illustrations. `correlations.csv`: all raw/phase/phase-motion/first-difference coefficients; `summary.json` also contains paired-difference coefficients and GT motion context. Phase-centered Spearman means ranks of phase-centered residuals, not rank-space partial correlation. No p-values, sample-independent uncertainty intervals or causal claims are computed.

The three PNGs are generated from existing tables only. Eight software/data checks cover timing, identity, constants/missing data, phase removal, saved-evaluation consistency and window endpoint constraints. These checks do not validate a SLAM mechanism.

Publication formatting check initially flagged CRLF in the new derived CSVs. These files and their writer were changed to LF; parsed CSV cells are identical. Original input CSVs remain unchanged.
