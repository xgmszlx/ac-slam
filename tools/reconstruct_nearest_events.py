#!/usr/bin/python3

"""Reconstruct the missing Nearest-Frontier event stream from archived logs."""

import argparse
import csv
import json
import re


ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07')
STAMP = re.compile(r',\s*([0-9]+(?:\.[0-9]+)?)\]')


def emit(writer, stamp, event, data):
    payload = dict(data)
    payload['source'] = 'offline_reconstructed_from_roslaunch'
    writer.writerow([f'{stamp:.9f}', event, json.dumps(payload, sort_keys=True)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    args = parser.parse_args()

    lines = []
    with open(args.log, errors='replace') as stream:
        lines = [ANSI.sub('', line) for line in stream]

    events = []
    events.append((args.start, 'HIGH_LEVEL_GOAL', {
        'scope': 'exploration_action',
        'planner': 'NearestFrontierPlanner',
        'vertex': None,
    }))
    previous = []
    for line in lines:
        if 'Really visited vertices:' not in line:
            continue
        match = STAMP.search(line)
        if not match:
            continue
        stamp = float(match.group(1))
        values = [int(value) for value in re.findall(
            r'-?\d+', line.split('Really visited vertices:', 1)[1]
        )]
        if values[:len(previous)] == previous:
            new_values = values[len(previous):]
        else:
            new_values = values
        if stamp >= args.start:
            for vertex in new_values:
                events.append((stamp, 'GOAL_REACHED', {
                    'vertex': vertex,
                    'semantic': 'inferred_from_really_visited_vertices',
                }))
        previous = values
    events.append((args.end, 'GOAL_REACHED', {
        'scope': 'exploration_action',
        'status': 3,
    }))

    with open(args.output, 'w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['timestamp', 'event', 'data'])
        for stamp, event, data in sorted(events, key=lambda item: item[0]):
            emit(writer, stamp, event, data)


if __name__ == '__main__':
    main()
