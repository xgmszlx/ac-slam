#!/usr/bin/python3
"""Post-analysis semantic correction for explicit TRY_CLOSE_LOOP labels.

The frozen diagnostic analysis used substring matching, which incorrectly
classified ADD_EDGES_BEFORE_TRY_CLOSE_LOOP as an explicit loop-closure edge.
This audit is deliberately separate from the preregistered primary analysis:
it changes no graph, estimand, contrast, threshold, or decision label.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from controlled_branch_suite import atomic_json
from v13c_posthoc_b_protocol import RESULT_ROOT


EXPLICIT_TOKEN = 'TRY_CLOSE_LOOP'
FIELDS = ('creation_provenance', 'creation_stage', 'matcher_type')


def is_explicit_try_close_loop(row):
    """Require an exact instrumentation token, never a substring."""
    return any(row.get(field) == EXPLICIT_TOKEN for field in FIELDS)


def audit_mode(root, mode):
    path = Path(root) / 'analysis' / mode / 'constraint_mechanism.csv'
    with open(path, newline='') as stream:
        rows = list(csv.DictReader(stream))
    old_positive = sum(
        str(row.get('explicit_try_close_loop', '')).lower() == 'true'
        for row in rows)
    corrected = [row for row in rows if is_explicit_try_close_loop(row)]
    triples = Counter(tuple(row.get(field) or 'UNKNOWN' for field in FIELDS)
                      for row in rows)
    return {
        'constraint_rows': len(rows),
        'frozen_substring_classifier_positive': old_positive,
        'corrected_exact_classifier_positive': len(corrected),
        'corrected_verdict': (
            'EXPLICIT_TRY_CLOSE_LOOP_OBSERVED' if corrected else
            'NO_EXPLICIT_TRY_CLOSE_LOOP_OBSERVED'),
        'observed_provenance_stage_matcher_combinations': [
            {
                'creation_provenance': triple[0],
                'creation_stage': triple[1],
                'matcher_type': triple[2],
                'count': count,
            }
            for triple, count in sorted(triples.items())
        ],
    }


def run(root=RESULT_ROOT):
    root = Path(root)
    modes = {mode: audit_mode(root, mode) for mode in ('FULL', 'MATCHED')}
    payload = {
        'status': 'POST_ANALYSIS_MECHANISM_CLASSIFIER_CORRECTED',
        'scope': 'explicit TRY_CLOSE_LOOP semantic classification only',
        'cause': (
            'Frozen analysis used substring matching and therefore treated '
            'ADD_EDGES_BEFORE_TRY_CLOSE_LOOP as TRY_CLOSE_LOOP.'),
        'exact_rule': (
            'creation_provenance, creation_stage, or matcher_type must equal '
            'TRY_CLOSE_LOOP exactly'),
        'primary_estimand_changed': False,
        'contrasts_changed': False,
        'diagnostic_decision_changed': False,
        'modes': modes,
    }
    atomic_json(
        root / 'analysis/mechanism_classifier_correction.json', payload)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=RESULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(run(args.root), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
