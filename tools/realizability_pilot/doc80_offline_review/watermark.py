#!/usr/bin/python3
"""Doc-80 sections 4.1 + 4.2: boundary watermark sensitivity and provenance
identity robustness.

Question 4.1: the watermark only asserts that the driver's last observed scan
was processed before the export; the synchronous dump may contain *further*
scans accepted during the dwell (or beyond).  We list exactly which nodes in
each stage graph were accepted after the watermark stamp and classify whether
they belong to the same dwell or to the next motion stage.

Question 4.2: the frozen analysis indexes edges by (source_state_id,
target_state_id).  We check whether the provenance stream ever contains
duplicate endpoint keys (which that dictionary would silently collapse) and
verify that every synchronous graph edge has exactly one creation record.
"""

import json
from pathlib import Path

from . import common


def boundary_sensitivity(doc80_root=common.DOC80):
    import csv
    rows = []
    for run in common.valid_runs():
        result = run['result']
        stage_windows = common.windows(result)
        scans = common.jsonl(run['attempt_dir'] / 'scan_stream.jsonl')
        accepts = {item['state_id']: item for item in common.accepts(run)}
        boundaries = run['boundary_manifest']
        if stage_windows is None:
            continue
        # phase end timestamps (last scan of the motion leg)
        phase_end = {
            'G_before_return': scans[stage_windows['history'][1] - 1]['stamp'],
            'G_arrival': scans[stage_windows['action'][0] - 1]['stamp'],
            'G_action_done': scans[stage_windows['action'][1] - 1]['stamp'],
            'G_final': scans[-1]['stamp'],
        }
        stage_of_boundary = {'G_before_return': 'before_return', 'G_arrival': 'arrival',
                             'G_action_done': 'action_done', 'G_final': 'final'}
        for boundary, entry in boundaries.items():
            if boundary == 'mode' or not isinstance(entry, dict):
                continue
            stem = {'G_before_return': 'before_return', 'G_arrival': 'arrival',
                    'G_action_done': 'action_done', 'G_final': 'final'}[boundary]
            graph = common.sync_graph(run, stem)
            watermark = (entry.get('watermark') or {})
            watermark_stamp = float(watermark.get('stamp', 0.0)) \
                if watermark.get('stamp') is not None else None
            beyond = []
            if graph is not None and watermark_stamp is not None:
                for node in graph['nodes']:
                    item = accepts.get(node['state_id'])
                    if item is None:
                        continue
                    if item['sim_time'] > watermark_stamp + 1e-9:
                        phase_stage = common.stage_of_stamp(
                            item['sim_time'], scans, stage_windows)
                        beyond.append({
                            'state_id': node['state_id'],
                            'sim_time': item['sim_time'],
                            'delta_s': item['sim_time'] - watermark_stamp,
                            'stage': phase_stage,
                        })
            classification = 'NONE'
            if beyond:
                same_dwell = [item for item in beyond
                              if item['stage'] == stage_of_boundary[boundary]
                              or item['sim_time'] <= phase_end.get(boundary, -1)]
                next_stage = [item for item in beyond
                              if item not in same_dwell]
                if next_stage:
                    classification = 'NEXT_STAGE_PRESENT'
                elif same_dwell:
                    classification = 'DWELL_ONLY'
            rows.append({
                'episode_id': run['episode_id'], 'attempt': run['attempt'],
                'boundary': boundary,
                'watermark_stamp': watermark_stamp,
                'watermark_seq': watermark.get('seq'),
                'last_mapper_stamp': (entry.get('telemetry_before_export') or {}).get(
                    'last_native_scan_stamp'),
                'latest_node_state_id': graph['nodes'][-1]['state_id'] if graph else None,
                'latest_node_accept_sim_time': (
                    accepts.get(graph['nodes'][-1]['state_id'], {}).get('sim_time')
                    if graph else None),
                'phase_end_stamp': phase_end.get(boundary),
                'nodes_beyond_watermark': len(beyond),
                'max_delta_beyond_watermark_s': (
                    max(item['delta_s'] for item in beyond) if beyond else 0.0),
                'classification': classification,
                'beyond_detail': json.dumps(beyond[:8]),
            })
    common.write_csv(Path(doc80_root) / 'audit' /
                     'boundary_watermark_sensitivity.csv', rows)
    return rows


def provenance_identity(doc80_root=common.DOC80):
    rows = []
    for run in common.valid_runs():
        records = common.jsonl(run['attempt_dir'] / 'karto_edge_provenance.jsonl')
        created = [record for record in records
                   if record.get('record_type') == 'constraint_created']
        keys = {}
        duplicates = []
        for record in created:
            key = (int(record['source_state_id']), int(record['target_state_id']))
            keys.setdefault(key, []).append(record)
        for key, items in keys.items():
            if len(items) > 1:
                duplicates.append({'key': list(key), 'count': len(items),
                                   'sequences': [item.get('creation_sequence')
                                                 for item in items]})
        # graph-edge coverage per stage
        coverage = {}
        for stem in common.STAGES:
            graph = common.sync_graph(run, stem)
            if graph is None:
                continue
            matched = 0
            unmatched = []
            for edge in graph['edges']:
                key = (edge['source_state_id'], edge['target_state_id'])
                items = keys.get(key) or keys.get((key[1], key[0]))
                if items:
                    matched += 1
                else:
                    unmatched.append(list(key))
            coverage[stem] = {'edges': len(graph['edges']), 'matched': matched,
                              'unmatched': unmatched[:6],
                              'unmatched_count': len(unmatched)}
        # identity robustness using unique ids as well
        rows.append({
            'episode_id': run['episode_id'], 'attempt': run['attempt'],
            'records': len(records), 'constraint_records': len(created),
            'distinct_endpoint_keys': len(keys),
            'duplicate_endpoint_keys': len(duplicates),
            'duplicate_detail': json.dumps(duplicates[:5]),
            'coverage_final_edges': coverage.get('final', {}).get('edges'),
            'coverage_final_matched': coverage.get('final', {}).get('matched'),
            'coverage_final_unmatched': coverage.get('final', {}).get('unmatched_count'),
            'coverage_detail': json.dumps(coverage),
        })
    common.write_csv(Path(doc80_root) / 'audit' /
                     'provenance_identity_audit.csv', rows)
    return rows


if __name__ == '__main__':
    boundary_sensitivity()
    provenance_identity()
