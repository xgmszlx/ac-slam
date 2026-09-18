#!/usr/bin/python3
"""N0 certification: combine the online sanity check and the same-input replay.

The two stages answer different questions and both are required before the
instrument may be called neutral:

* **online sanity** (``n0r_sanity`` suite): does a *small* matched-pair block see
  a same-direction shift after the repair?  A persistent shift here is
  ``PAUSED_INSTRUMENTATION_REPAIR_FAILED``: the repair did not work, so there is
  nothing to certify and N1 must not run.
* **same-input replay**: does the instrument change Karto's constraint
  generation for a bit-identical input stream?  This is the decisive evidence,
  because it removes scheduler, planner and Stage variability entirely.

Certification is granted only when the online sanity block shows no shift
beyond the measured repeatability *and* the replay is neutral.
"""

import argparse
import json
from pathlib import Path

STATE_CERTIFIED = 'OUTCOME_MEASUREMENT_STABLE'
STATE_REPAIR_FAILED = 'PAUSED_INSTRUMENTATION_REPAIR_FAILED'
STATE_NOT_NEUTRAL = 'INSTRUMENTATION_NOT_NEUTRAL'
STATE_INCONCLUSIVE = 'PAUSED_INSTRUMENTATION_INCONCLUSIVE'

#: outcome classes the online sanity stop rule watches, with the numerical
#: tolerance used for each (counts are integers, so any non-zero shift is real).
SHIFT_CLASSES = (
    ('final_edge_count', 0.0),
    ('final_node_count', 0.0),
    ('new_keyscans', 0.0),
    ('target_geodesic_mean_m', 1e-9),
)


#: outcome classes that must agree inside a seed pair before that pair may be
#: used for (or against) the instrument. They describe the *pre-probe* state,
#: i.e. the mapping phase that both arms of a pair are supposed to share.
COMPARABILITY_CLASSES = ('preprobe_node_count', 'preprobe_edge_count')

#: pre-registered minimum number of comparable pairs before any verdict other
#: than "not enough evidence" may be issued.
MINIMUM_COMPARABLE_PAIRS = 2


def pair_comparability(sanity):
    """Check that both arms of a seed pair started the probe from the same
    pre-probe graph.

    A pair whose arms entered the probe with different graphs was never
    matched, so any downstream difference is at least partly protocol
    variability.  Such a pair cannot be used to accuse the instrument, and it
    cannot be used to exonerate it either.
    """
    gate = sanity.get('preprobe_gate') or {}
    gate_pairs = gate.get('measured_pair_deviation') or []
    if gate_pairs:
        pairs = []
        for pair in gate_pairs:
            seed = str(pair.get('seed'))
            passed = bool(pair.get('passed', True))
            pairs.append({
                'seed': seed,
                'arms': {pair.get('arm_a'): pair.get('preprobe_node_count_a'),
                         pair.get('arm_b'): pair.get('preprobe_node_count_b')},
                'comparable': passed,
                'differences': {},
                'source': 'preprobe_gate',
            })
        comparable = [e for e in pairs if e['comparable']]
        return {
            'source': 'preprobe_gate',
            'classes': list(COMPARABILITY_CLASSES),
            'minimum_comparable_pairs': MINIMUM_COMPARABLE_PAIRS,
            'pairs': pairs,
            'comparable_seeds': [e['seed'] for e in comparable],
            'incomparable_seeds': [e['seed'] for e in pairs
                                   if not e['comparable']],
            'comparable_pair_count': len(comparable),
            'sufficient': len(comparable) >= MINIMUM_COMPARABLE_PAIRS,
            'gate_tolerances': gate.get('tolerances'),
        }

    outcomes = sanity.get('outcomes', {})
    comparator = sanity.get('comparator_arm', 'n0r_provenance_off')
    seeds = set()
    for name in COMPARABILITY_CLASSES:
        for arm, values in (outcomes.get(name) or {}).items():
            if arm != comparator:
                seeds.update(values.keys())
    if not seeds:
        # The payload carries no pre-probe information at all: comparability
        # cannot be assessed, so it may not be used to block a verdict.
        return {
            'source': 'not_evaluable',
            'classes': list(COMPARABILITY_CLASSES),
            'minimum_comparable_pairs': MINIMUM_COMPARABLE_PAIRS,
            'pairs': [],
            'comparable_seeds': [],
            'incomparable_seeds': [],
            'comparable_pair_count': None,
            'sufficient': True,
            'note': 'payload has no pre-probe outcome classes',
        }

    pairs = []
    for seed in sorted(seeds):
        entry = {'seed': seed, 'arms': {}, 'comparable': True, 'differences': {}}
        for name in COMPARABILITY_CLASSES:
            by_arm = outcomes.get(name) or {}
            for arm, values in sorted(by_arm.items()):
                if seed in values:
                    entry['arms'].setdefault(arm, {})[name] = values[seed]
            if comparator in (by_arm or {}) and seed in by_arm[comparator]:
                partners = [a for a in by_arm if a != comparator and seed in by_arm[a]]
                reference = by_arm[comparator][seed]
                for arm in partners:
                    difference = by_arm[arm][seed] - reference
                    entry['differences'].setdefault(arm, {})[name] = difference
                    if difference != 0:
                        entry['comparable'] = False
        pairs.append(entry)
    comparable = [e for e in pairs if e['comparable']]
    return {
        'source': 'recomputed_exact_equality',
        'classes': list(COMPARABILITY_CLASSES),
        'minimum_comparable_pairs': MINIMUM_COMPARABLE_PAIRS,
        'pairs': pairs,
        'comparable_seeds': [e['seed'] for e in comparable],
        'incomparable_seeds': [e['seed'] for e in pairs if not e['comparable']],
        'comparable_pair_count': len(comparable),
        'sufficient': len(comparable) >= MINIMUM_COMPARABLE_PAIRS,
    }


