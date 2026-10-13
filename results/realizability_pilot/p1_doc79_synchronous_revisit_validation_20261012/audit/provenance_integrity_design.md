# Doc-79 audit — provenance integrity design

## Existing machinery (unchanged)

`OpenMapper` already records every graph-constraint creation into a
mutex-protected buffer (`m_EdgeProvenanceBuffer`) with provenance enums
(`ConstraintProvenance_PreviousScan / _RunningScanChain / _NearChain /
_TryCloseLoop / _FirstScanCrossSensor / _CustomObjectLastScan / _Other`),
match responses/thresholds when available, relative measurement and 3x3
covariance, and `creation_sequence`. `FlushEdgeProvenance()` swaps the buffer
under the mutex and appends JSONL to the configured path.

## Doc-79 write discipline

- The launch runs with `instrumentation_flush_period_s = 0.0` — the
  maintenance thread never flushes, so the **only** writer is the serialized
  boundary export (plus the destructor flush, which runs after the spin has
  stopped).
- `doc79_sync_boundary_export` calls `FlushEdgeProvenance()` **before** writing
  the graph dump and reports `pending_edge_provenance`; the driver requires it
  to be `false` (i.e. everything created before the export is on disk).
- Consequence: a graph edge present in a synchronous dump must have its
  `constraint_created` record in the JSONL. The analysis checks this set
  relation (`provenance_graph_consistency`) and reports edges without records
  instead of assuming they cannot exist.

## Integrity checks (offline, per run)

- file exists, non-empty;
- every record parses, `run_id` matches `doc79_<episode>_a<NN>`;
- `creation_sequence` strictly increasing, no duplicates;
- record types limited to the documented set;
- record count reported next to the sync snapshot it was flushed for;
- rejection causes of candidate historical links are **not** reconstructible
  from this instrument and are reported as
  `REJECTION_CAUSE_NOT_OBSERVABLE` rather than inferred from the final graph.
