#!/usr/bin/python3
"""Doc-79 fixed plan: 2 places x 2 actions x 2 runs = 8 episodes, fixed order.

The commanded conditions are copied byte-for-byte from the frozen continuous
revisit suite (``protocol.py`` episode specs of the same place/action/repeat),
so the physical protocol, route geometry, seeds and mapper parameters are the
ones that produced the Doc-77/Doc-78 evidence.  Only the identifiers change and
the two runs of a condition are exact repeats of the same spec.

Run order (frozen in ``protocol/preregistration.json`` before run 1):

    1  B L+   2  B L-   3  C L-   4  C L+
    5  B L-   6  B L+   7  C L+   8  C L-

Runs 1-2 double as the observation-chain qualification pair.
"""

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(THIS_DIR.parent))
# tools/realizability_pilot must be on the path for ``from protocol import ...``
if str(THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(THIS_DIR.parent))
if str(THIS_DIR.parent / 'continuous_revisit') not in sys.path:
    sys.path.insert(0, str(THIS_DIR.parent / 'continuous_revisit'))

from continuous_revisit import protocol as cr  # noqa: E402

PLAN_ORDER = [
    ('place_B', 'L+', 1),
    ('place_B', 'L-', 1),
    ('place_C', 'L-', 1),
    ('place_C', 'L+', 1),
    ('place_B', 'L-', 2),
    ('place_B', 'L+', 2),
    ('place_C', 'L+', 2),
    ('place_C', 'L-', 2),
]

BUDGET_EPISODES = 8


def base_specs():
    """Frozen r1 specs of the four conditions, keyed by (place, action)."""
    table = {}
    for spec in cr.episode_specs():
        if int(spec['repeat']) != 1:
            continue
        if spec['place_id'] not in ('place_B', 'place_C'):
            continue
        table[(spec['place_id'], spec['action_id'])] = spec
    missing = [key for key in (('place_B', 'L+'), ('place_B', 'L-'),
                               ('place_C', 'L+'), ('place_C', 'L-'))
               if key not in table]
    if missing:
        raise RuntimeError('frozen specs missing: {}'.format(missing))
    return table


def doc79_specs():
    """The eight planned episodes in the frozen order."""
    base = base_specs()
    specs = []
    for position, (place, action, run_index) in enumerate(PLAN_ORDER, 1):
        spec = dict(base[(place, action)])
        source = spec['episode_id']
        spec['source_episode_id'] = source
        spec['episode_id'] = 'D79_{}_{}_{}'.format(place.replace('place_', ''),
                                                   action.replace('+', 'plus')
                                                   .replace('-', 'minus'),
                                                   run_index)
        spec['round'] = 'doc79'
        spec['doc79_order'] = position
        spec['doc79_run_index'] = run_index
        spec['sync_export'] = True
        spec['sync_barrier_timeout_s'] = 30.0
        specs.append(spec)
    return specs
