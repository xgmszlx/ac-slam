#!/usr/bin/python3
"""Pre-registered extension of the N0-R block: four seed pairs, unfiltered rule.

The two-pair R2 block could not settle whether the ON-minus-OFF difference is a
stable instrument effect or run-to-run variability: the pairs were not matched
(so the filtered rule could not be used) while the unfiltered rule flagged the
difference.  The extension adds seeds 41003 and 41004 under exactly the same
protocol and applies the rule that was written down *before* those episodes were
collected:

    pause if **all four** pairs show a same-sign, non-zero difference on the
    same watched outcome and the mean difference exceeds the measured reference
    repeatability; otherwise treat the online block as run-to-run variability
    and let the same-input replay decide.

Everything here is a pure function of the two per-suite analysis payloads, so
the rule can be re-evaluated later without re-running anything.
"""

import argparse
import json
from pathlib import Path

import n0_certification

OUTCOME_PAUSED = 'PAUSED_INSTRUMENTATION_REPAIR_FAILED'
OUTCOME_UNINFORMATIVE = 'ONLINE_BLOCK_UNINFORMATIVE_REPLAY_DECIDES'


def merge_outcomes(*payloads):
    """Union of the per-arm, per-seed outcome tables of several suites."""
    merged = {}
    for payload in payloads:
        for name, by_arm in (payload.get('outcomes') or {}).items():
            for arm, per_seed in by_arm.items():
                merged.setdefault(name, {}).setdefault(arm, {}).update(per_seed)
    return merged


def evaluate(suites, reference_repeatability=None, comparator_arm=None):
    payloads = [json.load(open(path)) for path in suites]
    return evaluate_from_payloads(payloads, reference_repeatability,
                                  comparator_arm)


def evaluate_from_payloads(payloads, reference_repeatability=None,
                           comparator_arm=None):
    comparator = comparator_arm or payloads[0].get('comparator_arm',
                                                   'n0r_provenance_off')
    merged = merge_outcomes(*payloads)
    unfiltered = {
        'comparator_arm': comparator,
        'outcomes': merged,
        # The pre-registered extension rule is deliberately unfiltered: the
        # verdict must not depend on the comparability filter.
        'comparability': {
            'source': 'filter_disabled',
            'sufficient': True,
            'comparable_seeds': [],
            'minimum_comparable_pairs': n0_certification.MINIMUM_COMPARABLE_PAIRS,
            'comparable_pair_count': None,
            'pairs': [],
            'incomparable_seeds': [],
            'classes': list(n0_certification.COMPARABILITY_CLASSES),
        },
    }
    rule = n0_certification.online_sanity_stop_rule(
        unfiltered, reference_repeatability)
    triggered = rule['triggered']
    per_pair = {}
    for entry in rule['entries']:
        per_pair[entry['outcome']] = {
            'arm': entry['arm'],
            'paired_differences_by_position': entry['paired_differences'],
            'mean_difference': entry['mean_difference'],
            'same_sign_nonzero': entry['same_sign_nonzero'],
            'threshold': entry['threshold'],
            'n_pairs': entry['n_comparable_pairs'],
        }
    same_condition_spread = {}
    for name, by_arm in merged.items():
        for arm, per_seed in by_arm.items():
            values = sorted(float(value) for value in per_seed.values())
            if len(values) < 2:
                continue
            same_condition_spread.setdefault(name, {})[arm] = {
                'values': values,
                'range': values[-1] - values[0],
            }
    return {
        'suites': [payload.get('suite_dir') for payload in payloads],
        'comparator_arm': comparator,
        'seeds': sorted(set(str(seed) for by_arm in merged.get(
            'final_edge_count', {}).values() for seed in by_arm)),
        'rule': {
            'pause_if': ('all seed pairs show a same-sign, non-zero difference '
                         'on the same watched outcome and the mean difference '
                         'exceeds the measured reference repeatability'),
            'otherwise': ('the online block reflects run-to-run variability and '
                          'the same-input replay decides'),
        },
        'per_outcome': per_pair,
        'triggered': triggered,
        'same_condition_spread': same_condition_spread,
        'outcome': OUTCOME_PAUSED if triggered else OUTCOME_UNINFORMATIVE,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', action='append', required=True,
                        help='n0_nonperturbation_decision.json, repeatable')
    parser.add_argument('--reference-repeatability')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    reference = json.load(open(args.reference_repeatability)) \
        if args.reference_repeatability else None
    payload = evaluate(args.suite, reference)
    with open(args.out, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    print(json.dumps({'outcome': payload['outcome'],
                      'triggered': [entry['outcome']
                                    for entry in payload['triggered']]},
                     indent=2))


if __name__ == '__main__':
    main()
