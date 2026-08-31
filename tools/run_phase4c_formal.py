#!/usr/bin/python3
"""Execute the frozen Phase 4C map8/Mexico formal matrix without auto-retry."""

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import run_phase4b_suite as phase4b
from phase4c_formal_common import (
    BASELINE, CONDITIONS, FORMAL_ROOT, MAPS, ORDERS, ROOT,
    materialize_runtime_environment,
)


NAVIGATION = ROOT / 'dependencies' / 'navigation_2d'


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def git_commit(repo):
    return subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True
    ).strip()


def tracked_status(repo):
    return subprocess.check_output(
        ['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'],
        text=True,
    ).strip()


def canonical_hash(value):
    raw = json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


def ensure_protocol():
    path = FORMAL_ROOT / 'protocol_manifest.json'
    if not path.is_file():
        raise phase4b.TechnicalInvalid('formal protocol manifest missing; run preflight')
    manifest = json.loads(path.read_text())
    current = {
        'root': git_commit(ROOT), 'baseline': git_commit(BASELINE),
        'navigation_2d': git_commit(NAVIGATION),
    }
    if manifest.get('commits') != current:
        raise phase4b.TechnicalInvalid(
            'preflight commit mismatch: {} != {}'.format(current, manifest.get('commits'))
        )
    for repo in (ROOT, BASELINE, NAVIGATION):
        status = tracked_status(repo)
        if status:
            raise phase4b.TechnicalInvalid(
                'tracked worktree is dirty in {}:\n{}'.format(repo, status)
            )
    for config in MAPS.values():
        materialize_runtime_environment(config)
    return path, manifest


