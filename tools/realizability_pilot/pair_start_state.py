#!/usr/bin/python3
"""Descriptive diagnostic: how well were the arms of a seed pair matched?

The matched-pair blocks only mean something when both arms of a seed enter the
probe from the same state.  This module does not gate anything - the
pre-registered `preprobe_gate` in `n0_analysis.py` does that - it only reports,
per seed pair, the measured deviation of the pre-probe start state so that a
reader can see whether a paired difference is even attributable to the
instrument.

Everything here is read from artifacts that are written *before* the probe
phase opens (`preprobe_graph_signature.json`), so it cannot contain any probe
outcome.
"""

import argparse
import json
import math
from pathlib import Path

#: fields copied verbatim from the pre-probe signature of every arm
SCALAR_FIELDS = (
    'node_count',
    'edge_count',
    'corrected_path_length_m',
    'sim_time',
    'route_start_node_count',
    'target_segment_size',
)

#: list fields compared element-wise
VECTOR_FIELDS = ('robot_gt_pose_before_probe',)


def _load_signature(attempt_dir):
    path = Path(attempt_dir) / 'preprobe_graph_signature.json'
    if not path.is_file():
        return None
    with open(path) as stream:
        return json.load(stream)


def _pose_difference(pose_a, pose_b):
    """Euclidean distance between two ``stamp,x,y,theta`` records."""
    if not pose_a or not pose_b:
        return None
    dx = float(pose_a[1]) - float(pose_b[1])
    dy = float(pose_a[2]) - float(pose_b[2])
    return math.hypot(dx, dy)


def collect_pairs(suite_dir):
    """Every seed pair in the suite, with both arms' pre-probe start state."""
    suite_dir = Path(suite_dir)
    with open(suite_dir / 'suite_state.json') as stream:
        state = json.load(stream)
    signature_by_episode = {}
    for episode in state['episodes']:
        attempts = episode.get('attempts') or []
        if not attempts:
            continue
        run_dir = attempts[-1].get('run_dir')
        attempt_dir = Path(run_dir) if run_dir else None
        if attempt_dir is None:
            attempt_dir = (suite_dir / 'episodes' / episode['episode_id']
                           / 'attempt_{:02d}'.format(len(attempts)))
        if not attempt_dir.is_absolute():
            attempt_dir = suite_dir / attempt_dir
        signature = _load_signature(attempt_dir)
        if signature is None:
            continue
        signature_by_episode[episode['episode_id']] = signature

    blocks = {}
    for episode_id, signature in signature_by_episode.items():
        block_id = signature.get('block_id') or episode_id
        blocks.setdefault(block_id, []).append((episode_id, signature))

    pairs = []
    for block_id in sorted(blocks):
        arms = sorted(blocks[block_id], key=lambda item: item[0])
        if len(arms) != 2:
            entry = {
                'block_id': block_id,
                'complete': False,
                'arms': [episode_id for episode_id, _ in arms],
            }
            pairs.append(entry)
            continue
        (arm_a, signature_a), (arm_b, signature_b) = arms
        entry = {
            'block_id': block_id,
            'complete': True,
            'arms': [arm_a, arm_b],
            'values': {},
            'deviations': {},
        }
        for field in SCALAR_FIELDS:
            value_a = signature_a.get(field)
            value_b = signature_b.get(field)
            entry['values'][field] = {'a': value_a, 'b': value_b}
            if isinstance(value_a, (int, float)) \
                    and isinstance(value_b, (int, float)):
                entry['deviations'][field] = abs(value_a - value_b)
        for field in VECTOR_FIELDS:
            difference = _pose_difference(signature_a.get(field),
                                          signature_b.get(field))
            entry['values'][field] = {'a': signature_a.get(field),
                                      'b': signature_b.get(field)}
            if difference is not None:
                entry['deviations'][field + '_distance_m'] = difference
        entry['diagnostics_enabled'] = {
            arm: signature.get('diagnostics_enabled')
            for arm, signature in arms}
        entry['provenance_enabled'] = {
            arm: signature.get('provenance_enabled')
            for arm, signature in arms}
        pairs.append(entry)
    return {
        'suite_dir': str(suite_dir),
        'pair_count': len(pairs),
        'pairs': pairs,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite-dir', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    payload = collect_pairs(args.suite_dir)
    with open(args.out, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    for pair in payload['pairs']:
        print(pair['block_id'], json.dumps(pair.get('deviations', {}),
                                           sort_keys=True))


if __name__ == '__main__':
    main()
