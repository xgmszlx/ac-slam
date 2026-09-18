#!/usr/bin/python3
"""Stable content hashes for common-prefix Karto graphs and input streams."""

import argparse
import hashlib
import json
from pathlib import Path


def canonical_graph(graph, target_ids):
    nodes = sorted(({
        'state_id': int(node['state_id']),
        'unique_id': int(node['unique_id']),
        'x': float(node['x']), 'y': float(node['y']),
        'theta': float(node['theta']),
    } for node in graph['nodes']), key=lambda row: row['state_id'])
    edges = sorted(({
        'index': int(edge['index']),
        'source_state_id': int(edge['source_state_id']),
        'target_state_id': int(edge['target_state_id']),
        'source_unique_id': int(edge['source_unique_id']),
        'target_unique_id': int(edge['target_unique_id']),
        'measurement': {
            key: float(edge['measurement'][key])
            for key in ('dx', 'dy', 'dtheta')},
        'covariance_3x3': [[float(value) for value in row]
                           for row in edge['covariance_3x3']],
    } for edge in graph['edges']), key=lambda row: row['index'])
    return {'nodes': nodes, 'edges': edges,
            'target_historical_ids': sorted(int(value) for value in target_ids)}


def content_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def stream_hash(path, limit=None):
    digest = hashlib.sha256()
    count = 0
    with open(path, 'rb') as stream:
        for line in stream:
            if not line.strip():
                continue
            if limit is not None and count >= int(limit):
                break
            digest.update(line)
            count += 1
    return digest.hexdigest(), count


def build_signature(graph, target_ids, stream_path=None, prefix_count=None):
    canonical = canonical_graph(graph, target_ids)
    signature = {
        'signature_version': 'common-prefix-graph-v1',
        'preprobe_graph_hash': content_hash(canonical),
        'node_count': len(canonical['nodes']),
        'edge_count': len(canonical['edges']),
        'node_ids': [node['state_id'] for node in canonical['nodes']],
        'edge_endpoints_in_insertion_order': [
            [edge['source_state_id'], edge['target_state_id']]
            for edge in canonical['edges']],
        'target_historical_ids': canonical['target_historical_ids'],
        'hash_fields': ('sorted state/unique IDs and corrected poses; ordered edge '
                        'IDs/endpoints/relative measurements/covariances; target IDs'),
        'excluded_fields': ['run_id', 'path', 'wall_clock', 'logging_timestamp'],
    }
    if stream_path is not None:
        signature['input_stream_hash'], signature['input_record_count'] = stream_hash(
            stream_path, prefix_count)
    return signature


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--graph', required=True)
    parser.add_argument('--frozen-target', required=True)
    parser.add_argument('--stream')
    parser.add_argument('--prefix-count', type=int)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    with open(args.graph) as stream:
        graph = json.load(stream)
    with open(args.frozen_target) as stream:
        frozen = json.load(stream)
    signature = build_signature(
        graph, frozen['historical_scan_ids'], args.stream, args.prefix_count)
    with open(args.out, 'w') as stream:
        json.dump(signature, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(signature, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
