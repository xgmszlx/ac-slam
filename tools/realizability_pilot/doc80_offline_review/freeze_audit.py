#!/usr/bin/python3
"""Doc-80 section 3.3: frozen-target consistency audit.

Re-runs the *exact* driver-side freeze rule on
(a) the executed topic-cache graph (fidelity reproduction),
(b) the synchronous ``G_before_return_sync`` graph with the executed reference,
(c) both graphs with a laser-frame-corrected reference,

and reports whether the missing topic nodes / the base-vs-laser lever arm could
have changed the frozen anchor / target identity.  Sensitivity only: the
ORIGINAL_FROZEN_TARGET_ESTIMAND is never replaced.
"""

import json
import math
from pathlib import Path

from . import common

ANCHOR_HEADING_WEIGHT = 0.5  # spec['target_anchor_heading_weight']
TARGET_STATE_COUNT = 5


# --- verbatim semantics of driver.contiguous_segment / cr.select_target_states
def contiguous_segment(nodes, reference, radius, heading_weight=ANCHOR_HEADING_WEIGHT):
    def pose_distance(node):
        return (math.hypot(node['x'] - reference[0], node['y'] - reference[1])
                + heading_weight * abs(common.wrap(node['theta'] - reference[2])))

    anchor = min(nodes, key=pose_distance)
    ordered = sorted(nodes, key=lambda node: node['id'])
    anchor_index = next(index for index, node in enumerate(ordered)
                        if node['id'] == anchor['id'])

    def inside(node):
        return math.hypot(node['x'] - anchor['x'], node['y'] - anchor['y']) <= radius

    left = anchor_index
    while (left > 0 and ordered[left - 1]['id'] + 1 == ordered[left]['id']
           and inside(ordered[left - 1])):
        left -= 1
    right = anchor_index
    while (right + 1 < len(ordered)
           and ordered[right]['id'] + 1 == ordered[right + 1]['id']
           and inside(ordered[right + 1])):
        right += 1
    return anchor, ordered[left:right + 1]


def select_target_states(segment, count=TARGET_STATE_COUNT):
    if len(segment) < count:
        return list(segment)
    positions = [0.0]
    for index in range(1, len(segment)):
        previous = segment[index - 1]
        node = segment[index]
        positions.append(positions[-1] + math.hypot(node['x'] - previous['x'],
                                                    node['y'] - previous['y']))
    total = positions[-1]
    if total <= 0.0:
        return list(segment[:count])
    selected = []
    used = set()
    for step in range(count):
        quantile = total * step / float(count - 1)
        best_index = min(range(len(segment)),
                         key=lambda i: abs(positions[i] - quantile))
        while best_index in used and best_index + 1 < len(segment):
            best_index += 1
        used.add(best_index)
        selected.append(segment[best_index])
    return selected


def freeze_from(nodes, reference, radius, max_distance, heading_tolerance,
                min_history_nodes):
    anchor, segment = contiguous_segment(nodes, reference, radius)
    selected = select_target_states(segment)
    anchor_distance = math.hypot(anchor['x'] - reference[0],
                                 anchor['y'] - reference[1])
    anchor_heading_error = abs(common.wrap(anchor['theta'] - reference[2]))
    checks = {
        'minimum_history_node_count': len(nodes) >= min_history_nodes,
        'anchor_within_reference_radius': anchor_distance <= max_distance,
        'anchor_heading_within_tolerance': anchor_heading_error <= heading_tolerance,
        'segment_has_target_states': len(segment) >= TARGET_STATE_COUNT,
        'anchor_is_not_root': int(anchor['id']) != int(nodes[0]['id']),
    }
    return {'anchor': anchor, 'segment': segment, 'selected': selected,
            'checks': checks, 'passed': all(checks.values()),
            'anchor_distance_m': anchor_distance,
            'anchor_heading_error_rad': anchor_heading_error}


