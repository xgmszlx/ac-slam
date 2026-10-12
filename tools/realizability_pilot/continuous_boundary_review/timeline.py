#!/usr/bin/python3
"""Stage timeline, motion windows and the keyframe publication audit.

The doc-77 analysis attributed states to stages through the *snapshot* pair
difference and matched states to key scans by nearest position.  This module
builds the timeline from recorded evidence instead:

* stage scan windows come from ``episode_result.json`` (same indices as the
  frozen analysis, so the review is comparable);
* motion ends inside a stage come from the recorded odometric stream;
* keyframe identity comes from the mapper accept log
  (``state_id``/``unique_id``/``sim_time``) parsed by :mod:`evidence`;
* publication status of every keyframe comes from the four graph snapshots and
  their recorded content times (``graph_boundary.graph_received_ros_time``).
"""

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import evidence as ev  # noqa: E402

#: A scan is "in motion" when odometry moved at least this much since the
#: previous scan (translation meters / heading radians).
MOTION_TRANSLATION_M = 0.005
MOTION_HEADING_RAD = 0.01
#: Half window used to describe odometry speed at a state's accept time.
SPEED_HALF_WINDOW_S = 0.5


def phase_windows(result, scans):
    """Scan-index windows of the four phases, plus their time span."""
    marks = result['phase_scan_marks']
    action_start = int(result['action_start_scan_index'])
    frames = int(result['action_frames_target'])
    windows = {
        'history': (0, int(marks['history_end_scan'])),
        'return': (int(marks['return_start_scan']), action_start),
        'action': (action_start, action_start + frames),
        'tail': (action_start + frames, None),
    }
    stamps = [record['stamp'] for record in scans]
    payload = {}
    for name, (start, end) in windows.items():
        subset = [record for record in scans
                  if record['index'] >= start and (end is None or record['index'] < end)]
        payload[name] = {
            'scan_start': start,
            'scan_end': end,
            'time_start': subset[0]['stamp'] if subset else None,
            'time_end': subset[-1]['stamp'] if subset else None,
            'scan_count': len(subset),
        }
    payload['_stamps'] = stamps
    return payload


def motion_flags(scans):
    """Per-scan boolean: did odometry move since the previous usable sample?"""
    flags = [False] * len(scans)
    previous = None
    for index, record in enumerate(scans):
        pose = record.get('odom_base')
        if pose is None:
            continue
        if previous is not None:
            moved = (abs(pose[0] - previous[0]) >= MOTION_TRANSLATION_M
                     or abs(ev.wrap_angle(pose[2] - previous[2])) >= MOTION_HEADING_RAD)
            flags[index] = moved
        previous = pose
    return flags


def last_motion_scan(scans, flags, window):
    """Index (into ``scans``) of the last moving scan inside ``window``."""
    start, end = window
    last = None
    for index, record in enumerate(scans):
        if record['index'] < start or (end is not None and record['index'] >= end):
            continue
        if flags[index]:
            last = index
    return last


def stage_motion(scans, flags, window):
    """Motion summary of one stage: motion end index/time and remainder."""
    start, end = window
    subset = [(index, record) for index, record in enumerate(scans)
              if record['index'] >= start and (end is None or record['index'] < end)]
    if not subset:
        return {'scan_count': 0, 'motion_end_index': None, 'motion_end_time': None,
                'collect_end_index': None, 'collect_end_time': None,
                'motion_scan_count': 0, 'static_scan_count': 0}
    last_motion = last_motion_scan(scans, flags, window)
    return {
        'scan_count': len(subset),
        'motion_end_index': (scans[last_motion]['index'] if last_motion is not None
                             else None),
        'motion_end_time': (scans[last_motion]['stamp'] if last_motion is not None
                            else None),
        'collect_end_index': subset[-1][1]['index'],
        'collect_end_time': subset[-1][1]['stamp'],
        'motion_scan_count': sum(1 for index, _ in subset if flags[index]),
        'static_scan_count': sum(1 for index, _ in subset if not flags[index]),
    }


