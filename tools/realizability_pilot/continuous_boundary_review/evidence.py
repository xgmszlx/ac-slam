#!/usr/bin/python3
"""Evidence loading for the doc-78 boundary / mechanism review.

Everything in this module is *read-only* with respect to the doc-77 suite.  It
extracts, per recorded run:

* the mapper accept log (``PHASE2C_KEYSCAN_ACCEPTED unique_id=.. state_id=..
  sim_time=..``) parsed out of ``rosout.log`` — this is the only artefact that
  carries the explicit ``state_id`` of a keyframe and therefore the only honest
  identity chain ``state_id -> unique_id -> sim time``;
* the key-scan stream, scan stream (light fields only), ground-truth stream and
  loop-event stream written by the driver;
* the four graph snapshots together with the quiescence record the driver
  stored next to each snapshot;
* the launch instrumentation flags actually used (provenance / dump).

The module deliberately avoids the position-nearest matching used by the
doc-77 analysis: identities come from the accept log where possible and every
fallback is flagged so that the review tables can report it.
"""

import json
import math
import re
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
CR_DIR = REPO_ROOT / 'tools' / 'realizability_pilot' / 'continuous_revisit'
import sys  # noqa: E402

if str(CR_DIR) not in sys.path:
    sys.path.insert(0, str(CR_DIR))

import analysis as an  # noqa: E402

SNAPSHOTS = an.SNAPSHOTS
SNAPSHOT_FILES = an.SNAPSHOT_FILES
#: The stage whose *snapshot difference* defines the gain of a name.
STAGE_OF_SNAPSHOT = {
    'G_arrival': 'return',
    'G_action_done': 'action',
    'G_final': 'tail',
}
STAGE_ORDER = ('return', 'action', 'tail')

ACCEPT_RE = re.compile(
    r'PHASE2C_KEYSCAN_ACCEPTED unique_id=(\d+) state_id=(\d+) sim_time=([0-9.]+)')

#: Files the doc-77 launch was *supposed* to produce but the review must verify.
INSTRUMENTATION_FILES = {
    'provenance': 'karto_edge_provenance.jsonl',
    'pose_graph_dump': 'pose_graph_dump.json',
}


def _jsonl(path):
    path = Path(path)
    if not path.is_file():
        return []
    records = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def parse_accepts(rosout_path):
    """Parse ``rosout.log`` into the mapper keyframe accept timeline.

    Returns ``(accepts, meta)`` where ``accepts`` is a list of dicts
    ``{state_id, unique_id, sim_time}`` sorted by ``sim_time`` and ``meta``
    carries ``log_lines`` and ``duplicate_state_ids`` so the caller can prove
    that the identity map is complete and unambiguous.
    """
    path = Path(rosout_path)
    if not path.is_file():
        return [], {'present': False, 'log_lines': 0, 'duplicate_state_ids': []}
    accepts = []
    lines = 0
    with open(path, errors='ignore') as handle:
        for line in handle:
            lines += 1
            match = ACCEPT_RE.search(line)
            if match:
                accepts.append({
                    'unique_id': int(match.group(1)),
                    'state_id': int(match.group(2)),
                    'sim_time': float(match.group(3)),
                })
    accepts.sort(key=lambda item: (item['state_id'], item['sim_time']))
    seen = {}
    duplicates = []
    for item in accepts:
        if item['state_id'] in seen:
            duplicates.append(item['state_id'])
        seen[item['state_id']] = item
    return accepts, {'present': True, 'log_lines': lines,
                     'duplicate_state_ids': sorted(set(duplicates))}


def load_scan_light(path):
    """Scan stream fields needed for motion / ground-truth work (no ranges)."""
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            out.append({
                'index': int(record['index']),
                'stamp': float(record['stamp']),
                'odom_base': record.get('odom_base'),
                'map_base': record.get('map_base'),
                'finite_returns': int(record.get('finite_returns', 0)),
            })
    return out


def load_episode(dirpath):
    """Load one recorded run directory into a plain dictionary."""
    dirpath = Path(dirpath)
    run = {
        'dir': dirpath,
        'spec': an.load_json(dirpath / 'episode_spec.json', {}) or {},
        'result': an.load_json(dirpath / 'episode_result.json', {}) or {},
        'frozen': an.load_json(dirpath / 'frozen_target.json', {}) or {},
        'manifest': an.load_json(dirpath / 'manifest.json', {}) or {},
        'snapshots_raw': {},
        'snapshots': {},
        'boundary': {},
        'content_time': {},
        'snapshot_time': {},
    }
    for name, filename in SNAPSHOT_FILES.items():
        raw = an.load_json(dirpath / filename)
        run['snapshots_raw'][name] = raw
        run['snapshots'][name] = an.snapshot_graph(raw) if raw else None
        boundary = (raw or {}).get('graph_boundary', {})
        run['boundary'][name] = boundary
        content = boundary.get('graph_received_ros_time')
        run['content_time'][name] = None if content is None else float(content)
        snap_time = (raw or {}).get('ros_time')
        run['snapshot_time'][name] = None if snap_time is None else float(snap_time)
    accepts, accept_meta = parse_accepts(dirpath / 'rosout.log')
    run['accepts'] = accepts
    run['accept_meta'] = accept_meta
    run['keyscans'] = _jsonl(dirpath / 'keyscan_stream.jsonl')
    run['loops'] = _jsonl(dirpath / 'loop_events.jsonl')
    run['gt'] = _jsonl(dirpath / 'gt_stream.jsonl')
    run['scans'] = load_scan_light(dirpath / 'scan_stream.jsonl')
    run['files'] = {
        'rosout': (dirpath / 'rosout.log').is_file(),
        'scan_stream': (dirpath / 'scan_stream.jsonl').is_file(),
        'keyscan_stream': (dirpath / 'keyscan_stream.jsonl').is_file(),
        'gt_stream': (dirpath / 'gt_stream.jsonl').is_file(),
        'loop_events': (dirpath / 'loop_events.jsonl').is_file(),
    }
    for key, filename in INSTRUMENTATION_FILES.items():
        run['files'][key] = (dirpath / filename).is_file()
    run['episode_id'] = run['spec'].get('episode_id', dirpath.parent.name)
    run['round'] = run['spec'].get('round', 'main')
    run['repeatability_of'] = run['spec'].get('repeatability_of')
    run['replay_index'] = run['spec'].get('replay_index')
    run['action_id'] = run['spec'].get('action_id')
    run['place_id'] = run['spec'].get('place_id')
    run['repeat'] = run['spec'].get('repeat')
    run['group_id'] = run['spec'].get('group_id')
    return run


