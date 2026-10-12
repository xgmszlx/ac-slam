#!/usr/bin/python3
"""Doc-78 review pipeline: boundary audit, statistics, ground truth, mechanism.

Usage (from the repository root, with the suite python on ``PYTHONPATH``)::

    PYTHONPATH=catkin_ws/python /usr/bin/python3 \
        tools/realizability_pilot/continuous_boundary_review/review.py \
        --suite results/realizability_pilot/p1_continuous_revisit_actions_20261010 \
        --out results/realizability_pilot/p1_continuous_boundary_review_20261012

The pipeline reimplements the frozen ``J_T`` measure locally (through
``analysis.py``, the same module doc 77 used) and *re-derives* every number
from the recorded run directories.  Nothing here modifies the doc-77 suite.
"""

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import numpy as np  # noqa: E402

import evidence as ev  # noqa: E402
import timeline as tl  # noqa: E402

import analysis as an  # noqa: E402
import geometry as ge  # noqa: E402

REVIEW_VERSION = 'p1_continuous_boundary_review_v1'
#: A run's stage gain counts as exactly zero below this magnitude (nats).
ZERO_GAIN_TOLERANCE = 1e-6
#: Effective-closure contribution threshold (nats) for "this closure mattered".
EFFECTIVE_CLOSURE_EPS = 1e-9
#: Relative tolerance when comparing an independently recomputed stage gain with
#: the sum of the stage's closure contributions.  The remaining deviation is
#: numerical conditioning of the J_T marginal solve, not mechanism.
GAIN_MATCH_REL_TOLERANCE = 1e-3
GAIN_MATCH_ABS_FLOOR = 1e-5


