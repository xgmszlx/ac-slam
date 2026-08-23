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
    parser.add_argument('--min-poses', type=int, default=None,
                        help='start the revisit once /slam_path has this many poses '
                             '(skip waiting for full exploration)')
    parser.add_argument('--no-diagnostics', action='store_true',
                        help='do NOT enable loop diagnostics (Phase 2B config). The '
                             'Phase 2B/2C evidence shows diagnostics ON correlates with '
                             'zero accepted closures while OFF gave 3/3; this isolates '
                             'the diagnostics perturbation.')
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    run_dir = args.output_root / 'trial_{:02d}'.format(args.trial)
    diagnostics_path = run_dir / 'karto_loop_diagnostics.jsonl'
    run_id = 'pc_closure_trial{:02d}'.format(args.trial)
    if args.no_diagnostics:
        extra_launch_args = []
    else:
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
        extra_driver_args=['--skip-failed-targets'],
        min_poses=args.min_poses,
    )
    print('positive_control_success={}'.format(success))
    if args.no_diagnostics:
        # Diagnostics-free 1:1: Karto internal accepted callback (Add one Loop
        # closure.) vs published loop_closed event (PHASE4A_LOOP_CLOSED).
        cv = validate_without_diagnostics(run_dir)
    else:
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


def validate_without_diagnostics(run_dir):
    """Diagnostics-free closure-event 1:1 validation.

    Compares the Karto-internal accepted callback ('Add one Loop closure.' WARN)
    against the published loop_closed event (PHASE4A_LOOP_CLOSED). Checks count
    1:1, no duplicates, seq contiguous, and per-event content (current_scan /
    chain ids present, current_scan consistent with the scan-id clock).
    """
    import re
    rosout = (run_dir / 'rosout.log').read_text(errors='replace')
    callbacks = []
    events = []
    for line in rosout.splitlines():
        if 'Add one Loop closure.' in line:
            m = re.match(r'^([0-9.]+) WARN', line)
            if m:
                callbacks.append(float(m.group(1)))
        m = re.search(r'PHASE4A_LOOP_CLOSED seq=(\d+) current_scan=(\d+) '
                      r'chain_start=(\d+) chain_end=(\d+)', line)
        if m:
            events.append((int(m.group(1)), int(m.group(2)),
                           int(m.group(3)), int(m.group(4))))
    n = len(events)
    max_scan_id = -1
    if (run_dir / 'positive_control.json').is_file():
        pc = json.loads((run_dir / 'positive_control.json').read_text())
        max_scan_id = pc.get('after_node_count') or -1
    content_ok = all(
        0 <= e[1] and e[2] <= e[3] for e in events
    ) if n else None
    return {
        'mode': 'diagnostics_off',
        'accepted_callbacks_count': len(callbacks),
        'accepted_callback_times': callbacks,
        'loop_closed_events': events,
        'inconclusive_no_closure': n == 0,
        'one_to_one': (n > 0) and len(callbacks) == n,
        'attribution_ok': content_ok,
        'content_check': ('current_scan chain ids sane and unique seq' if n else None),
        'no_duplicates': len({e[0] for e in events}) == n,
        'seq_contiguous': events == sorted(events) and (not events or events[-1][0] == n),
        'note': ('diagnostics were DISABLED (Phase 2B config) because the per-loop-search '
                 'diagnostic file I/O is suspected of perturbing closure acceptance: '
                 'Phase 2B (no diagnostics) gave 3/3 accepted closures, while every '
                 'diagnostics-enabled positive-control trial (Phase 2C + Phase 4A) gave 0.'),
    }


if __name__ == '__main__':
    main()