def discover_runs(suite_dir, include_repeatability=True):
    """All recorded runs of the suite, one entry per episode (attempt resolved).

    Returns ``(runs, issues)`` where ``issues`` records failed or unusable
    attempts so the review can state exactly which directories were skipped.
    Runs are ordered like the suite: main matrix first, repeatability second.
    """
    suite_dir = Path(suite_dir)
    runs, issues = [], []
    roots = [('main', suite_dir / 'episodes')]
    if include_repeatability:
        roots.append(('repeatability', suite_dir / 'repeatability' / 'episodes'))
    for round_name, root in roots:
        if not root.is_dir():
            continue
        for episode_dir in sorted(root.iterdir()):
            if not episode_dir.is_dir():
                continue
            chosen = None
            for attempt in sorted(episode_dir.iterdir()):
                if not attempt.is_dir() or not attempt.name.startswith('attempt_'):
                    continue
                has_final = (attempt / 'graph_final.json').is_file()
                result = an.load_json(attempt / 'episode_result.json', {}) or {}
                status = result.get('status')
                if has_final and (status in (None, 'SUCCESS', 'OK', 'COMPLETE')
                                  or attempt == sorted(episode_dir.iterdir())[-1]):
                    if chosen is None:
                        chosen = attempt
                else:
                    issues.append({'episode': episode_dir.name,
                                   'attempt': attempt.name, 'status': status,
                                   'reason': 'no graph_final.json' if not has_final
                                             else 'status {}'.format(status)})
            if chosen is None:
                issues.append({'episode': episode_dir.name, 'attempt': None,
                               'status': None, 'reason': 'no usable attempt'})
                continue
            run = load_episode(chosen)
            run['suite_round'] = round_name
            runs.append(run)
    return runs, issues


def nearest_index(stamps, value):
    """Index of the entry of ``stamps`` (sorted) nearest to ``value``."""
    if not stamps:
        return None
    import bisect

    position = bisect.bisect_left(stamps, value)
    if position <= 0:
        return 0
    if position >= len(stamps):
        return len(stamps) - 1
    before, after = stamps[position - 1], stamps[position]
    if abs(before - value) <= abs(after - value):
        return position - 1
    return position


def pose_at(samples, stamp, key='stamp', xyz=('x', 'y', 'theta'), tolerance=0.15):
    """Linear interpolation of a pose stream with a hard tolerance.

    Returns ``(pose, source_stamp, gap)`` or ``(None, None, gap)`` when the
    nearest sample is farther away than ``tolerance`` seconds.  Angle values
    are interpolated through their unwrapped difference.
    """
    if not samples:
        return None, None, None
    stamps = [float(sample[key]) for sample in samples]
    index = nearest_index(stamps, float(stamp))
    gap = abs(stamps[index] - float(stamp))
    if gap > tolerance:
        return None, None, gap
    first = samples[index]
    pose = [float(first[xyz[0]]), float(first[xyz[1]]), float(first[xyz[2]])]
    if index + 1 < len(samples):
        second = samples[index + 1]
        span = float(second[key]) - float(first[key])
        if span > 0.0 and float(stamp) >= float(first[key]):
            ratio = (float(stamp) - float(first[key])) / span
            pose[0] += ratio * (float(second[xyz[0]]) - pose[0])
            pose[1] += ratio * (float(second[xyz[1]]) - pose[1])
            delta = wrap_angle(float(second[xyz[2]]) - pose[2])
            pose[2] = wrap_angle(pose[2] + ratio * delta)
    elif index - 1 >= 0:
        second = samples[index - 1]
        span = float(first[key]) - float(second[key])
        if span > 0.0 and float(stamp) <= float(first[key]):
            ratio = (float(first[key]) - float(stamp)) / span
            pose[0] -= ratio * (float(first[xyz[0]]) - pose[0])
            pose[1] -= ratio * (float(first[xyz[1]]) - pose[1])
            delta = wrap_angle(pose[2] - float(second[xyz[2]]))
            pose[2] = wrap_angle(pose[2] - ratio * delta)
    return pose, float(first[key]), gap


def wrap_angle(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle
