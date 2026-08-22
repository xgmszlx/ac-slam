#!/usr/bin/python3
"""Run one Phase 2C positive-control trial with Karto loop diagnostics enabled.

This mirrors the Phase 2B positive control (Nearest-Frontier exploration then an
independent /MoveTo revisit of early Karto history) but enables the observation-only
loop diagnostics so the structured JSONL can be validated against the accepted
"Add one Loop closure" callback.
"""

import argparse
from pathlib import Path

from run_phase2b_positive_controls import ROOT, activated_environment, run_trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', required=True, type=int)
    parser.add_argument('--diagnostics-path', required=True, type=str)
    parser.add_argument('--run-id', required=True, type=str)
    parser.add_argument(
        '--output-root', type=Path,
        default=ROOT / 'results' / 'phase2c' / 'positive_control',
    )
    parser.add_argument('--explore-timeout', type=int, default=1800)
    parser.add_argument('--revisit-timeout', type=int, default=1800)
    parser.add_argument('--target-timeout', type=float, default=420.0)
    args = parser.parse_args()
    extra_launch_args = [
        'enable_loop_diagnostics:=true',
        'loop_diagnostics_path:={}'.format(args.diagnostics_path),
        'loop_diagnostics_run_id:={}'.format(args.run_id),
    ]
    success = run_trial(
        args.trial, args.output_root.resolve(), activated_environment(),
        args.explore_timeout, args.revisit_timeout,
        extra_launch_args=extra_launch_args,
        target_timeout=args.target_timeout,
    )
    print('positive_control_success={}'.format(success))


if __name__ == '__main__':
    main()
