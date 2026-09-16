#!/usr/bin/python3
"""Record the real commit layers behind the current pilot checkout."""

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'baseline' / 'Graph-Based_SLAM-Aware_Exploration'
NAV = ROOT / 'dependencies' / 'navigation_2d'

LAYERS = {
    'author_original': '675299330dff0460d42c0ffd87a2f1f7f9f959da',
    'minimal_compatibility_patch': '5a11667',
    'tsp_control': '2cfe168',
    'active_loop_observer': '211642d',
    'diagnostic_config': '547ea24',
    'experimental_method': '7993bf8',
}


def git(*args, cwd):
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True).strip()


def status_summary(cwd):
    tracked = git('status', '--short', '--untracked-files=no', cwd=cwd)
    untracked = git('ls-files', '--others', '--exclude-standard', cwd=cwd)
    return {
        'branch': git('branch', '--show-current', cwd=cwd),
        'tracked_changes': tracked.splitlines() if tracked else [],
        'untracked_file_count': len(untracked.splitlines()) if untracked else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'results' / 'realizability_pilot' /
                        'provenance_audit.json')
    args = parser.parse_args()
    resolved = {}
    for name, revision in LAYERS.items():
        resolved[name] = git('rev-parse', revision, cwd=BASELINE)
    payload = {
        'baseline_head': git('rev-parse', 'HEAD', cwd=BASELINE),
        'baseline_origin_master': git('rev-parse', 'origin/master', cwd=BASELINE),
        'baseline_status': status_summary(BASELINE),
        'navigation_2d_head': git('rev-parse', 'HEAD', cwd=NAV),
        'navigation_2d_origin_main': git('rev-parse', 'origin/main', cwd=NAV),
        'navigation_2d_status': status_summary(NAV),
        'logical_layers': resolved,
        'warning': (
            'The current checkout is an experimental superset. oracle_mode=0 is '
            'default-off compatibility evidence, not a pristine author checkout.'
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