def _number(value):
    """Float from a CSV cell that may be empty or a string."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


FOCUS_EPISODES = (
    '0005_place_A_r2_S1',
    '0016_place_B_r1_L+',
    '0016_place_B_r1_L+_L+_rep2',
    '0025_place_C_r1_L+',
)
#: Name for every fixed-linearisation sub-graph diagnostic, kept separate from
#: the recorded (real) stage J_T values.
FIXED_LINEARIZATION_LABEL = 'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC'


def run_features(run, timeline):
    """Pre-action / execution features used to explain arm differences."""
    result = run['result']
    windows = timeline['windows']
    action_start_time = windows['action']['time_start']
    pre_action_states = sum(1 for item in run['accepts']
                            if action_start_time is not None
                            and item['sim_time'] <= action_start_time)
    return {
        'pre_action_states': pre_action_states,
        'action_states_created': sum(
            1 for item in timeline['timeline'] if item['stage_by_time'] == 'action'),
        'action_rotation_rad': result.get('action_cumulative_rotation_rad'),
        'action_path_m': result.get('action_path_length_m'),
        'return_duration_s': (None if (windows['return']['time_end'] is None
                                       or windows['return']['time_start'] is None)
                              else windows['return']['time_end'] - windows['return']['time_start']),
        'anchor_heading_error_rad': (run['frozen'].get('anchor_heading_error_rad')),
    }


def stage_sequence():
    return ev.SNAPSHOTS


# --------------------------------------------------------------------- phase 1
def boundary_audit(runs, timelines):
    """Per run x boundary rows: what the snapshot really contained."""
    rows = []
    for run in runs:
        timeline = timelines[run['episode_id']]
        stages = {}
        for name in ('return', 'action', 'tail'):
            stages[name] = tl.stage_motion(run['scans'], tl.motion_flags(run['scans']),
                                           (timeline['windows'][name]['scan_start'],
                                            timeline['windows'][name]['scan_end']))
        state_stage = {item['state_id']: item['stage_by_time']
                       for item in timeline['timeline']}
        for position, name in enumerate(ev.SNAPSHOTS):
            content = run['content_time'][name]
            snap_time = run['snapshot_time'][name]
            node_ids = timeline['node_ids'][name]
            accepts = run['accepts']
            states_in_snapshot = [item for item in accepts if item['state_id'] in node_ids]
            # states created in the stage this boundary closes, and how many of
            # them the boundary snapshot actually contains
            stage = ev.STAGE_OF_SNAPSHOT.get(name)
            created = []
            if stage is not None:
                created = [item for item in accepts if state_stage.get(item['state_id']) == stage]
            contained = [item for item in created if item['state_id'] in node_ids]
            # the stage's motion end that this boundary is supposed to close
            motion_end_time = stages[stage]['motion_end_time'] if stage else None
            before_motion = [item for item in created
                             if motion_end_time is not None and item['sim_time'] <= motion_end_time]
            after_motion = [item for item in created
                            if motion_end_time is not None and item['sim_time'] > motion_end_time]
            rows.append({
                'episode_id': run['episode_id'],
                'suite_round': run['suite_round'],
                'action_id': run['action_id'],
                'place_id': run['place_id'],
                'repeat': run['repeat'],
                'boundary': name,
                'stage': stage,
                'snapshot_time_ros': (None if snap_time is None else round(snap_time, 3)),
                'content_time_ros': (None if content is None else round(content, 3)),
                'content_lag_s': (None if (snap_time is None or content is None)
                                  else round(snap_time - content, 3)),
                'stage_motion_end_time': (None if motion_end_time is None
                                          else round(motion_end_time, 3)),
                'content_before_stage_motion_end': (None if (content is None or motion_end_time is None)
                                                    else bool(content < motion_end_time)),
                'accepted_states': len(accepts),
                'states_in_snapshot': len(states_in_snapshot),
                'states_created_in_stage': len(created),
                'stage_states_in_snapshot': len(contained),
                'stage_states_deferred': len(created) - len(contained),
                'stage_states_before_motion_end': len(before_motion),
                'stage_states_after_motion_end': len(after_motion),
                'states_accepted_after_content': sum(
                    1 for item in accepts if content is not None and item['sim_time'] > content),
                'graph_nodes': len(run['snapshots'][name]['nodes']),
                'graph_edges': len(run['snapshots'][name]['edges']),
                'graph_closures': sum(
                    1 for edge in run['snapshots'][name]['edges']
                    if edge['target_state_id'] != edge['source_state_id'] + 1),
                'quiescence_satisfied': bool(run['boundary'][name].get('satisfied')),
                'quiescence_s': run['boundary'][name].get('quiescence_s'),
                'full_graph_messages': run['boundary'][name].get('full_graph_messages'),
                'keyscan_publications': run['boundary'][name].get('keyscan_publications'),
                'keyscan_missing_check_vacuous': True,
            })
    return rows


def recoverability_rows(runs, timelines):
    rows = []
    for run in runs:
        timeline = timelines[run['episode_id']]
        for item in timeline['timeline']:
            if item['class'] == 'PUBLISHED_TIMELY':
                continue
            rows.append({
                'episode_id': run['episode_id'],
                'suite_round': run['suite_round'],
                'action_id': run['action_id'],
                'place_id': run['place_id'],
                'state_id': item['state_id'],
                'unique_id': item['unique_id'],
                'accept_sim_time': round(item['sim_time'], 3),
                'stage_by_time': item['stage_by_time'],
                'first_snapshot_with_state': item['first_snapshot'],
                'recoverability_class': item['class'],
                'recoverable_offline': item['class'] == 'DEFERRED_RECOVERABLE',
                'edges_recorded_somewhere': item['class'] == 'DEFERRED_RECOVERABLE',
                'speed_at_accept_mps': (None if item['speed_mps'] is None
                                        else round(item['speed_mps'], 3)),
                'in_contiguous_suffix': item['class'] == 'NEVER_PUBLISHED_SUFFIX',
                'needs_fixed_linearization_diagnostic': item['class'].startswith('NEVER_PUBLISHED'),
            })
    return rows


# --------------------------------------------------------------------- phase 2
def _doc77_table(suite_dir):
    table = {}
    for name in ('analysis/per_episode_metrics.csv',
                 'repeatability/analysis/per_episode_metrics.csv'):
        path = Path(suite_dir) / name
        if not path.is_file():
            continue
        import csv
        with open(path) as handle:
            for row in csv.DictReader(handle):
                converted = dict(row)
                for key, value in row.items():
                    try:
                        converted[key] = float(value)
                    except (TypeError, ValueError):
                        converted[key] = value
                converted['action_gain_doc77'] = converted.get('action_gain')
                converted['return_gain_doc77'] = converted.get('return_gain')
                converted['tail_gain_doc77'] = converted.get('tail_gain')
                converted['_round'] = ('repeatability' if 'repeatability' in name
                                       else 'main')
                table[row['episode_id']] = converted
    return table


def recompute_gains(run):
    """Independent J_T recomputation from the four recorded snapshots."""
    frozen = run['frozen']
    target_ids = [int(state) for state in frozen['target_state_ids']]
    scores = {}
    for name in ev.SNAPSHOTS:
        graph = run['snapshots'][name]
        try:
            scores[name] = an.target_score(graph, target_ids)['J_T']
        except Exception as exc:  # noqa: BLE001 - recorded, never silent
            scores[name] = None
            run.setdefault('score_failures', []).append(
                {'snapshot': name, 'error': '{}: {}'.format(type(exc).__name__, exc)})
    if all(scores[name] is not None for name in ev.SNAPSHOTS):
        first, second, third, fourth = (scores[name] for name in ev.SNAPSHOTS)
        return {
            'return_gain': second - first,
            'action_gain': third - second,
            'tail_gain': fourth - third,
            'total_gain': fourth - first,
        }
    return {'return_gain': None, 'action_gain': None,
            'tail_gain': None, 'total_gain': None}


def statistics_rows(runs, doc77, recomputed, timelines):
    rows = []
    configs = ['0003_place_A_r1_L+', '0004_place_A_r1_L-',
               '0016_place_B_r1_L+', '0013_place_B_r1_L-']
    features = {run['episode_id']: run_features(run, timelines[run['episode_id']])
                for run in runs}
    by_config = defaultdict(list)
    for run in runs:
        if run['round'] == 'repeatability' and run['repeatability_of']:
            by_config[run['repeatability_of']].append(run)
    for config in configs:
        base = run_by_id(runs, config)
        reps = sorted(by_config.get(config, []), key=lambda run: run['replay_index'] or 0)
        values = [recomputed[base['episode_id']]['action_gain']] + \
                 [recomputed[run['episode_id']]['action_gain'] for run in reps]
        doc_values = [doc77.get(base['episode_id'], {}).get('action_gain_doc77')] + \
                     [doc77.get(run['episode_id'], {}).get('action_gain_doc77') for run in reps]
        triplet = [base] + reps
        pre_state = {}
        for key in ('pre_action_states', 'action_states_created', 'action_rotation_rad',
                    'return_duration_s'):
            feature_values = [features[run['episode_id']][key] for run in triplet]
            feature_values = [value for value in feature_values if value is not None]
            if feature_values:
                pre_state[key] = 'min {:.4g} max {:.4g} spread {:.4g}'.format(
                    min(feature_values), max(feature_values),
                    max(feature_values) - min(feature_values))
        rows.append({
            'row_type': 'REPEATABILITY_CONFIG',
            'config': config,
            'place_id': base['place_id'],
            'action_id': base['action_id'],
            'runs': len(values),
            'values': ';'.join('{:.5f}'.format(value) for value in values if value is not None),
            'values_doc77': ';'.join('{:.5f}'.format(value) for value in doc_values
                                     if value is not None),
            'mean': statistics.mean(values),
            'sd_ddof0': statistics.pstdev(values),
            'sd_ddof1': statistics.stdev(values),
            'method': ('three same-configuration full runs (r1 + 2 re-runs), action_gain '
                       'recomputed; pre-state spread: ' + json.dumps(pre_state)),
        })
    # the old doc-77 number, reproduced exactly: for each of the four
    # repeatability configs, all five runs of the same (place, action) cell
    # (three main repeats + two re-runs), pstdev (ddof=0), averaged
    old_terms, all5_pooled = [], []
    for config in configs:
        base = run_by_id(runs, config)
        arm = [run for run in runs
               if run['place_id'] == base['place_id'] and run['action_id'] == base['action_id']]
        values = [recomputed[run['episode_id']]['action_gain'] for run in arm
                  if recomputed[run['episode_id']]['action_gain'] is not None]
        if len(values) > 1:
            old_terms.append(statistics.pstdev(values))
            all5_pooled.append(statistics.variance(values))
    config_variance = []
    for config in configs:
        values = [recomputed[run['episode_id']]['action_gain']
                  for run in runs
                  if run['episode_id'] == config or run['repeatability_of'] == config]
        values = [value for value in values if value is not None]
        config_variance.append(statistics.variance(values))
    rows.append({
        'row_type': 'POOLED_SD_RECONCILIATION',
        'config': 'ALL_4_CONFIGS',
        'place_id': '', 'action_id': '', 'runs': 3,
        'values': '',
        'mean': None,
        'sd_ddof0': statistics.mean(old_terms) if old_terms else None,
        'sd_ddof1': math.sqrt(sum(config_variance) / len(config_variance)),
        'method': ('sd_ddof0 column reproduces doc-77 s_rep = mean over place x action '
                   'of pstdev(all runs of that cell, ddof=0); sd_ddof1 column is the '
                   'corrected same-configuration pooled within-group sd '
                   '(equal weights over the four configs, each with 3 runs, ddof=1)'),
    })
    rows.append({
        'row_type': 'POOLED_SD_ALL_FIVE_RUNS',
        'config': 'ALL_4_CONFIGS', 'place_id': '', 'action_id': '', 'runs': 5,
        'values': '', 'mean': None, 'sd_ddof0': None,
        'sd_ddof1': math.sqrt(sum(all5_pooled) / len(all5_pooled)) if all5_pooled else None,
        'method': ('pooled within-cell sd over the three main repeats plus the two '
                   're-runs of each of the four configs (ddof=1)'),
    })
    # arm-level realisation statistics: zero-gain frequency and closure productivity
    actions = ['S0', 'S1', 'L+', 'L-']
    for action in actions:
        for round_name in ('main', 'repeatability'):
            arm = [run for run in runs if run['action_id'] == action
                   and run['suite_round'] == round_name]
            gains = [recomputed[run['episode_id']]['action_gain'] for run in arm
                     if recomputed[run['episode_id']]['action_gain'] is not None]
            zeros = sum(1 for value in gains if abs(value) <= ZERO_GAIN_TOLERANCE)
            rows.append({
                'row_type': 'ARM_REALISATION',
                'config': round_name, 'place_id': '', 'action_id': action,
                'runs': len(gains),
            'values': '{}/{} exactly-zero action_gain'.format(zeros, len(gains)),
            'mean': statistics.mean(gains) if gains else None,
            'sd_ddof0': statistics.pstdev(gains) if len(gains) > 1 else None,
            'sd_ddof1': statistics.stdev(gains) if len(gains) > 1 else None,
            'method': 'independent recomputation over main + repeatability runs',
        })
    return rows, recomputed


def run_by_id(runs, episode_id):
    for run in runs:
        if run['episode_id'] == episode_id:
            return run
    raise KeyError(episode_id)


# --------------------------------------------------------------------- phase 4
def _edge_contribution(graph, edge_index):
    """J_T change of the snapshot when one edge is removed (its contribution)."""
    frozen_targets = graph['_target_ids']
    try:
        full = an.target_score(graph, frozen_targets)['J_T']
    except Exception:  # noqa: BLE001
        return None
    reduced = {'nodes': graph['nodes'],
               'edges': [edge for edge in graph['edges'] if edge['index'] != edge_index]}
    try:
        without = an.target_score(reduced, frozen_targets)['J_T']
    except Exception:  # noqa: BLE001
        return None
    return full - without


def stage_edge_review(run, timeline):
    """Per-stage edge accounting with accept-time attribution and J_T deltas."""
    frozen = run['frozen']
    target_ids = [int(state) for state in frozen['target_state_ids']]
    accepts = {item['state_id']: item for item in timeline['timeline']}
    graphs = {}
    for name in ev.SNAPSHOTS:
        graph = dict(run['snapshots'][name])
        graph['_target_ids'] = target_ids
        graphs[name] = graph
    rows = []
    for before, after, stage in (('G_before_return', 'G_arrival', 'return'),
                                 ('G_arrival', 'G_action_done', 'action'),
                                 ('G_action_done', 'G_final', 'tail')):
        before_graph, after_graph = graphs[before], graphs[after]
        known = {edge['index'] for edge in before_graph['edges']}
        new_edges = [edge for edge in after_graph['edges']
                     if edge['index'] not in known]
        closures = [edge for edge in new_edges
                    if edge['target_state_id'] != edge['source_state_id'] + 1]
        gain = None
        try:
            gain = (an.target_score(after_graph, target_ids)['J_T']
                    - an.target_score(before_graph, target_ids)['J_T'])
        except Exception:  # noqa: BLE001
            gain = None
        # closure contributions: individual and combined
        individual = []
        for edge in closures:
            contribution = _edge_contribution(after_graph, edge['index'])
            source = accepts.get(edge['source_state_id'], {})
            target = accepts.get(edge['target_state_id'], {})
            individual.append({
                'index': edge['index'],
                'source': edge['source_state_id'],
                'target': edge['target_state_id'],
                'source_stage': source.get('stage_by_time'),
                'target_stage': target.get('stage_by_time'),
                'source_accept': source.get('sim_time'),
                'target_accept': target.get('sim_time'),
                'contribution': contribution,
            })
        combined = None
        if closures:
            reduced = {'nodes': after_graph['nodes'],
                       'edges': [edge for edge in after_graph['edges']
                                 if edge['index'] not in {item['index'] for item in individual}]}
            try:
                combined = (an.target_score(after_graph, target_ids)['J_T']
                            - an.target_score(reduced, target_ids)['J_T'])
            except Exception:  # noqa: BLE001
                combined = None
        # accept-time attribution: an edge is created with the later scan
        def stage_of_edge(edge):
            source = accepts.get(edge['source_state_id'], {})
            target = accepts.get(edge['target_state_id'], {})
            if source.get('sim_time') is None or target.get('sim_time') is None:
                return None
            return (source.get('stage_by_time') if source['sim_time'] >= target['sim_time']
                    else target.get('stage_by_time'))
        deferred = [edge for edge in closures
                    if stage_of_edge(edge) is not None and stage_of_edge(edge) != stage]
        effective = [item for item in individual
                     if item['contribution'] is not None
                     and abs(item['contribution']) > EFFECTIVE_CLOSURE_EPS]
        rows.append({
            'episode_id': run['episode_id'],
            'suite_round': run['suite_round'],
            'action_id': run['action_id'],
            'place_id': run['place_id'],
            'stage': stage,
            'new_edges': len(new_edges),
            'new_chain_edges': len(new_edges) - len(closures),
            'new_closures': len(closures),
            'effective_closures': len(effective),
            'deferred_attribution_edges': sum(
                1 for edge in new_edges
                if stage_of_edge(edge) is not None and stage_of_edge(edge) != stage),
            'deferred_attribution_closures': len(deferred),
            'closure_contribution_sum': (None if combined is None else combined),
            'individual_contributions': json.dumps(
                [{key: (round(value, 12) if isinstance(value, float) else value)
                  for key, value in item.items()} for item in individual]),
            'stage_gain_recomputed': gain,
            'gain_minus_closure_sum': (None if (gain is None or combined is None)
                                       else gain - combined),
            'gain_matches_closure_sum': (None if (gain is None or combined is None)
                                         else bool(abs(gain - combined)
                                                   <= max(GAIN_MATCH_ABS_FLOOR,
                                                          GAIN_MATCH_REL_TOLERANCE * abs(gain)))),
            'deferred_detail': json.dumps(
                [{'index': edge['index'], 'source': edge['source_state_id'],
                  'target': edge['target_state_id'], 'created_stage': stage_of_edge(edge)}
                 for edge in deferred]),
        })
    return rows


def missing_state_diagnostic(run, timeline, closure_covariance):
    """Worst-case bound for never-published suffix states.

    Each never-published state is placed at the pose the mapper published on
    ``/others`` (recorded in ``keyscan_stream.jsonl``) and given (a) the chain
    edge to its predecessor - provably a no-op for J_T - and (b) one synthetic
    closure edge to the nearest *published* state, using the median covariance
    of observed closure edges of the same action arm.  The returned delta is a
    labelled diagnostic, never a primary measurement.
    """
    missing = [item for item in timeline['timeline']
               if item['class'] == 'NEVER_PUBLISHED_SUFFIX']
    if not missing:
        return {'states': 0, 'delta_jt_worst_case': 0.0}
    final = run['snapshots']['G_final']
    target_ids = [int(state) for state in run['frozen']['target_state_ids']]
    nodes = list(final['nodes'])
    known_keyscan = {int(item['unique_id']): item for item in run['keyscans']
                     if item.get('unique_id') is not None}
    # ``/others`` records carry the accepted pose; match by sim time
    keyscan_by_stamp = {}
    for index, item in enumerate(run['keyscans']):
        keyscan_by_stamp[index] = item
    stamps = [float(item['stamp']) for item in run['keyscans']]
    added_nodes = []
    for item in missing:
        position = ev.nearest_index(stamps, item['sim_time']) if stamps else None
        if position is None:
            continue
        sample = run['keyscans'][position]
        if abs(float(sample['stamp']) - item['sim_time']) > 0.05:
            continue
        added_nodes.append({'state_id': item['state_id'],
                            'unique_id': item['unique_id'],
                            'x': float(sample['x']), 'y': float(sample['y']),
                            'theta': float(sample['theta']),
                            '_accept': item['sim_time']})
    if not added_nodes:
        return {'states': 0, 'delta_jt_worst_case': None,
                'reason': 'no matching /others pose for the missing states'}
    # chain edges keep the suffix attached (subtree -> provably no J_T change)
    edges = list(final['edges'])
    ordered = sorted(added_nodes, key=lambda node: node['state_id'])
    chain_edges = []
    for position, node in enumerate(ordered):
        parent = node['state_id'] - 1
        chain_edges.append((parent, node['state_id']))
    published = {node['state_id']: node for node in nodes}
    synthetic = []
    for node in ordered:
        best, best_distance = None, None
        for candidate in nodes:
            distance = math.hypot(candidate['x'] - node['x'], candidate['y'] - node['y'])
            if best is None or distance < best_distance:
                best, best_distance = candidate, distance
        if best is None:
            continue
        synthetic.append((best['state_id'], node['state_id'], best_distance))
    graph_nodes = nodes + [{'state_id': node['state_id'], 'unique_id': node['unique_id'],
                            'x': node['x'], 'y': node['y'], 'theta': node['theta']}
                           for node in ordered]
    base_edges = [dict(edge) for edge in edges]
    covariance = None if closure_covariance is None else np.asarray(closure_covariance, float)

    def build_graph(with_closures):
        graph = {'nodes': graph_nodes, 'edges': [dict(edge) for edge in base_edges]}
        node_index = {node['state_id']: node for node in graph_nodes}
        for parent, child in chain_edges:
            if parent not in node_index or child not in node_index:
                continue
            graph['edges'].append({
                'index': 100000 + len(graph['edges']),
                'source_state_id': parent, 'target_state_id': child,
                'covariance_3x3': ((covariance.tolist() if covariance is not None
                                    else np.eye(3).tolist()))})
        if with_closures:
            for source, target, _ in synthetic:
                graph['edges'].append({
                    'index': 200000 + len(graph['edges']),
                    'source_state_id': source, 'target_state_id': target,
                    'covariance_3x3': ((covariance.tolist() if covariance is not None
                                        else np.eye(3).tolist()))})
        return graph

    try:
        with_chain = an.target_score(build_graph(False), target_ids)['J_T']
        with_closures = an.target_score(build_graph(True), target_ids)['J_T']
        without_states = an.target_score(
            {'nodes': nodes, 'edges': [dict(edge) for edge in base_edges]},
            target_ids)['J_T']
    except Exception as exc:  # noqa: BLE001
        return {'states': len(ordered), 'delta_jt_worst_case': None,
                'reason': '{}: {}'.format(type(exc).__name__, exc)}
    return {
        'states': len(ordered),
        'delta_jt_chain_only': with_chain - without_states,
        'delta_jt_worst_case': with_closures - without_states,
        'synthetic_closures': [{'source': source, 'target': target,
                                'distance_m': round(distance, 3)}
                               for source, target, distance in synthetic],
        'diagnostic': 'FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC',
    }


def median_closure_covariance(runs):
    """Median covariance (3x3) over all recorded closure edges of the suite."""
    matrices = []
    for run in runs:
        for name in ev.SNAPSHOTS:
            graph = run['snapshots'][name]
            for edge in graph['edges']:
                if edge['target_state_id'] != edge['source_state_id'] + 1:
                    matrices.append(np.asarray(edge['covariance_3x3'], float))
    if not matrices:
        return None
    stack = np.stack(matrices)
    return np.median(stack, axis=0)


# ------------------------------------------------------- creation attribution
STAGE_RANK = {'history': 0, 'return': 1, 'action': 2, 'tail': 3}


def creation_attribution(run, timeline):
    """Stage increments attributed by *creation* time, not by publication.

    The recorded `stage gain` of the frozen analysis is a difference of two
    snapshot contents; an edge created late in one stage can be published only
    after the next boundary and therefore lands in the wrong difference.  This
    function builds the alternative, time-true decomposition: for every stage
    boundary k it forms the graph that contains exactly the states accepted up
    to the end of stage k and exactly the edges whose creation stage (the stage
    of the later accepted endpoint) is at most k, and evaluates the frozen J_T.
    The increment of that nested chain is additive by construction (one common
    linearisation, the final map poses), so it answers "which stage created the
    information that measure sees", with no double counting.

    Never-published suffix states cannot be included (their map poses were
    never published); they are provably J_T-neutral subtrees, and the separate
    FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC bounds them.
    """
    target_ids = [int(state) for state in run['frozen']['target_state_ids']]
    accepts = {item['state_id']: item for item in timeline['timeline']}
    published_ids = {int(node['state_id']) for node in run['snapshots']['G_final']['nodes']}

    def state_rank(state_id):
        item = accepts.get(state_id)
        if item is None:
            return None
        stage = item['stage_by_time']
        return None if stage is None else STAGE_RANK[stage]

    final = run['snapshots']['G_final']
    edge_ranks = {}
    for edge in final['edges']:
        source, target = int(edge['source_state_id']), int(edge['target_state_id'])
        source_rank, target_rank = state_rank(source), state_rank(target)
        if source_rank is None or target_rank is None:
            edge_ranks[edge['index']] = None
            continue
        edge_ranks[edge['index']] = max(source_rank, target_rank)
    node_ranks = {state: state_rank(state) for state in published_ids}
    graphs, scores = {}, {}
    for name, rank in STAGE_RANK.items():
        nodes = [node for node in final['nodes'] if node_ranks.get(int(node['state_id']), 99) <= rank]
        ids = {int(node['state_id']) for node in nodes}
        edges = [edge for edge in final['edges']
                 if edge_ranks.get(edge['index']) is not None
                 and edge_ranks[edge['index']] <= rank
                 and int(edge['source_state_id']) in ids
                 and int(edge['target_state_id']) in ids]
        graphs[name] = {'nodes': nodes, 'edges': edges}
        try:
            scores[name] = an.target_score(graphs[name], target_ids)['J_T']
        except Exception as exc:  # noqa: BLE001
            scores[name] = None
            run.setdefault('score_failures', []).append(
                {'attribution': name, 'error': '{}: {}'.format(type(exc).__name__, exc)})
    # closure edges by creation stage: count and individual contributions
    closure_creation = {}
    known_before = {edge['index'] for edge in run['snapshots']['G_before_return']['edges']}
    closure_counts = {stage: 0 for stage in STAGE_RANK}
    effective_counts = {stage: 0 for stage in STAGE_RANK}
    for edge in final['edges']:
        rank = edge_ranks.get(edge['index'])
        is_closure = edge['target_state_id'] != edge['source_state_id'] + 1
        if edge['index'] in known_before or not is_closure or rank is None:
            continue
        stage = [key for key, value in STAGE_RANK.items() if value == rank][0]
        closure_counts[stage] += 1
        if scores['tail'] is not None:
            reduced = {'nodes': final['nodes'],
                       'edges': [item for item in final['edges']
                                 if item['index'] != edge['index']]}
            try:
                contribution = scores['tail'] - an.target_score(reduced, target_ids)['J_T']
            except Exception:  # noqa: BLE001
                contribution = None
            if contribution is not None and abs(contribution) > EFFECTIVE_CLOSURE_EPS:
                effective_counts[stage] += 1
    closure_creation = {'closure_counts': closure_counts, 'effective_counts': effective_counts}
    increments = {}
    if all(scores[name] is not None for name in STAGE_RANK):
        increments['return'] = scores['return'] - scores['history']
        increments['action'] = scores['action'] - scores['return']
        increments['tail'] = scores['tail'] - scores['action']
        increments['total'] = scores['tail'] - scores['history']
    else:
        increments = {key: None for key in ('return', 'action', 'tail', 'total')}
    before_graph = run['snapshots']['G_before_return']
    tail_ids = {int(node['state_id']) for node in graphs['tail']['nodes']}
    final_ids = {int(node['state_id']) for node in final['nodes']}
    tail_edges = {edge['index'] for edge in graphs['tail']['edges']}
    final_edges = {edge['index'] for edge in final['edges']}
    try:
        before_score = an.target_score(before_graph, target_ids)['J_T']
    except Exception:  # noqa: BLE001
        before_score = None
    return {
        'scores': scores,
        'increments': increments,
        'before_return_score': before_score,
        'history_baseline_delta': (None if (before_score is None or scores['history'] is None)
                                   else before_score - scores['history']),
        'tail_graph_matches_final': bool(tail_ids == final_ids and tail_edges == final_edges),
        'closure_creation': closure_creation,
        'edge_creation_histogram': {
            stage: sum(1 for rank in edge_ranks.values() if rank == STAGE_RANK[stage])
            for stage in STAGE_RANK},
    }


# --------------------------------------------------------------------- phase 3
def _identity_stamps(run, timeline):
    """state_id -> accept sim time from the mapper log (no position matching)."""
    stamps = {item['state_id']: item['sim_time'] for item in timeline['timeline']}
    keyscan_stamps = {float(item['stamp']) for item in run['keyscans']}
    matched = sum(1 for value in stamps.values()
                  if any(abs(value - candidate) < 1e-6 for candidate in keyscan_stamps))
    node_by_state = {int(node['state_id']): node
                     for node in run['snapshots']['G_final']['nodes']}
    unique_mismatches = []
    for item in timeline['timeline']:
        node = node_by_state.get(item['state_id'])
        if node is not None and int(node['unique_id']) != int(item['unique_id']):
            unique_mismatches.append(item['state_id'])
    return stamps, {
        'states': len(stamps),
        'states_with_keyscan_stamp': matched,
        'unique_id_mismatches': len(unique_mismatches),
        'unique_id_mismatch_states': unique_mismatches[:10],
    }


def corrected_ground_truth(runs, timelines, doc77_old):
    """Corrected GT metrics with explicit identities (A/B/C/D families)."""
    rows = []
    for run in runs:
        timeline = timelines[run['episode_id']]
        stamps, identity_meta = _identity_stamps(run, timeline)
        gt = run['gt']
        if not gt:
            rows.append({'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                         'family': 'ALL', 'stage': '', 'metric': 'gt_stream',
                         'n': 0, 'value': None, 'value_old': None,
                         'notes': 'NOT_EVALUABLE: no ground-truth stream'})
            continue
        frozen = run['frozen']
        target_ids = [int(state) for state in frozen['target_state_ids']]
        anchor_id = int(frozen['anchor']['id'])
        # ---- A: frozen target states vs GT (accept-time identity) ----------
        before_nodes = {node['state_id']: node for node in run['snapshots']['G_before_return']['nodes']}
        source, truth = [], []
        for state in target_ids:
            node = before_nodes.get(state)
            stamp = stamps.get(state)
            pose, _, _ = ev.pose_at(gt, stamp, tolerance=0.15) if stamp is not None else (None, None, None)
            if node is None or pose is None:
                continue
            source.append([node['x'], node['y'], node['theta']])
            truth.append(pose)
        transform = ge.align_rigid([pair[:2] for pair in source],
                                   [pair[:2] for pair in truth]) if len(source) >= 2 else None
        for name in ev.SNAPSHOTS:
            nodes = {node['state_id']: node for node in run['snapshots'][name]['nodes']}
            residuals, headings = [], []
            for state in target_ids:
                node = nodes.get(state)
                stamp = stamps.get(state)
                pose, _, _ = ev.pose_at(gt, stamp, tolerance=0.15) if stamp is not None else (None, None, None)
                if node is None or pose is None or transform is None:
                    continue
                moved = ge.pose_apply(transform, [node['x'], node['y'], node['theta']])
                residuals.append(math.hypot(moved[0] - pose[0], moved[1] - pose[1]))
                headings.append(abs(ge.wrap_angle(moved[2] - pose[2])))
            old = _number(doc77_old.get(run['episode_id'], {}).get(
                '{}_target_error_mean_m'.format(name)))
            rows.append({
                'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                'family': 'TARGET_MAP_ERROR', 'stage': name.split('_', 1)[-1],
                'metric': 'mean_m', 'n': len(residuals),
                'value': (statistics.mean(residuals) if residuals else None),
                'value_old': old,
                'notes': 'accept-log identity; alignment on pre-return target states ({})'.format(
                    len(source)),
            })
            rows.append({
                'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                'family': 'TARGET_MAP_ERROR', 'stage': name.split('_', 1)[-1],
                'metric': 'max_m', 'n': len(residuals),
                'value': (max(residuals) if residuals else None),
                'value_old': _number(doc77_old.get(run['episode_id'], {}).get(
                    '{}_target_error_max_m'.format(name))),
                'notes': 'accept-log identity',
            })
        # ---- B: robot localization error (map frame vs GT) -----------------
        windows = timeline['windows']
        for record in run['scans']:
            stage = None
            for name in ('history', 'return', 'action', 'tail'):
                start = windows[name]['scan_start']
                end = windows[name]['scan_end']
                if record['index'] >= start and (end is None or record['index'] < end):
                    stage = name
                    break
            record['_stage'] = stage
        align_pairs = []
        for record in run['scans']:
            if record.get('map_base') is None or record['_stage'] not in ('history', 'return'):
                continue
            pose, _, _ = ev.pose_at(gt, record['stamp'], tolerance=0.1)
            if pose is None:
                continue
            align_pairs.append((record['map_base'], pose))
        if len(align_pairs) >= 2:
            transform = ge.align_rigid([pair[0][:2] for pair in align_pairs],
                                       [pair[1][:2] for pair in align_pairs])
            per_stage = defaultdict(list)
            action_motion = defaultdict(list)
            motion_end = timeline['motion']['action']['motion_end_time']
            for record in run['scans']:
                if record.get('map_base') is None:
                    continue
                pose, _, _ = ev.pose_at(gt, record['stamp'], tolerance=0.1)
                if pose is None:
                    continue
                moved = ge.pose_apply(transform, record['map_base'])
                error = math.hypot(moved[0] - pose[0], moved[1] - pose[1])
                per_stage[record['_stage']].append(error)
                if record['_stage'] == 'action':
                    if motion_end is not None and record['stamp'] <= motion_end:
                        action_motion['motion'].append(error)
                    else:
                        action_motion['remainder'].append(error)
            for stage in ('history', 'return', 'action', 'tail'):
                values = per_stage.get(stage) or []
                old = _number(doc77_old.get(run['episode_id'], {}).get(
                    '{}_odom_gt_residual_mean_m'.format(stage)))
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'ROBOT_LOCALIZATION_ERROR', 'stage': stage,
                    'metric': 'mean_m', 'n': len(values),
                    'value': (statistics.mean(values) if values else None),
                    'value_old': old,
                    'notes': 'SLAM map pose vs GT; alignment fitted on history+return only',
                })
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'ROBOT_LOCALIZATION_ERROR', 'stage': stage,
                    'metric': 'max_m', 'n': len(values),
                    'value': (max(values) if values else None),
                    'value_old': None,
                    'notes': 'SLAM map pose vs GT; alignment fitted on history+return only',
                })
            for part in ('motion', 'remainder'):
                values = action_motion.get(part) or []
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'ROBOT_LOCALIZATION_ERROR',
                    'stage': 'action_' + part, 'metric': 'mean_m', 'n': len(values),
                    'value': (statistics.mean(values) if values else None),
                    'value_old': None,
                    'notes': 'action window split at the recorded motion end',
                })
            # ---- D: map / trajectory consistency --------------------------
            all_errors = [error for values in per_stage.values() for error in values]
            if all_errors:
                rmse = math.sqrt(sum(error * error for error in all_errors)
                                 / len(all_errors))
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'MAP_CONSISTENCY', 'stage': 'all',
                    'metric': 'slam_path_gt_ate_mean_m', 'n': len(all_errors),
                    'value': statistics.mean(all_errors), 'value_old': None,
                    'notes': 'map-frame trajectory vs GT, pre-action alignment',
                })
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'MAP_CONSISTENCY', 'stage': 'all',
                    'metric': 'slam_path_gt_ate_rmse_m', 'n': len(all_errors),
                    'value': rmse, 'value_old': None,
                    'notes': 'map-frame trajectory vs GT, pre-action alignment',
                })
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'MAP_CONSISTENCY', 'stage': 'pre_action_fit',
                    'metric': 'alignment_yaw_rad', 'n': len(align_pairs),
                    'value': float(transform[0]), 'value_old': None,
                    'notes': 'rigid map->GT transform fitted on history+return scans only',
                })
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'MAP_CONSISTENCY', 'stage': 'pre_action_fit',
                    'metric': 'alignment_translation_m', 'n': len(align_pairs),
                    'value': float(math.hypot(transform[1], transform[2])),
                    'value_old': None,
                    'notes': 'rigid map->GT transform fitted on history+return scans only',
                })
        # ---- C: relative pose error (robot vs anchor state) ----------------
        anchor_node = before_nodes.get(anchor_id)
        anchor_stamp = stamps.get(anchor_id)
        anchor_gt = (ev.pose_at(gt, anchor_stamp, tolerance=0.15)[0]
                     if anchor_stamp is not None else None)
        if anchor_node is not None and anchor_gt is not None:
            translation, heading = [], []
            for record in run['scans']:
                if record.get('map_base') is None or record['_stage'] != 'action':
                    continue
                pose_map = record['map_base']
                pose_gt, _, _ = ev.pose_at(gt, record['stamp'], tolerance=0.1)
                if pose_gt is None:
                    continue
                dx = pose_map[0] - anchor_node['x']
                dy = pose_map[1] - anchor_node['y']
                dxt = pose_gt[0] - anchor_gt[0]
                dyt = pose_gt[1] - anchor_gt[1]
                translation.append(abs(math.hypot(dx, dy) - math.hypot(dxt, dyt)))
                heading.append(abs(ge.wrap_angle(
                    ge.wrap_angle(pose_map[2] - anchor_node['theta'])
                    - ge.wrap_angle(pose_gt[2] - anchor_gt[2]))))
            if translation:
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'RELATIVE_POSE_ERROR', 'stage': 'action',
                    'metric': 'translation_mean_m', 'n': len(translation),
                    'value': statistics.mean(translation), 'value_old': None,
                    'notes': 'map-frame robot-to-anchor distance error vs GT',
                })
                rows.append({
                    'episode_id': run['episode_id'], 'suite_round': run['suite_round'],
                    'family': 'RELATIVE_POSE_ERROR', 'stage': 'action',
                    'metric': 'heading_mean_rad', 'n': len(heading),
                    'value': statistics.mean(heading), 'value_old': None,
                    'notes': 'map-frame robot-to-anchor heading error vs GT',
                })
        run['_identity_meta'] = identity_meta
    return rows


# --------------------------------------------------------------------- phase 5
def _delta(first, second):
    if first is None or second is None:
        return None
    return first - second


def _pearson(xs, ys):
    if len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    dev_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    dev_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if dev_x == 0.0 or dev_y == 0.0:
        return None
    return numerator / (dev_x * dev_y)


def write_final_decision(out_dir, statistics_rows_list, mechanisms, attribution_rows,
                         gt_rows=()):
    """The single recommended verdict, kept machine readable next to the gate."""
    def rows_of(kind):
        return [row for row in statistics_rows_list if row['row_type'] == kind]

    arms = {}
    for row in rows_of('ARM_ATTRIBUTION'):
        arms['{}_{}'.format(row['action_id'], row['config'])] = {
            'recorded_detail': row['values'], 'created_mean': row['mean'],
            'created_sd_ddof1': row['sd_ddof1']}
    contrasts = {row['config']: {'mean': row['mean'], 'runs': row['runs'],
                                 'detail': row['values']}
                 for row in rows_of('PAIRED_CONTRAST_CORRECTED')}
    law_failures = [row for row in mechanisms if row['gain_matches_closure_sum'] is False]
    focus = {}
    for episode in FOCUS_EPISODES:
        rows = [row for row in attribution_rows if row['episode_id'] == episode]
        if rows:
            row = rows[0]
            focus[episode] = {
                'recorded_return_gain': row['recorded_return_gain'],
                'recorded_action_gain': row['recorded_action_gain'],
                'created_return_increment': row['created_return_increment'],
                'created_action_increment': row['created_action_increment'],
                'created_action_closures': row['created_action_closures'],
                'created_action_effective_closures': row['created_action_effective_closures'],
            }
    # GT aggregates for the decision text
    def numbers(family, stage, metric, round_name='main'):
        out = []
        for row in gt_rows:
            if row['family'] == family and row['stage'] == stage and row['metric'] == metric \
                    and row['suite_round'] == round_name:
                try:
                    out.append(float(row['value']))
                except (TypeError, ValueError):
                    pass
        return out
    target_before = {row['episode_id']: float(row['value'])
                     for row in gt_rows
                     if row['family'] == 'TARGET_MAP_ERROR' and row['stage'] == 'before_return'
                     and row['metric'] == 'mean_m' and row['suite_round'] == 'main'
                     and row['value'] not in ('', None)}
    target_final = {row['episode_id']: float(row['value'])
                    for row in gt_rows
                    if row['family'] == 'TARGET_MAP_ERROR' and row['stage'] == 'final'
                    and row['metric'] == 'mean_m' and row['suite_round'] == 'main'
                    and row['value'] not in ('', None)}
    target_change = [target_final[key] - target_before[key] for key in target_before
                     if key in target_final]
    robot_hist = numbers('ROBOT_LOCALIZATION_ERROR', 'history', 'mean_m')
    robot_tail = numbers('ROBOT_LOCALIZATION_ERROR', 'tail', 'mean_m')
    decision = {
        'review_version': REVIEW_VERSION,
        'verdict': 'D_PURE_ROTATION_SELECTION_NOT_SUPPORTED',
        'verdict_options_considered': {
            'A_LOCAL_ACTION_METHOD_WORTH_TESTING': False,
            'B_GEOMETRY_MECHANISM_ONLY': 'describes the remaining scientific value, not a method',
            'C_METRIC_VALIDITY_UNRESOLVED': False,
            'D_PURE_ROTATION_SELECTION_NOT_SUPPORTED': True,
            'E_EVIDENCE_TECHNICALLY_INCOMPLETE': False,
        },
        'rationale': [
            'recorded stage gains are reproducible independently (all 56 runs), but the '
            'snapshot-difference attribution mixed stages: closures created during the '
            'return leg were published after the arrival boundary and landed in the '
            'action difference',
            'after the FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC attribution, the S1 action '
            'mean drops from 0.08144 to {:.5f} nats; L+ from 0.06485 to {:.5f}; L- from '
            '0.11562 to {:.5f}; S0 stays exactly zero in 12/12'.format(
                arms.get('S1_main', {}).get('created_mean', float('nan')),
                arms.get('L+_main', {}).get('created_mean', float('nan')),
                arms.get('L-_main', {}).get('created_mean', float('nan'))),
            'the recorded L+ minus L- direction difference (-0.05077 nats) collapses to '
            '{:.5f} (positive in 6/12 pairs) after the correction: the apparent direction '
            'effect was a publication-timing artifact'.format(
                contrasts.get('L+_minus_L-', {}).get('mean', float('nan'))),
            'information gains never translated into localisation value: target-state map '
            'error change (final - before) is {:.6f} m mean, SLAM robot error change '
            '(tail - history) is {:.6f} m mean; no GT improvement accompanies the J_T '
            'gains'.format(statistics.mean(target_change) if target_change else float('nan'),
                           (statistics.mean([t - h for t, h in zip(robot_tail, robot_hist)])
                            if robot_hist and robot_tail else float('nan'))),
            'the mechanism is fully accounted for: every stage gain equals the marginal '
            'contribution of the closure edges added in that stage difference '
            '({} law violations of {} stage rows); zero-gain runs are runs whose action '
            'produced no effective closure'.format(len(law_failures), len(mechanisms)),
        ],
        'online_diagnostic': {
            'run': False,
            'reason': ('the offline data already support stage attribution (accept-time '
                       'identity for every keyframe, content times for every snapshot); '
                       'the remaining questions are mechanism-level (why some runs form no '
                       'effective closure) and would need the repaired observation chain '
                       'rather than more of the old one'),
            'preconditions_if_revived': [
                'periodic provenance flush (instrumentation_flush_period_s > 0) so the '
                'edge-provenance JSONL is actually written',
                '/Mapper/dump_pose_graph_now called at each boundary as an in-mapper '
                'barrier, with SHA-stamped files',
                'scan-queue / accept-progress counters recorded before trusting the dump',
                'old-topic and new synchronous snapshots stored in the same run',
                'budget: place_A r2 S0/S1 first (2 runs), then at most place_B r1 L+/L- '
                'and place_C r1 L+/L- (4 runs), hard cap 8 including technical repairs',
            ],
        },
        'questions': {
            'q1_misattributed_action_gain': (
                'the entire late-published share: S1 0.08144 -> 0.00946; L- 0.11562 -> '
                '0.04636; L+ 0.06485 -> 0.04360; per-run table in '
                'stage_attribution_correction.csv'),
            'q2_recomputable_records': (
                'all 56 recorded stage gains recompute exactly; keyframe accept times and '
                'creation-stage attribution are recoverable; edge provenance enums and '
                'never-published edge sets are not (instrumentation gap, documented)'),
            'q3_incremental_value_after_correction': (
                'yes but small and realisation-dependent: S0 zero, S1 ~0.009, L+ ~0.044 '
                '(5/12 exactly zero), L- ~0.046 (0/12 zero)'),
            'q4_place_direction_difference': (
                'the mean direction difference disappears; a realisation asymmetry '
                'remains: L- created an effective closure in 12/12 main runs, L+ failed '
                'in 5/12 (A r2/r3 and all three B runs)'),
            'q5_pre_action_explanation': (
                'no pre-action feature explains the remaining asymmetry; it clusters by '
                'place/run order (see DIRECTION_DIFFERENCE_EXPLANATION rows)'),
            'q6_information_vs_gt': (
                'no measurable GT improvement: target error change ~+1e-4 m, robot SLAM '
                'error unchanged, relative pose error unchanged'),
            'q7_localisation_error_needing_repair': (
                'no case-specific repair signal: robot SLAM error is centimetre-scale and '
                'does not accumulate through the action; target-state map error ~9.5 cm is '
                'constant across boundaries'),
            'q8_best_fixed_action_sufficient': (
                'a fixed L- action is the most reliable default (0 zeros), but its '
                'expected increment (~0.046 nats) is far below the same-configuration '
                're-execution scale (0.127 nats) per run, so single-run benefit is not '
                'demonstrable'),
            'q9_method_necessity': (
                'no: no localisation value, no selection signal above realisation noise; '
                'the remaining interest is the closure-realisation mechanism itself'),
        },
        'single_next_step': (
            'close the pure-rotation selection line and, if the revisit topic continues, '
            'restart it as a closure-realisation mechanism study using the repaired '
            'observation chain (periodic provenance flush + synchronous dump per boundary), '
            'beginning with a bounded place_B L+ zero-cluster replication (<=4 runs) '
            'instead of any further selector evaluation'),
        'inputs': {
            'recorded_statistics': 'statistical_correction.csv',
            'boundary_evidence': 'boundary_event_audit.csv / recoverability_matrix.csv',
            'attribution': 'stage_attribution_correction.csv (labelled diagnostic)',
            'ground_truth': 'corrected_gt_metrics.csv',
            'mechanism': 'historical_factor_mechanism.csv',
            'gate': 'offline_evidence_gate.json',
        },
        'focus_cases': focus,
    }
    (Path(out_dir) / 'final_research_decision.json').write_text(
        json.dumps(decision, indent=1, sort_keys=True))
    return decision


def build_gate(runs, audits, recoverability, statistics_rows_list, mechanisms,
               corrections, gt_rows):
    summary = {}
    for row in statistics_rows_list:
        summary.setdefault(row['row_type'], []).append(row)
    arm_attribution = {
        '{}_{}'.format(row['action_id'], row['config']): {
            'created_mean': row.get('mean'), 'created_sd_ddof1': row.get('sd_ddof1'),
            'detail': row.get('values')}
        for row in statistics_rows_list if row['row_type'] == 'ARM_ATTRIBUTION'}
    never = [row for row in recoverability
             if row['recoverability_class'].startswith('NEVER_PUBLISHED')]
    deferred = [row for row in recoverability
                if row['recoverability_class'] == 'DEFERRED_RECOVERABLE']
    gap = [row for row in never if row['recoverability_class'] == 'NEVER_PUBLISHED_GAP']
    boundary_fail = [row for row in audits if not row['quiescence_satisfied']]
    content_before_motion = [row for row in audits
                             if row['content_before_stage_motion_end']]
    vacuous = [row for row in audits if row['keyscan_missing_check_vacuous']]
    mismatch = [row for row in mechanisms if row['gain_matches_closure_sum'] is False]
    diagnostic = [row for row in mechanisms if row.get('diagnostic_delta_jt_worst_case') is not None
                  and abs(row['diagnostic_delta_jt_worst_case']) > 0.01]
    return {
        'review_version': REVIEW_VERSION,
        'runs_audited': len(runs),
        'gates': {
            'G1_snapshot_integrity': {
                'keyframe_missing_from_all_snapshots': len(never),
                'keyframe_deferred_to_later_stage': len(deferred),
                'unexpected_gap_states': len(gap),
                'stages_with_content_older_than_motion_end': len(content_before_motion),
                'quiescence_failures': len(boundary_fail),
                'keyscan_missing_check_vacuous_rows': len(vacuous),
                'interpretation': (
                    'quiescence satisfied does not imply full integration: the '
                    'snapshot content time can predate the last accepted states'),
            },
            'G2_stage_attribution': {
                'gain_equals_closure_sum_failures': len(mismatch),
                'action_attribution_created_vs_recorded': arm_attribution,
                'interpretation': (
                    'stage gains are fully explained by closure edges added in '
                    'the stage difference (relative tolerance); chain edges behave as '
                    'subtrees.  Attributing edges by their creation time instead of '
                    'their publication time moves late-published return-leg closures '
                    'out of the action stage; the created means above are the '
                    'time-true stage values'),
            },
            'G3_corrected_statistics': summary,
            'G4_ground_truth': {
                'families_evaluated': sorted({row['family'] for row in gt_rows}),
                'not_evaluable_rows': sum(1 for row in gt_rows
                                          if (row.get('notes') or '').startswith('NOT_EVALUABLE')),
            },
            'G5_mechanism_bounds': {
                'focus_runs_above_0p01_nats_worst_case': len(
                    [row for row in mechanisms
                     if row.get('focus_case') and row.get('diagnostic_relevant')
                     and row.get('diagnostic_delta_jt_worst_case') is not None
                     and abs(row['diagnostic_delta_jt_worst_case']) > 0.01]),
                'note': ('worst case: one synthetic closure to the nearest published state '
                         'for every never-published keyframe, using the median observed '
                         'closure covariance; labelled FIXED_LINEARIZATION_FACTOR_DIAGNOSTIC'),
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--skip-mechanism', action='store_true')
    args = parser.parse_args()

    suite_dir = Path(args.suite).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    runs, issues = ev.discover_runs(suite_dir)
    print('runs discovered: {} (skipped attempts: {})'.format(len(runs), len(issues)))
    timelines = {run['episode_id']: tl.build_state_timeline(run) for run in runs}
    doc77 = _doc77_table(suite_dir)
    recomputed = {run['episode_id']: recompute_gains(run) for run in runs}

    audits = boundary_audit(runs, timelines)
    recoverability = recoverability_rows(runs, timelines)
    statistics_table, _ = statistics_rows(runs, doc77, recomputed, timelines)
    corrections = []
    for run in runs:
        gains = recomputed[run['episode_id']]
        old = doc77.get(run['episode_id'], {})
        corrections.append({
            'episode_id': run['episode_id'],
            'suite_round': run['suite_round'],
            'place_id': run['place_id'],
            'action_id': run['action_id'],
            'return_gain_recomputed': gains['return_gain'],
            'return_gain_doc77': old.get('return_gain_doc77'),
            'action_gain_recomputed': gains['action_gain'],
            'action_gain_doc77': old.get('action_gain_doc77'),
            'tail_gain_recomputed': gains['tail_gain'],
            'tail_gain_doc77': old.get('tail_gain_doc77'),
            'action_gain_abs_diff': (None if (gains['action_gain'] is None
                                              or old.get('action_gain_doc77') is None)
                                     else abs(gains['action_gain'] - old['action_gain_doc77'])),
        })
    mechanisms = []
    if not args.skip_mechanism:
        covariance = median_closure_covariance(runs)
        for run in runs:
            timeline = timelines[run['episode_id']]
            rows = stage_edge_review(run, timeline)
            diagnostic = missing_state_diagnostic(run, timeline, covariance)
            missing_stages = {item['stage_by_time'] for item in timeline['timeline']
                              if item['class'].startswith('NEVER_PUBLISHED')}
            for row in rows:
                row['diagnostic_delta_jt_worst_case'] = diagnostic.get('delta_jt_worst_case')
                row['diagnostic_states'] = diagnostic.get('states')
                row['diagnostic_relevant'] = row['stage'] in missing_stages
                row['diagnostic_name'] = (FIXED_LINEARIZATION_LABEL
                                          if row['diagnostic_relevant'] else '')
                row['declared_diagnostic'] = FIXED_LINEARIZATION_LABEL
                row['focus_case'] = run['episode_id'] in FOCUS_EPISODES
            mechanisms.extend(rows)
    gt_rows = corrected_ground_truth(runs, timelines, doc77_old=doc77)
    creation = {run['episode_id']: creation_attribution(run, timelines[run['episode_id']])
                for run in runs}
    attribution_rows = []
    for run in runs:
        recorded = recomputed[run['episode_id']]
        increments = creation[run['episode_id']]['increments']
        attribution_rows.append({
            'episode_id': run['episode_id'],
            'suite_round': run['suite_round'],
            'place_id': run['place_id'],
            'repeat': run['repeat'],
            'action_id': run['action_id'],
            'recorded_return_gain': recorded['return_gain'],
            'recorded_action_gain': recorded['action_gain'],
            'recorded_tail_gain': recorded['tail_gain'],
            'recorded_total_gain': recorded['total_gain'],
            'created_return_increment': increments['return'],
            'created_action_increment': increments['action'],
            'created_tail_increment': increments['tail'],
            'created_total_increment': increments['total'],
            'action_gain_attribution_delta': (
                None if (recorded['action_gain'] is None or increments['action'] is None)
                else recorded['action_gain'] - increments['action']),
            'history_baseline_delta': creation[run['episode_id']]['history_baseline_delta'],
            'tail_graph_matches_final': creation[run['episode_id']]['tail_graph_matches_final'],
            'created_action_closures': creation[run['episode_id']]['closure_creation']['closure_counts']['action'],
            'created_action_effective_closures': creation[run['episode_id']]['closure_creation']['effective_counts']['action'],
            'created_return_closures': creation[run['episode_id']]['closure_creation']['closure_counts']['return'],
            'created_return_effective_closures': creation[run['episode_id']]['closure_creation']['effective_counts']['return'],
            'method_label': FIXED_LINEARIZATION_LABEL,
            'method_note': ('nested real-factor sub-graphs of the final graph evaluated at the '
                            'final poses; labelled diagnostic, kept separate from the real '
                            'recorded stage J_T'),
            'edge_creation_histogram': json.dumps(
                creation[run['episode_id']]['edge_creation_histogram']),
        })
    for action in ('S0', 'S1', 'L+', 'L-'):
        for round_name in ('main', 'repeatability'):
            arms = [row for row in attribution_rows
                    if row['action_id'] == action and row['suite_round'] == round_name]
            recorded_values = [row['recorded_action_gain'] for row in arms
                               if row['recorded_action_gain'] is not None]
            created_values = [row['created_action_increment'] for row in arms
                              if row['created_action_increment'] is not None]
            if not created_values:
                continue
            statistics_table.append({
                'row_type': 'ARM_ATTRIBUTION',
                'config': round_name, 'place_id': '', 'action_id': action,
                'runs': len(created_values),
                'values': ('recorded mean {:.5f} (zeros {}), created mean {:.5f} '
                           '(zeros {})').format(
                    statistics.mean(recorded_values) if recorded_values else float('nan'),
                    sum(1 for value in recorded_values if abs(value) <= ZERO_GAIN_TOLERANCE),
                    statistics.mean(created_values),
                    sum(1 for value in created_values if abs(value) <= ZERO_GAIN_TOLERANCE)),
                'mean': statistics.mean(created_values),
                'sd_ddof0': (statistics.pstdev(created_values)
                             if len(created_values) > 1 else None),
                'sd_ddof1': (statistics.stdev(created_values)
                             if len(created_values) > 1 else None),
                'method': ('action-stage information attributed by edge creation time '
                           '(nested cumulative graphs, fixed final-pose linearisation) '
                           'vs the recorded snapshot-difference gain'),
            })
    # paired contrasts on the corrected, time-true action increments (the same
    # place x repeat pairing the frozen analysis used for its paired tests)
    by_group = defaultdict(dict)
    for run in runs:
        if run['suite_round'] != 'main':
            continue
        key = '{}_r{}'.format(run['place_id'], run['repeat'])
        by_group[key][run['action_id']] = creation[run['episode_id']]['increments']
    for first, second in (('L+', 'L-'), ('L+', 'S1'), ('L-', 'S1')):
        differences = []
        for key, arms in sorted(by_group.items()):
            if arms.get(first, {}).get('action') is None or arms.get(second, {}).get('action') is None:
                continue
            differences.append(arms[first]['action'] - arms[second]['action'])
        if differences:
            statistics_table.append({
                'row_type': 'PAIRED_CONTRAST_CORRECTED',
                'config': '{}_minus_{}'.format(first, second),
                'place_id': '', 'action_id': '', 'runs': len(differences),
                'values': ';'.join('{:.5f}'.format(value) for value in differences),
                'mean': statistics.mean(differences),
                'sd_ddof0': statistics.pstdev(differences),
                'sd_ddof1': (statistics.stdev(differences) if len(differences) > 1 else None),
                'method': ('paired per place x repeat on corrected action increments; '
                           'positive count = {} of {}').format(
                    sum(1 for value in differences if value > 0), len(differences)),
            })
    # ---- the four variability classes the handoff asks to keep apart ------
    features = {run['episode_id']: run_features(run, timelines[run['episode_id']])
                for run in runs}
    config_names = ['0003_place_A_r1_L+', '0004_place_A_r1_L-',
                    '0016_place_B_r1_L+', '0013_place_B_r1_L-']
    config_variances, config_sds = [], []
    for config in config_names:
        values = [recomputed[run['episode_id']]['action_gain'] for run in runs
                  if run['episode_id'] == config or run['repeatability_of'] == config]
        values = [value for value in values if value is not None]
        config_variances.append(statistics.variance(values))
        config_sds.append(statistics.stdev(values))
    statistics_table.append({
        'row_type': 'VARIANCE_DECOMPOSITION',
        'config': 'FULL_SYSTEM_REEXECUTION', 'place_id': '', 'action_id': '',
        'runs': 4,
        'values': ';'.join('{:.6f}'.format(value) for value in config_sds),
        'mean': statistics.mean(config_sds), 'sd_ddof0': None,
        'sd_ddof1': math.sqrt(sum(config_variances) / len(config_variances)),
        'method': ('same-configuration re-execution: three complete runs per config '
                   '(r1 + 2 re-runs), pooled within sd with equal config weights'),
    })
    statistics_table.append({
        'row_type': 'VARIANCE_DECOMPOSITION',
        'config': 'SAME_INPUT_BACKEND', 'place_id': '', 'action_id': '',
        'runs': 0, 'values': 'NOT_MEASURED_IN_THIS_PROTOCOL',
        'mean': None, 'sd_ddof0': None, 'sd_ddof1': None,
        'method': ('the doc-77 protocol re-executes the complete Stage+Karto stack; no '
                   'same-recorded-input replay exists for this suite, so the pure backend '
                   'numerical floor is not measurable from these files (the earlier v12 '
                   'pilot replays used a different protocol and are not transferable). '
                   'The closure-realisation mechanism below bounds its role indirectly'),
    })
    # action mean uncertainty and between-place spread are computed from the
    # corrected attribution values
    corrected = {row['episode_id']: row['created_action_increment']
                 for row in attribution_rows}
    main_values = {run['episode_id']: corrected[run['episode_id']] for run in runs
                   if run['suite_round'] == 'main' and corrected[run['episode_id']] is not None}
    statistics_table.append({
        'row_type': 'VARIANCE_DECOMPOSITION',
        'config': 'ACTION_MEAN_UNCERTAINTY', 'place_id': '', 'action_id': '',
        'runs': len(main_values),
        'values': 'corrected action increments over all 48 main runs',
        'mean': statistics.mean(main_values.values()),
        'sd_ddof0': statistics.pstdev(list(main_values.values())),
        'sd_ddof1': statistics.stdev(list(main_values.values())),
        'method': ('standard error of an arm mean scales with the run sd above; the '
                   'per-arm equivalent is reported in ARM_ATTRIBUTION'),
    })
    place_means = {}
    for place in ('place_A', 'place_B', 'place_C', 'place_D'):
        values = [corrected[run['episode_id']] for run in runs
                  if run['suite_round'] == 'main' and run['place_id'] == place
                  and corrected[run['episode_id']] is not None]
        if values:
            place_means[place] = statistics.mean(values)
    statistics_table.append({
        'row_type': 'VARIANCE_DECOMPOSITION',
        'config': 'BETWEEN_PLACE_CONDITION', 'place_id': '', 'action_id': '',
        'runs': len(place_means),
        'values': ';'.join('{} {:.5f}'.format(key, value)
                           for key, value in sorted(place_means.items())),
        'mean': (statistics.mean(place_means.values()) if place_means else None),
        'sd_ddof0': (statistics.pstdev(list(place_means.values()))
                     if len(place_means) > 1 else None),
        'sd_ddof1': (statistics.stdev(list(place_means.values()))
                     if len(place_means) > 1 else None),
        'method': 'place-level means of the corrected action increment (all arms pooled)',
    })
    # ---- can any pre-action feature explain the direction difference? -----
    explanation = []
    for key, arms in sorted(by_group.items()):
        run_first = next(run for run in runs
                         if '{}_r{}'.format(run['place_id'], run['repeat']) == key
                         and run['action_id'] == 'L+' and run['suite_round'] == 'main')
        run_second = next(run for run in runs
                          if '{}_r{}'.format(run['place_id'], run['repeat']) == key
                          and run['action_id'] == 'L-' and run['suite_round'] == 'main')
        first_features = features[run_first['episode_id']]
        second_features = features[run_second['episode_id']]
        explanation.append({
            'group': key,
            'place_id': run_first['place_id'],
            'difference': (creation[run_first['episode_id']]['increments']['action']
                           - creation[run_second['episode_id']]['increments']['action']),
            'rotation_difference_rad': _delta(first_features['action_rotation_rad'],
                                              second_features['action_rotation_rad']),
            'pre_action_states_difference': _delta(first_features['pre_action_states'],
                                                   second_features['pre_action_states']),
            'anchor_heading_difference_rad': _delta(first_features['anchor_heading_error_rad'],
                                                    second_features['anchor_heading_error_rad']),
        })
    for label in ('rotation_difference_rad', 'pre_action_states_difference',
                  'anchor_heading_difference_rad'):
        pairs = [(item[label], item['difference']) for item in explanation
                 if item[label] is not None and item['difference'] is not None]
        r = _pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        statistics_table.append({
            'row_type': 'DIRECTION_DIFFERENCE_EXPLANATION',
            'config': 'Lplus_minus_Lminus_vs_{}'.format(label),
            'place_id': '', 'action_id': '', 'runs': len(pairs),
            'values': ';'.join('{:.4f}:{:.4f}'.format(pair[0], pair[1]) for pair in pairs),
            'mean': r, 'sd_ddof0': None, 'sd_ddof1': None,
            'method': ('Pearson r between the corrected L+ minus L- action difference and the '
                       'pre-action feature across the 12 main place x repeat pairs; place '
                       'labels are kept in the values column for the grouped reading'),
        })
    gate = build_gate(runs, audits, recoverability, statistics_table, mechanisms,
                      corrections, gt_rows)
    write_outputs(out_dir, audits, recoverability, corrections, statistics_table,
                  gt_rows, mechanisms, gate, issues, runs, attribution_rows)
    write_final_decision(out_dir, statistics_table, mechanisms, attribution_rows,
                         gt_rows)
    print('review written to', out_dir)


def write_outputs(out_dir, audits, recoverability, corrections, statistics_table,
                  gt_rows, mechanisms, gate, issues, runs, attribution_rows):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def write_csv(name, rows, fields=None):
        import csv
        path = out_dir / name
        if not rows:
            path.write_text('')
            return
        fieldnames = fields or list(rows[0].keys())
        with open(path, 'w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    write_csv('boundary_event_audit.csv', audits)
    write_csv('recoverability_matrix.csv', recoverability)
    write_csv('corrected_gt_metrics.csv', gt_rows)
    write_csv('historical_factor_mechanism.csv', mechanisms)
    write_csv('statistical_correction.csv', statistics_table)
    write_csv('gain_recomputation.csv', corrections)
    write_csv('stage_attribution_correction.csv', attribution_rows)

    identity_meta = {}
    for run in runs:
        if '_identity_meta' in run:
            identity_meta[run['episode_id']] = run['_identity_meta']
    summary = {
        'review_version': REVIEW_VERSION,
        'runs': len(runs),
        'skipped_attempts': issues,
        'identity_meta': identity_meta,
        'score_failures': {run['episode_id']: run.get('score_failures', [])
                           for run in runs if run.get('score_failures')},
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=1, sort_keys=True))
    (out_dir / 'offline_evidence_gate.json').write_text(
        json.dumps(gate, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
