"""Post-hoc measurement and mechanism review of the doc-77 continuous suite.

This package never re-runs a backend and never modifies the doc-77 artefacts.
It reads the recorded run directories (rosout accept log, key-scan stream, scan
stream, ground-truth stream, loop events, the four graph snapshots and the
episode results) and writes a separate, clearly labelled review root.

Modules
-------
``evidence``  : loading / parsing of one recorded run and of the whole suite.
``review``    : the five review phases (boundary audit, recoverability,
                statistics, ground truth, mechanism) plus the offline gate.
``figures``   : the review figures (each answers one review question).
"""