def online_sanity_stop_rule(sanity, reference_repeatability=None):
    """Evaluate the pre-registered online stop rule.

    A shift class fails the sanity check when every paired seed difference is
    non-zero with the same sign AND the mean difference exceeds both the
    numerical tolerance and the reference repeatability measured in the earlier
    N0 block.
    """
    outcomes = sanity.get('outcomes', {})
    comparator = sanity.get('comparator_arm', 'n0r_provenance_off')
    repeatability = (reference_repeatability or {}).get('repeatability', {})
    comparability = sanity.get('comparability') or pair_comparability(sanity)
    # Seed keys are strings in one payload and integers in another; compare
    # them in a single normalised form.
    comparable = {str(seed) for seed in comparability['comparable_seeds']}
    entries = []
    triggered = []
    for name, numerical_tolerance in SHIFT_CLASSES:
        by_arm = outcomes.get(name)
        if not by_arm:
            continue
        reference_values = by_arm.get(comparator) or {}
        for arm, seed_values in sorted(by_arm.items()):
            if arm == comparator:
                continue
            raw = sanity.get('nonperturbation', {}).get(
                'per_outcome', {}).get(name, {}).get(arm, {}).get('statistics')
            # A pair may only accuse the instrument when both of its arms
            # entered the probe from the same pre-probe graph.
            differences = []
            pairing_available = bool(reference_values)
            reference_by_seed = {str(seed): value
                                 for seed, value in reference_values.items()}
            for seed in sorted(seed_values, key=str):
                if comparable and str(seed) not in comparable:
                    continue
                if str(seed) in reference_by_seed:
                    differences.append(seed_values[seed]
                                       - reference_by_seed[str(seed)])
            if not pairing_available and raw:
                differences = [value for value in raw['differences']
                               if value is not None]
            reference = repeatability.get(name, {}).get('mad') or 0.0
            threshold = max(numerical_tolerance, reference)
            if differences:
                mean_difference = sum(differences) / len(differences)
                same_sign_nonzero = (all(d > 0 for d in differences)
                                     or all(d < 0 for d in differences))
            else:
                mean_difference = None
                same_sign_nonzero = False
            magnitude = (abs(mean_difference)
                         if mean_difference is not None else None)
            entry = {
                'outcome': name,
                'arm': arm,
                'paired_differences': differences,
                'raw_paired_differences_all_seeds': (
                    raw or {}).get('differences'),
                'excluded_incomparable_seeds': [
                    str(seed) for seed in sorted(seed_values)
                    if comparable and str(seed) not in comparable],
                'mean_difference': mean_difference,
                'raw_mean_difference': (raw or {}).get('mean_difference'),
                'same_sign_nonzero': same_sign_nonzero,
                'reference_repeatability_mad': reference,
                'numerical_tolerance': numerical_tolerance,
                'threshold': threshold,
                'exceeds_repeatability': bool(magnitude is not None
                                              and magnitude > threshold),
            }
            entry['triggers_stop_rule'] = bool(
                entry['same_sign_nonzero'] and entry['exceeds_repeatability']
                and comparability['sufficient'])
            entry['n_comparable_pairs'] = len(differences)
            entries.append(entry)
            if entry['triggers_stop_rule']:
                triggered.append(entry)
    return {
        'comparator_arm': comparator,
        'comparability': comparability,
        'entries': entries,
        'triggered': triggered,
        'state': STATE_REPAIR_FAILED if triggered else 'ONLINE_SANITY_PASSED',
    }