def odom_samples(scans):
    """Pose stream (stamp, x, y, theta) built from the odometric scan track."""
    return [{'stamp': record['stamp'], 'x': record['odom_base'][0],
             'y': record['odom_base'][1], 'theta': record['odom_base'][2]}
            for record in scans if record.get('odom_base') is not None]


def odom_speed(samples, stamp):
    """Odometry displacement per second in a +-0.5 s window around ``stamp``."""
    before = ev.pose_at(samples, stamp - SPEED_HALF_WINDOW_S, tolerance=0.2)
    after = ev.pose_at(samples, stamp + SPEED_HALF_WINDOW_S, tolerance=0.2)
    if before[0] is None or after[0] is None:
        return None
    distance = ((after[0][0] - before[0][0]) ** 2
                + (after[0][1] - before[0][1]) ** 2) ** 0.5
    return distance / (2.0 * SPEED_HALF_WINDOW_S)


def build_state_timeline(run):
    """Per accepted keyframe: accept time, stage, motion and publication class.

    Publication classes
    -------------------
    ``PUBLISHED_TIMELY``      first snapshot at which the state appears is the
                              first snapshot whose recorded graph content time
                              is at or after the accept time;
    ``DEFERRED_RECOVERABLE``  appears in a *later* snapshot than that (its edges
                              land in a later stage difference, but the state -
                              and therefore the chain edge - is still recorded);
    ``NEVER_PUBLISHED_SUFFIX`` absent from all snapshots and part of the
                              trailing contiguous id suffix (no loop event after
                              the last content time in such runs);
    ``NEVER_PUBLISHED_GAP``   absent from all snapshots but *not* in the suffix
                              (would break the subtree argument; must be empty).
    """
    scans = run['scans']
    flags = motion_flags(scans)
    odom = odom_samples(scans)
    windows = phase_windows(run['result'], scans)
    stage_of_index = {}
    for name in ('history', 'return', 'action', 'tail'):
        start, end = windows[name]['scan_start'], windows[name]['scan_end']
        for record in scans:
            if record['index'] >= start and (end is None or record['index'] < end):
                stage_of_index[record['index']] = name
    stamps = [record['stamp'] for record in scans]
    content_times = [run['content_time'][name] for name in ev.SNAPSHOTS]
    node_ids = {
        name: {int(node['state_id']) for node in (run['snapshots'][name] or {'nodes': []})['nodes']}
        for name in ev.SNAPSHOTS
    }
    accepted_ids = [item['state_id'] for item in run['accepts']]
    missing_ids = set(accepted_ids) - node_ids['G_final']
    suffix_start = None
    if missing_ids:
        ordered = sorted(accepted_ids)
        tail = []
        for state in reversed(ordered):
            if state in missing_ids:
                tail.append(state)
            else:
                break
        suffix_start = min(tail) if tail and set(tail) == missing_ids else None
    timeline = []
    for item in run['accepts']:
        stamp = item['sim_time']
        scan_index = ev.nearest_index(stamps, stamp) if stamps else None
        stage_by_time = stage_of_index.get(scans[scan_index]['index']) if scan_index is not None else None
        expected = None
        for position, content in enumerate(content_times):
            if content is not None and stamp <= content:
                expected = position
                break
        appearance = None
        for position, name in enumerate(ev.SNAPSHOTS):
            if item['state_id'] in node_ids[name]:
                appearance = position
                break
        if appearance is None:
            if suffix_start is not None and item['state_id'] in missing_ids:
                cls = 'NEVER_PUBLISHED_SUFFIX'
            else:
                cls = 'NEVER_PUBLISHED_GAP'
        elif expected is None:
            cls = 'DEFERRED_RECOVERABLE' if appearance is not None else 'NEVER_PUBLISHED_GAP'
            # expected is None only when the accept time is after the last
            # recorded content time; if the state *is* present, the publisher
            # simply never delivered a later message and the state itself is
            # recorded, so it still counts as recoverable.
        elif appearance <= expected:
            cls = 'PUBLISHED_TIMELY'
        else:
            cls = 'DEFERRED_RECOVERABLE'
        timeline.append({
            'state_id': item['state_id'],
            'unique_id': item['unique_id'],
            'sim_time': stamp,
            'scan_index': (scans[scan_index]['index'] if scan_index is not None else None),
            'stage_by_time': stage_by_time,
            'stage_by_content': expected,
            'first_snapshot': (ev.SNAPSHOTS[appearance] if appearance is not None else None),
            'first_snapshot_index': appearance,
            'speed_mps': odom_speed(odom, stamp),
            'class': cls,
        })
    return {
        'timeline': timeline,
        'windows': windows,
        'motion': {
            'return': stage_motion(scans, flags, (
                windows['return']['scan_start'], windows['return']['scan_end'])),
            'action': stage_motion(scans, flags, (
                windows['action']['scan_start'], windows['action']['scan_end'])),
            'tail': stage_motion(scans, flags, (
                windows['tail']['scan_start'], None)),
        },
        'missing_ids': sorted(missing_ids),
        'suffix_start': suffix_start,
        'node_ids': node_ids,
        'content_times': content_times,
    }


