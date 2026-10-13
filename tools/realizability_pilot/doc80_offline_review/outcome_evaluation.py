#!/usr/bin/python3
"""Doc-80 section 7.6-7.7: outcome join, counterfactual boundary, hypotheses.

Outcome side: this module is the ONLY place that reads post-action labels.  It
joins the frozen pre-action features with observed action gains and writes the
competing-hypothesis evidence table.  It never feeds anything back into
feature construction (the modules are imported in opposite directions).
"""

import json
import statistics
from pathlib import Path

from . import common

HYPOTHESES = [
    {
        'id': 'H1',
        'statement': 'Direction-dependent historical visibility controls the action gain.',
        'observed': ('Exclusive swept-sector counts are tiny (0-7 of 108-114 history '
                     'nodes) and do not separate observed directions in 7/7 runs.'),
        'status': 'HYPOTHESIS_ONLY: no pre-action separation in the collected geometry',
        'counterexample': 'D79_B_Lplus_2 (L+ executed) has larger L- visible count '
                          '(98 vs 101) yet the largest observed gain.',
        'confound': 'Node-level visibility is a geometric proxy, not the Karto '
                    'matchability of scan structure.',
        'minimal_test': 'Same initial state, execute both directions, compare realised '
                        'historic links (requires a counterfactual run pair and is '
                        'outside this offline review).',
    },
    {
        'id': 'H2',
        'statement': 'The pre-action graph state (arrival graph) explains the gain.',
        'observed': ('Arrival graphs differ modestly across runs (nodes 108-114, '
                     'non-chain edges 8-21, J_T 7.53-9.11); gains do not order with '
                     'any single arrival statistic (see outcome join).'),
        'status': 'DIAGNOSTIC: partial covariate, not identified',
        'counterexample': 'D79_B_Lminus_1 J=8.06 gain 0.0225 vs D79_C_Lplus_1 J=8.22 '
                          'gain 0.1244 -- close J yet very different gains.',
        'confound': 'Graph statistics co-vary with place, seed and route leg; n=2 per '
                    'cell forbids partialling them apart.',
        'minimal_test': 'Matched-state counterfactual pairs at one place.',
    },
    {
        'id': 'H3',
        'statement': 'A fixed directional advantage (L+) explains the results.',
        'observed': ('All observed per-pair L+ - L- differences are positive '
                     '(B: 0.261-0.339; C: 0.104-0.122); no place shows the opposite '
                     'sign, so a constant L+ policy is not excluded.'),
        'status': 'OBSERVED (within the sampled protocol): cannot be excluded',
        'counterexample': 'None in the seven runs.',
        'confound': 'Seeds differ between L+ and L- runs at the same place '
                    '(B 44016 vs 44013; C 44025 vs 44026), so pairing is not a '
                    'same-state control.',
        'minimal_test': 'Repeat both directions at a new place with identical seeds; '
                        'if L+ wins everywhere, the selection problem collapses to a '
                        'constant policy.',
    },
    {
        'id': 'H4',
        'statement': 'Historic links raise graph information but yield no measurable '
                     'localisation benefit in this task.',
        'observed': ('Corrected target map error changes by <= 0.005 m mean '
                     '(<= 0.014 m node displacement) across stages; robot boundary '
                     'localisation change is mixed sign (-0.008 .. +0.063 m); no '
                     'consistent improvement.'),
        'status': 'OBSERVED: information gain did not translate into localisation gains',
        'counterexample': 'D79_B_Lminus_2 localisation error worsened by +0.063 m '
                          'despite a small positive information gain.',
        'confound': 'Localisation error at these scales is comparable to the TF-lag '
                    'noise floor (~2-5 cm) of the measurement chain itself.',
        'minimal_test': 'Longer horizon: track target-map error over many future '
                        'revisits with the same synchronous instrumentation.',
    },
]


def outcome_join(doc80_root=common.DOC80, doc79_root=common.DOC79):
    import csv
    metrics = {}
    with open(Path(doc79_root) / 'analysis' / 'per_episode_metrics.csv') as handle:
        for row in csv.DictReader(handle):
            if row['technical_validity'] == 'MEASUREMENT_VALIDATED':
                metrics[(row['episode_id'], row['attempt'])] = row
    features = []
    with open(Path(doc80_root) / 'analysis' /
              'directional_visibility_features.csv') as handle:
        for row in csv.DictReader(handle):
            features.append(row)
    contributions = {}
    contributions_path = Path(doc80_root) / 'analysis' / 'factor_group_contributions.csv'
    if contributions_path.is_file():
        with open(contributions_path) as handle:
            for row in csv.DictReader(handle):
                contributions[(row['episode_id'], row['attempt'])] = row
    class_counts = {}
    classes_path = Path(doc80_root) / 'analysis' / 'historical_link_classes.csv'
    if classes_path.is_file():
        with open(classes_path) as handle:
            for row in csv.DictReader(handle):
                if row['is_chain'] == 'True':
                    continue
                key = (row['episode_id'], row['attempt'])
                counts = class_counts.setdefault(key, {'A': 0, 'B': 0, 'C': 0})
                counts[row['edge_class'][0]] += 1

    joined = []
    for feature in features:
        key = (feature['episode_id'], feature['attempt'])
        metric = metrics.get(key, {})
        contrib = contributions.get(key, {})
        counts = class_counts.get(key, {})
        joined.append({
            'episode_id': feature['episode_id'], 'attempt': feature['attempt'],
            'place': feature['place'], 'action': feature['action'],
            'seed': feature['seed'],
            'visible_delta_frac': feature['directional_visibility_delta_frac'],
            'novelty_delta': feature['novelty_proxy_delta'],
            'exclusive_Lplus': feature['history_exclusive_Lplus'],
            'exclusive_Lminus': feature['history_exclusive_Lminus'],
            'delta_J_action_sync': metric.get('delta_J_action_sync'),
            'historic_links_action': None,
            'class_A_edges': counts.get('A'), 'class_B_edges': counts.get('B'),
            'class_C_edges': counts.get('C'),
            'contribution_class_A': contrib.get('contribution_class_A'),
            'contribution_class_B': contrib.get('contribution_class_B'),
            'contribution_class_C': contrib.get('contribution_class_C'),
            'actual_rotation_rad': metric.get('actual_rotation_rad'),
            'action_path_m': metric.get('action_path_m'),
        })
    common.write_csv(Path(doc80_root) / 'analysis' / 'feature_outcome_join.csv',
                     joined)
    surviving = [row for row in joined if row['delta_J_action_sync']]
    directions = {'L+': [], 'L-': []}
    for row in surviving:
        value = float(row['delta_J_action_sync'])
        directions[row['action']].append(value)
    stats = {}
    for action, values in directions.items():
        if values:
            stats[action] = {'n': len(values),
                             'mean': statistics.mean(values),
                             'min': min(values), 'max': max(values)}
    return {'joined': joined, 'stats': stats}


def hypotheses_rows():
    return [{'id': item['id'], 'statement': item['statement'],
             'evidence': item['observed'], 'status': item['status'],
             'counterexample': item['counterexample'],
             'confound': item['confound'],
             'minimal_test': item['minimal_test']} for item in HYPOTHESES]


def run(doc80_root=common.DOC80):
    join = outcome_join(doc80_root)
    rows = hypotheses_rows()
    common.write_csv(Path(doc80_root) / 'analysis' /
                     'directional_competing_hypotheses.csv', rows)
    return {'join': join, 'hypotheses': rows}


if __name__ == '__main__':
    out = run()
    print(json.dumps(out['join']['stats'], indent=1))