def certify(sanity, replay, reference_repeatability=None):
    online = online_sanity_stop_rule(sanity, reference_repeatability)
    replay_verdict = (replay or {}).get('verdict', {}).get('verdict')
    # Transparency: the same stop rule evaluated *without* the comparability
    # filter, i.e. the reading that would treat unmatched pairs as evidence.
    # It is recorded even when it disagrees, so a reader can see both.
    unfiltered_sanity = dict(sanity)
    unfiltered_sanity['comparability'] = {
        'source': 'filter_disabled', 'sufficient': True, 'comparable_seeds': [],
        'minimum_comparable_pairs': MINIMUM_COMPARABLE_PAIRS,
        'comparable_pair_count': None, 'pairs': [], 'incomparable_seeds': [],
        'classes': list(COMPARABILITY_CLASSES),
    }
    payload = {
        'online_sanity': online,
        'online_sanity_unfiltered': online_sanity_stop_rule(
            unfiltered_sanity, reference_repeatability),
        'replay_verdict': replay_verdict,
        'online_sanity_source': sanity.get('suite_dir'),
    }
    # The online block may only be used when its pairs are matched.  With too
    # few comparable pairs it can neither accuse nor exonerate the instrument,
    # so the decision falls to the same-input replay, which the pre-registration
    # designates as the decisive instrument-neutrality evidence.
    online_usable = online['comparability']['sufficient']
    payload['online_sanity_usable'] = online_usable
    if not online_usable:
        payload['online_sanity_unusable_reason'] = (
            'only {} seed pair(s) entered the probe from the same pre-probe '
            'graph (minimum {}), so a paired difference cannot be attributed '
            'to the instrument'.format(
                online['comparability']['comparable_pair_count'],
                online['comparability']['minimum_comparable_pairs']))
    if online_usable and online['state'] == STATE_REPAIR_FAILED:
        payload.update({
            'outcome': STATE_REPAIR_FAILED,
            'reason': ('the repaired instrumentation still shows a '
                       'same-direction shift in the matched online sanity block'),
            'next_required_action': [
                'inspect and further repair the instrumentation; do not run the '
                'same-input replay or N1 yet',
            ],
        })
        return payload
    if replay_verdict is None:
        if not online_usable:
            payload.update({
                'outcome': STATE_INCONCLUSIVE,
                'reason': ('the online sanity block is unusable and the '
                           'same-input replay has not been evaluated, so there '
                           'is no evidence either way'),
            })
            return payload
        payload.update({
            'outcome': 'PENDING_SAME_INPUT_REPLAY',
            'reason': ('the online sanity block passed; the same-input replay '
                       'has not been evaluated yet and is required for '
                       'certification'),
        })
        return payload
    if replay_verdict == 'REPLAY_NEUTRALITY_CERTIFIED':
        failures = (replay or {}).get('verdict', {}).get('failures') or []
        payload.update({
            'outcome': STATE_CERTIFIED,
            'reason': ('identical input produces an identical graph with the '
                       'instrument off and on, within the pre-registered '
                       'numerical floor and the measured replay repeatability'),
            'online_sanity_role': (
                'screen for an obvious post-repair shift; it is decisive only '
                'when at least {} matched pairs exist, otherwise the replay '
                'decides'.format(
                    online['comparability']['minimum_comparable_pairs'])),
            'replay_failures': failures,
        })
        return payload
    payload.update({
        'outcome': STATE_NOT_NEUTRAL,
        'reason': ('identical input produces a different Karto graph when the '
                   'instrument is enabled'),
        'replay_failures': (replay or {}).get('verdict', {}).get('failures'),
        'next_required_action': [
            'the instrument changes constraint generation; do not run N1',
        ],
    })
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sanity', required=True,
                        help='n0_nonperturbation_decision.json of the N0-R suite')
    parser.add_argument('--reference-repeatability',
                        help='n0_nonperturbation_decision.json of the earlier '
                             'N0 block, used as the measured reference scale')
    parser.add_argument('--replay', help='replay_comparison.json')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    sanity = json.load(open(args.sanity))
    reference = json.load(open(args.reference_repeatability)) \
        if args.reference_repeatability else None
    replay = json.load(open(args.replay)) if args.replay else None
    payload = certify(sanity, replay, reference)
    with open(args.out, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    print(json.dumps({'outcome': payload['outcome'],
                      'reason': payload['reason']}, indent=2))


if __name__ == '__main__':
    main()