def boundary_rows(run, timeline):
    """One audit row per snapshot boundary (the four events of the attachment)."""
    rows = []
    accepts = run['accepts']
    for position, name in enumerate(ev.SNAPSHOTS):
        content = run['content_time'][name]
        snap_time = run['snapshot_time'][name]
        boundary = run['boundary'][name]
        node_ids = timeline['node_ids'][name]
        accepted_ids = [item['state_id'] for item in accepts]
        states_after_content = [item for item in accepts
                                if content is not None and item['sim_time'] > content]
        missing_from_snapshot = [state for state in accepted_ids if state not in node_ids]
        rows.append({
            'episode_id': run['episode_id'],
            'round': run['suite_round'],
            'action_id': run['action_id'],
            'place_id': run['place_id'],
            'repeat': run['repeat'],
            'boundary': name,
            'snapshot_time_ros': snap_time,
            'content_time_ros': content,
            'content_lag_s': (None if (snap_time is None or content is None)
                              else round(snap_time - content, 4)),
            'accepted_states': len(accepts),
            'graph_nodes': len(node_ids),
            'graph_edges': len((run['snapshots'][name] or {'edges': []})['edges']),
            'last_accept_sim_time': (round(accepts[-1]['sim_time'], 3) if accepts else None),
            'accepts_after_content': len(states_after_content),
            'states_missing_from_snapshot': len(missing_from_snapshot),
            'quiescence_satisfied': bool(boundary.get('satisfied')),
            'quiescence_s': boundary.get('quiescence_s'),
            'full_graph_messages': boundary.get('full_graph_messages'),
            'keyscan_publications': boundary.get('keyscan_publications'),
            'keyscan_check_informative': False,  # driver stores no state_id
            'provenance_file': bool(run['files'].get('provenance')),
            'pose_graph_dump_file': bool(run['files'].get('pose_graph_dump')),
        })
    return rows


def recoverability_rows(run, timeline):
    """Rows for every accepted state that was not published at its boundary."""
    rows = []
    for item in timeline['timeline']:
        if item['class'] == 'PUBLISHED_TIMELY':
            continue
        rows.append({
            'episode_id': run['episode_id'],
            'round': run['suite_round'],
            'action_id': run['action_id'],
            'place_id': run['place_id'],
            'state_id': item['state_id'],
            'unique_id': item['unique_id'],
            'sim_time': round(item['sim_time'], 3),
            'stage_by_time': item['stage_by_time'],
            'first_snapshot': item['first_snapshot'],
            'recoverability_class': item['class'],
            'recoverable_offline': item['class'] == 'DEFERRED_RECOVERABLE',
            'edges_recorded': item['class'] == 'DEFERRED_RECOVERABLE',
            'speed_at_accept_mps': (None if item['speed_mps'] is None
                                    else round(item['speed_mps'], 4)),
            'in_suffix': item['class'] == 'NEVER_PUBLISHED_SUFFIX',
            'diagnostic_bound_required': item['class'].startswith('NEVER_PUBLISHED'),
        })
    return rows