def audit_run(run):
    frozen = run['frozen']
    spec = run['spec']
    radius = float(spec['target_segment_radius_m'])
    max_distance = float(spec['target_anchor_max_distance_m'])
    heading_tolerance = float(spec['target_anchor_heading_tolerance_rad'])
    min_history_nodes = int(spec['minimum_history_node_count'])
    reference = [float(value) for value in frozen['reference_mapper_pose']]
    reference_laser = common.compose(tuple(reference), (0.2, 0.0, 0.0))

    topic = common.topic_payload(run, 'before_return')
    sync = common.sync_graph(run, 'before_return')
    if topic is None or sync is None:
        return None
    topic_nodes = topic['graph']['nodes']
    # topic payload node ids = vertex index = state id (verified in frame audit)
    sync_nodes = [{'id': node['state_id'], 'unique_id': node['unique_id'],
                   'x': node['x'], 'y': node['y'], 'theta': node['theta']}
                  for node in sync['nodes']]
    sync_ids = {node['id'] for node in sync_nodes}
    topic_ids = {node['id'] for node in topic_nodes}
    missing_in_topic = sorted(sync_ids - topic_ids)
    extra_in_topic = sorted(topic_ids - sync_ids)

    original = {
        'anchor': int(frozen['anchor']['id']),
        'targets': [int(value) for value in frozen['target_state_ids']],
        'segment': [int(value) for value in frozen['segment_state_ids']],
    }

    def summarise(result, tag):
        return {
            'tag': tag,
            'anchor': int(result['anchor']['id']),
            'targets': [int(node['id']) for node in result['selected']],
            'segment': [int(node['id']) for node in result['segment']],
            'passed': bool(result['passed']),
            'anchor_distance_m': float(result['anchor_distance_m']),
            'anchor_heading_error_rad': float(result['anchor_heading_error_rad']),
        }

    reproduction = summarise(freeze_from(topic_nodes, reference, radius,
                                         max_distance, heading_tolerance,
                                         min_history_nodes), 'TOPIC_EXECUTED')
    sync_same_ref = summarise(freeze_from(sync_nodes, reference, radius,
                                          max_distance, heading_tolerance,
                                          min_history_nodes), 'SYNC_EXECUTED_REF')
    sync_laser_ref = summarise(freeze_from(sync_nodes, reference_laser, radius,
                                           max_distance, heading_tolerance,
                                           min_history_nodes), 'SYNC_LASER_REF')
    topic_laser_ref = summarise(freeze_from(topic_nodes, reference_laser, radius,
                                            max_distance, heading_tolerance,
                                            min_history_nodes), 'TOPIC_LASER_REF')

    topic_only = [node for node in topic_nodes if node['id'] in missing_in_topic]
    geometry = {}
    for tag, summary in (('SYNC_EXECUTED_REF', sync_same_ref),
                         ('SYNC_LASER_REF', sync_laser_ref),
                         ('TOPIC_LASER_REF', topic_laser_ref)):
        anchor = summary['anchor']
        same = [t for t in summary['targets'] if t in original['targets']]
        moved = [t for t in summary['targets'] if t not in original['targets']]
        dropped = [t for t in original['targets'] if t not in summary['targets']]
        geometry[tag] = {
            'anchor_same': anchor == original['anchor'],
            'anchor_shift_m': _node_distance(topic_nodes, original['anchor'], anchor),
            'targets_same': summary['targets'] == original['targets'],
            'targets_added': moved, 'targets_dropped': dropped,
            'targets_same_count': len(same),
            'segment_same': summary['segment'] == original['segment'],
        }

    return {
        'episode_id': run['episode_id'], 'attempt': run['attempt'],
        'action': run['spec'].get('action_id'),
        'place': run['spec'].get('place_id'),
        'seed': run['spec'].get('tsp_seed'),
        'missing_in_topic': missing_in_topic,
        'extra_in_topic': extra_in_topic,
        'original': original,
        'reproduction': reproduction,
        'sync_executed_ref': sync_same_ref,
        'sync_laser_ref': sync_laser_ref,
        'topic_laser_ref': topic_laser_ref,
        'geometry': geometry,
        'reference_base': reference,
        'reference_laser': reference_laser,
        'reference_source': frozen.get('reference_source'),
        'reference_provenance': 'DRIVER_TF_MAP_BASE_AT_HISTORY_STOP',
    }