def formal_selection_record(run_dir):
    tsp = json.loads((run_dir / 'tsp_record.json').read_text())
    loops = json.loads((run_dir / 'loops.json').read_text()).get('loops', [])
    sequence = [int(loop['loop_vertex']) for loop in loops]
    selection = {
        'selected_loop_vertex_sequence': sequence,
        'selection_order': [
            {
                'order': index, 'loop_id': loop.get('loop_id'),
                'loop_vertex': loop.get('loop_vertex'),
                'selection_timestamp': loop.get('planned_start_time'),
            }
            for index, loop in enumerate(loops, start=1)
        ],
        'selection_timestamp': [loop.get('planned_start_time') for loop in loops],
        'initial_tsp_hash': canonical_hash(tsp.get('initial_tsp_path')),
        'full_tsp_hash': canonical_hash(tsp.get('full_tsp_path')),
        'planned_loop_count': len(loops),
        'executed_loop_count': sum(loop.get('actual_start_time') is not None for loop in loops),
        'hash_definition': 'SHA-256 of compact canonical JSON integer path',
    }
    (run_dir / 'selection_sequence.json').write_text(
        json.dumps(selection, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    return selection


def next_attempt(method_dir, retry_allowed):
    attempts = sorted(method_dir.glob('attempt_*')) if method_dir.exists() else []
    if not attempts:
        return 'attempt_01'
    selected = method_dir / 'selected_attempt.json'
    if selected.exists():
        return None
    if not retry_allowed:
        raise phase4b.TechnicalInvalid(
            'preserved incomplete/technical attempt requires explicit retry authorization: {}'.format(
                attempts[-1]
            )
        )
    latest_state = attempts[-1] / 'run_state.json'
    state = json.loads(latest_state.read_text()) if latest_state.is_file() else {}
    if state.get('validity') != 'TECHNICAL_INVALID':
        raise phase4b.TechnicalInvalid(
            'retry forbidden because latest attempt is not TECHNICAL_INVALID: {}'.format(state)
        )
    return 'attempt_{:02d}'.format(len(attempts) + 1)


def selected_attempt(method_dir):
    path = method_dir / 'selected_attempt.json'
    return json.loads(path.read_text()) if path.is_file() else None


def run_cell(map_id, seed, label, env, protocol_path, explore_timeout,
             retry_allowed=False):
    config = MAPS[map_id]
    seed_dir = FORMAL_ROOT / map_id / 'seed_{}'.format(seed)
    seed_dir.mkdir(parents=True, exist_ok=True)
    condition = CONDITIONS[label]
    method_dir = seed_dir / condition['directory']
    existing = selected_attempt(method_dir)
    if existing:
        return {'skipped_completed': True, **existing}
    attempt_name = next_attempt(method_dir, retry_allowed)
    if shutil.disk_usage(str(ROOT)).free < 512 * 1024 ** 2:
        raise phase4b.TechnicalInvalid('less than 512 MiB free disk before formal cell')
    outcome = phase4b.run_one(
        seed, label, condition, seed_dir, env, explore_timeout, protocol_path,
        map_config=config, phase_tag='Phase4C', attempt_name=attempt_name,
    )
    run_dir = method_dir / attempt_name
    selection = formal_selection_record(run_dir)
    selected = {
        'attempt': attempt_name,
        'run_dir': str(run_dir.relative_to(ROOT)),
        'validity': outcome['validity'],
        'experimental_failure_reason': outcome.get('reason'),
        'selected_wall_time_utc': now_utc(),
        'selection_sequence_file': 'selection_sequence.json',
        'planned_loop_count': selection['planned_loop_count'],
        'executed_loop_count': selection['executed_loop_count'],
    }
    method_dir.mkdir(parents=True, exist_ok=True)
    (method_dir / 'selected_attempt.json').write_text(
        json.dumps(selected, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--maps', nargs='+', choices=sorted(MAPS), default=list(MAPS))
    parser.add_argument('--seeds', nargs='+', type=int, default=list(ORDERS))
    parser.add_argument('--explore-timeout', type=int, default=18000)
    parser.add_argument(
        '--allow-technical-retry', action='append', default=[],
        metavar='MAP:SEED:CONDITION',
        help='explicit authorization for one preserved TECHNICAL_INVALID cell only',
    )
    args = parser.parse_args()
    if any(seed not in ORDERS for seed in args.seeds):
        raise SystemExit('seeds must be {}'.format(sorted(ORDERS)))
    retry_cells = set()
    for value in args.allow_technical_retry:
        map_id, seed, label = value.split(':')
        retry_cells.add((map_id, int(seed), label))

    protocol_path, _ = ensure_protocol()
    env = phase4b.activated_environment()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    state_path = FORMAL_ROOT / 'suite_state.json'
    state = json.loads(state_path.read_text()) if state_path.is_file() else {
        'phase': '4C_FORMAL', 'status': 'RUNNING',
        'started_wall_time_utc': now_utc(), 'completed_cells': [],
        'automatic_retry': False,
    }
    state['status'] = 'RUNNING'
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    try:
        for map_id in args.maps:
            for seed in args.seeds:
                for label in ORDERS[seed]:
                    result = run_cell(
                        map_id, seed, label, env, protocol_path,
                        args.explore_timeout,
                        retry_allowed=(map_id, seed, label) in retry_cells,
                    )
                    key = {'map': map_id, 'seed': seed, 'condition': label}
                    state['completed_cells'] = [
                        row for row in state['completed_cells']
                        if any(row.get(field) != value for field, value in key.items())
                    ]
                    state['completed_cells'].append({**key, **result})
                    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
        expected = len(MAPS) * len(ORDERS) * len(CONDITIONS)
        if len(state['completed_cells']) == expected:
            state['status'] = 'COMPLETED'
            state['finished_wall_time_utc'] = now_utc()
    except Exception as exc:
        state.update({
            'status': 'STOPPED_TECHNICAL_FAILURE',
            'reason': '{}: {}'.format(type(exc).__name__, exc),
            'stopped_wall_time_utc': now_utc(),
            'automatic_retry': False,
        })
        raise
    finally:
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
        print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
