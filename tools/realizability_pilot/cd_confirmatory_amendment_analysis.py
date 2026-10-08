#!/usr/bin/python3
"""Unchanged frozen analysis bound to CD technical amendment 1 outputs."""

import argparse
import json

import cd_confirmatory_analysis as base
import cd_confirmatory_guard as guard
import cd_confirmatory_amendment_protocol as protocol


PHYSICAL_LOCK = protocol.RESULT_ROOT / \
    'collection/PHYSICAL_COLLECTION_LOCK.json'
BACKEND_LOCK = protocol.RESULT_ROOT / \
    'collection/BACKEND_REPLAY_LOCK.json'
DOC_PATH = protocol.ROOT / \
    'docs/research_log/71_context_disentanglement_amendment1.md'


def assert_backend_lock_allows_analysis():
    if not protocol.original_run_audit()['passed']:
        raise RuntimeError('original incomplete run changed after amendment')
    return guard.assert_backend_lock_allows_analysis(
        protocol.PREREGISTRATION_PATH, PHYSICAL_LOCK, BACKEND_LOCK)


def configure_base():
    base.BOOTSTRAP_REPETITIONS = protocol.BOOTSTRAP_REPETITIONS
    base.BOOTSTRAP_SEED = protocol.BOOTSTRAP_SEED
    base.DOC_PATH = DOC_PATH
    base.PREREGISTRATION_PATH = protocol.PREREGISTRATION_PATH
    base.PROTOCOL_ID = protocol.PROTOCOL_ID
    base.RESULT_ROOT = protocol.RESULT_ROOT
    base.ROOT = protocol.ROOT
    base.frozen_blocks = protocol.frozen_blocks
    base.load_json = protocol.load_json
    base.sha256 = protocol.sha256
    base.source_attempt = protocol.source_attempt
    base.assert_backend_lock_allows_analysis = \
        assert_backend_lock_allows_analysis


def analyze():
    configure_base()
    return base.analyze(protocol.RESULT_ROOT)


def write_technical_incomplete(stage, reason):
    configure_base()
    return base.write_technical_incomplete(stage, reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run',))
    args = parser.parse_args()
    if args.command == 'run':
        print(json.dumps(analyze(), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