def _node_distance(nodes, first_id, second_id):
    lookup = {node['id']: node for node in nodes}
    if first_id not in lookup or second_id not in lookup:
        return None
    first, second = lookup[first_id], lookup[second_id]
    return math.hypot(first['x'] - second['x'], first['y'] - second['y'])


def run(doc80_root=common.DOC80):
    rows = []
    audit = []
    reproduction_failures = []
    for run_ in common.valid_runs():
        entry = audit_run(run_)
        if entry is None:
            continue
        audit.append(entry)
        original = entry['original']
        reproduction = entry['reproduction']
        if (reproduction['anchor'] != original['anchor']
                or reproduction['targets'] != original['targets']
                or reproduction['segment'] != original['segment']):
            reproduction_failures.append(entry['episode_id'])
        rows.append({
            'episode_id': entry['episode_id'], 'attempt': entry['attempt'],
            'place': entry['place'], 'action': entry['action'],
            'missing_in_topic': json.dumps(entry['missing_in_topic']),
            'anchor_original': original['anchor'],
            'anchor_sync_same_ref': entry['sync_executed_ref']['anchor'],
            'anchor_sync_laser_ref': entry['sync_laser_ref']['anchor'],
            'targets_original': json.dumps(original['targets']),
            'targets_sync_same_ref': json.dumps(entry['sync_executed_ref']['targets']),
            'targets_sync_laser_ref': json.dumps(entry['sync_laser_ref']['targets']),
            'targets_topic_laser_ref': json.dumps(entry['topic_laser_ref']['targets']),
            'targets_identical_all_definitions': (
                entry['reproduction']['targets'] == original['targets']
                and entry['sync_executed_ref']['targets'] == original['targets']
                and entry['sync_laser_ref']['targets'] == original['targets']),
            'anchor_identical_all_definitions': (
                entry['reproduction']['anchor'] == original['anchor']
                and entry['sync_executed_ref']['anchor'] == original['anchor']
                and entry['sync_laser_ref']['anchor'] == original['anchor']),
            'anchor_distance_executed_ref_m': entry['sync_executed_ref']['anchor_distance_m'],
            'anchor_heading_error_executed_ref_rad': entry['sync_executed_ref']['anchor_heading_error_rad'],
            'all_checks_passed_sync_same_ref': entry['sync_executed_ref']['passed'],
            'all_checks_passed_sync_laser_ref': entry['sync_laser_ref']['passed'],
        })
    payload = {
        'role': 'target freeze topic-vs-sync and lever-arm sensitivity',
        'estimand_rule': ('ORIGINAL_FROZEN_TARGET_ESTIMAND kept; SYNC_REFREEZE '
                          'is sensitivity only (never substituted)'),
        'runs': len(rows),
        'reproduction_failures': reproduction_failures,
        'sensitivity': [{
            'episode_id': entry['episode_id'],
            'geometry': entry['geometry'],
        } for entry in audit],
        'conclusion': {
            'targets_changed_by_sync_or_frames': any(
                not row['targets_identical_all_definitions'] for row in rows),
            'anchor_changed': any(
                not row['anchor_identical_all_definitions'] for row in rows),
        },
    }
    common.write_csv(Path(doc80_root) / 'audit' / 'target_freeze_consistency.csv', rows)
    common.write_json(Path(doc80_root) / 'audit' / 'target_freeze_sensitivity.json',
                      payload)
    return {'payload': payload, 'rows': rows}
