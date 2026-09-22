#!/usr/bin/python3
"""Shared exact semantic classifier for Karto constraint provenance."""

EXPLICIT_TRY_CLOSE_LOOP = 'TRY_CLOSE_LOOP'
EXPLICIT_FIELDS = ('creation_provenance', 'creation_stage', 'matcher_type')


def is_explicit_try_close_loop(record):
    """Return true only for an exact instrumentation token.

    In particular, ``ADD_EDGES_BEFORE_TRY_CLOSE_LOOP`` is a stage label for
    ordinary sequential edge creation and must never be treated as a loop
    closure.
    """
    return any(record.get(field) == EXPLICIT_TRY_CLOSE_LOOP
               for field in EXPLICIT_FIELDS)


def constraint_family(record):
    if is_explicit_try_close_loop(record):
        return EXPLICIT_TRY_CLOSE_LOOP
    provenance = record.get('creation_provenance')
    if provenance in ('PREVIOUS_SCAN', 'RUNNING_SCAN_CHAIN', 'NEAR_CHAIN'):
        return provenance
    return 'UNKNOWN'
