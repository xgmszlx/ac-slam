#!/usr/bin/python3
"""Generate a frozen controlled-pilot episode queue."""

import argparse
import datetime
import json
from pathlib import Path

from protocol import PROTOCOL_VERSION, episode_specs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=('preflight', 'screening'), default='preflight')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--target', action='append', dest='targets')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit('--repeats must be >= 1')
    episodes = episode_specs(args.profile, args.repeats, args.targets)
    payload = {
        'protocol_version': PROTOCOL_VERSION,
        'profile': args.profile,
        'repeats': args.repeats,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'episodes': episodes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit('refusing to overwrite {}'.format(args.output))
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    print('wrote {} episodes to {}'.format(len(episodes), args.output))


if __name__ == '__main__':
    main()
