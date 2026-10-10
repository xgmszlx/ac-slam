#!/usr/bin/python3
"""Print doc-ready summary tables for the continuous revisit round.

Reads only the analysis tables / summary JSON so the printed numbers and the
committed CSV/JSON artefacts never disagree.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import analysis as an  # noqa: E402
import protocol as cr  # noqa: E402


def read_table(path):
    import csv
    path = Path(path)
    if not path.is_file():
        return []
    with path.open() as stream:
        return list(csv.DictReader(stream))


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def describe(values):
    values = [value for value in values if value is not None]
    if not values:
        return {'n': 0}
    return {
        'n': len(values),
        'mean': statistics.mean(values),
        'sd': statistics.pstdev(values) if len(values) > 1 else 0.0,
        'min': min(values),
        'max': max(values),
        'median': statistics.median(values),
        'positive': sum(1 for value in values if value > 1e-12),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite_dir')
    parser.add_argument('--repeatability-dir')
    args = parser.parse_args()
    suite = Path(args.suite_dir)
    summary = an.load_json(suite / 'analysis' / 'summary.json', {})
    rows = read_table(suite / 'analysis' / 'per_episode_metrics.csv')
    if not rows:
        print('no analysis rows yet')
        return

    print('== analysed episodes: {} of planned {}'.format(
        summary.get('episode_count_analysed'),
        summary.get('episode_count_planned')))

    print('\n== stage gains per action (nats)')
    for action in cr.ACTION_IDS:
        arm = [row for row in rows if row['action_id'] == action]
        for key in ('return_gain', 'action_gain', 'tail_gain', 'total_gain'):
            stats = describe([number(row.get(key)) for row in arm])
            if stats['n']:
                print('{:<3} {:<12} n={:<3} mean {:+.5f} sd {:.5f} min {:+.5f} '
                      'max {:+.5f} median {:+.5f} positive {}'.format(
                          action, key, stats['n'], stats['mean'], stats['sd'],
                          stats['min'], stats['max'], stats['median'],
                          stats['positive']))

    print('\n== per place and action (action/return/total gain means)')
    for place in cr.PLACE_IDS:
        for action in cr.ACTION_IDS:
            arm = [row for row in rows
                   if row['place_id'] == place and row['action_id'] == action]
            if not arm:
                continue
            values = {key: describe([number(row.get(key)) for row in arm])
                      for key in ('return_gain', 'action_gain', 'total_gain')}
            rotation = describe([number(row.get('action_measured_rotation_rad'))
                                 for row in arm])
            print('{:<8} {:<3} n={} return {:+.5f} action {:+.5f} total {:+.5f} '
                  'rotation {:.3f} rad'.format(
                      place, action, values['action_gain']['n'],
                      values['return_gain']['mean'], values['action_gain']['mean'],
                      values['total_gain']['mean'], rotation['mean']))

    print('\n== paired differences inside each place/repeat group (action gain)')
    for key in ('L+_L-', 'L+_S1', 'L+_S0', 'S1_S0', 'L-_S0'):
        payload = summary.get('difference_summary', {}).get(key)
        if not payload:
            continue
        values = [value for value in payload['action_gain_values']]
        print('{:<7} groups {} mean {:+.5f} min {:+.5f} max {:+.5f} '
              'positive groups {} of {}'.format(
                  key, payload['groups'], payload['action_gain_mean'],
                  payload['action_gain_min'], payload['action_gain_max'],
                  payload['action_gain_positive_groups'], payload['groups']))

    print('\n== observation geometry and keyframe gate per action')
    for action in cr.ACTION_IDS:
        arm = [row for row in rows if row['action_id'] == action]
        heading = describe([number(row.get('max_heading_deflection_rad')) for row in arm])
        new_heading = describe([number(row.get('new_heading_fraction')) for row in arm])
        keyscans = describe([number(row.get('action_keyscans_created')) for row in arm])
        duration = describe([number(row.get('action_duration_s')) for row in arm])
        print('{:<3} deflection {:.3f} rad | new-heading fraction {:.3f} | '
              'action keyscans {:.2f} | duration {:.1f} s'.format(
                  action, heading['mean'], new_heading['mean'],
                  keyscans['mean'], duration['mean']))

    print('\n== graph vs real target error')
    pairs = summary.get('errors_vs_information', {})
    for stage in ('return', 'action'):
        payload = pairs.get(stage)
        if payload:
            print('{:<7} samples {} gain mean {:+.5f} error delta mean {:+.5f} m '
                  'pearson r {}'.format(
                      stage, payload['samples'], payload['gain_mean'],
                      payload['error_delta_mean_m'], payload['pearson_r']))

    print('\n== edge accounting per action (mean added edges / loop edges)')
    for action in cr.ACTION_IDS:
        arm = [row for row in rows if row['action_id'] == action]
        for phase in ('return', 'action', 'tail'):
            added = describe([number(row.get('{}_edges_added'.format(phase)))
                              for row in arm])
            loops = describe([number(row.get('{}_loop_edges_added'.format(phase)))
                              for row in arm])
            print('{:<3} {:<7} edges {:.2f} (loop {:.2f})'.format(
                action, phase, added['mean'], loops['mean']))

    print('\n== sensitivity check (synthetic target edge)')
    sensitivity = [entry.get('added_edge_J_T_gain')
                   for entry in summary.get('measurement_sensitivity', [])]
    stats = describe(sensitivity)
    print('n={} mean {:+.5f} min {:+.5f} max {:+.5f} all positive {}'.format(
        stats['n'], stats['mean'], stats['min'], stats['max'],
        stats['positive'] == stats['n']))

    if args.repeatability_dir:
        repeat_dir = Path(args.repeatability_dir)
        repeat_summary = an.load_json(repeat_dir / 'analysis' / 'summary.json', {})
        repeat_rows = read_table(repeat_dir / 'analysis' / 'per_episode_metrics.csv')
        print('\n== repeatability (same configuration re-executed)')
        groups = {}
        for row in repeat_rows:
            config = (row['place_id'], row['action_id'])
            groups.setdefault(config, []).append(row)
        for (place, action), arms in sorted(groups.items()):
            gains = [number(row.get('action_gain')) for row in arms]
            spreads = describe(gains)
            main = [number(row.get('action_gain')) for row in rows
                    if row['place_id'] == place and row['action_id'] == action]
            main_stats = describe(main)
            print('{:<8} {:<3} repeats {} action_gain mean {:+.5f} sd {:.5f} | '
                  'main-matrix mean {:+.5f} sd {:.5f}'.format(
                      place, action, spreads['n'], spreads['mean'], spreads['sd'],
                      main_stats['mean'], main_stats['sd']))
        combined = []
        for (place, action), arms in groups.items():
            values = [number(row.get('action_gain')) for row in arms]
            values += [number(row.get('action_gain')) for row in rows
                       if row['place_id'] == place and row['action_id'] == action]
            values = [value for value in values if value is not None]
            if len(values) > 1:
                combined.append(statistics.pstdev(values))
        if combined:
            print('pooled within-configuration sd (action_gain): {:.5f} nats'.format(
                statistics.mean(combined)))
        print('repeatability status:', repeat_summary.get('episode_count_analysed'),
              'episodes analysed')


if __name__ == '__main__':
    main()
