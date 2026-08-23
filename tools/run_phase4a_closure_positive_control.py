#!/usr/bin/python3
"""Phase 4A Stage C (positive-control route): validate /Mapper/loop_closed 1:1.

Uses the Phase 2B independent positive control (Nearest-Frontier history
exploration, then an independent /MoveTo revisit of early Karto history, which
reliably produced an accepted closure 3/3 in Phase 2B) with loop diagnostics
enabled, then validates 1:1:
  Karto internal accepted (diagnostics ACCEPTED record + 'Add one Loop' callback)
  == published loop_closed event (PHASE4A_LOOP_CLOSED in rosout, current_scan id)
Checking: count 1:1, no duplicates, no missed, no wrong attribution, seq contiguous.
"""

import argparse
import json
from pathlib import Path

from run_phase2b_positive_controls import ROOT, activated_environment, run_trial
from run_phase4a_targeted import closure_validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', required=True, type=int)
    parser.add_argument('--output-root', type=Path,
                        default=ROOT / 'results' / 'phase4a' / 'closure_event_validation' / 'positive_control')
    parser.add_argument('--explore-timeout', type=int, default=2400)
    parser.add_argument('--revisit-timeout', type=int, default=2400)
    parser.add_argument('--target-timeout', type=float, default=420.0)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    run_dir = args.output_root / 'trial_{:02d}'.format(args.trial)
    diagnostics_path = run_dir / 'karto_loop_diagnostics.jsonl'
    run_id = 'pc_closure_trial{:02d}'.format(args.trial)
    extra_launch_args = [
        'enable_loop_diagnostics:=true',
        'loop_diagnostics_path:={}'.format(diagnostics_path),
        'loop_diagnostics_run_id:={}'.format(run_id),
    ]
    env = activated_environment()
    success = run_trial(
        args.trial, args.output_root.resolve(), env,
        args.explore_timeout, args.revisit_timeout,
        extra_launch_args=extra_launch_args,
        target_timeout=args.target_timeout,
    )
    print('positive_control_success={}'.format(success))
    cv = closure_validate(run_dir, diagnostics_path, None, env)
    print('CLOSURE_VALIDATION: {}'.format(json.dumps(cv, indent=2, sort_keys=True)))
    (run_dir / 'closure_event_validation.json').write_text(
        json.dumps(cv, indent=2, sort_keys=True) + '\n')
    if cv.get('inconclusive_no_closure'):
        print('WARNING: positive control succeeded but NO accepted closure event found; '
              '1:1 validation INCONCLUSIVE.')
    elif cv.get('one_to_one') and cv.get('attribution_ok') and cv.get('no_duplicates') \
            and cv.get('seq_contiguous'):
        print('CLOSURE_VALIDATION: PASS (1:1, attribution ok, no duplicates, seq contiguous)')
    else:
        print('CLOSURE_VALIDATION: FAIL (see closure_event_validation.json)')


if __name__ == '__main__':
    main()
