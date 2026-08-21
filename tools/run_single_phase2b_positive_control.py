#!/usr/bin/python3
"""Run one explicitly numbered Phase 2B positive-control trial."""

import argparse
from pathlib import Path

from run_phase2b_positive_controls import ROOT, activated_environment, run_trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', required=True, type=int)
    parser.add_argument(
        '--output-root', type=Path,
        default=ROOT / 'results' / 'phase2b' / 'positive_control',
    )
    parser.add_argument('--explore-timeout', type=int, default=1800)
    parser.add_argument('--revisit-timeout', type=int, default=1800)
    args = parser.parse_args()
    success = run_trial(
        args.trial, args.output_root.resolve(), activated_environment(),
        args.explore_timeout, args.revisit_timeout,
    )
    print('positive_control_success={}'.format(success))


if __name__ == '__main__':
    main()
