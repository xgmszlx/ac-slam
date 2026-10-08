# 72 — CD Amendment 1 completion audit

## Outcome

Protocol `p1_context_disentangle_confirmatory_amendment1_20260930` reached a
hard stop with:

`CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE`

This is a technical outcome, not evidence for or against the preregistered
scientific interaction. No scientific contrast was computed.

## Outcome-blind amendment provenance

- The original `p1_context_disentangle_confirmatory_20260930` run remains
  preserved as `CD_PROSPECTIVE_TECHNICALLY_INCOMPLETE`.
- Its aggregate pre-amendment manifest SHA-256 remains
  `0725778cbcd223cea69384350bcedefc965c2bb8c75a32a484e1e7e4d747fd4b`
  across 3,881 files.
- Before amendment freeze, it contained no physical branch, backend replay,
  scientific analysis, or read scientific endpoint.
- Amendment preregistration SHA-256 is
  `692daf7f5180db660912e42dbe7e45bf3640e6f885fdcd785aa09a3e8df2c450`.
- The first eight histories per Target and deterministic arm orders were
  reused exactly. Histories were not regenerated and arms were not reordered.
- The only protocol amendment was to validate arm-position balance within
  each Target stratum instead of pooling Target A and Target B. Doses,
  `N=347`, controller, estimands, analysis, retry rules, backend, and
  scientific gates remained unchanged.

## Physical collection

- Blocks physically collected: 16/16.
- Technically valid branches: 48/48.
- Every block satisfied strict `D0 < D1 < D2` realized-dose ordering.
- Target-A and Target-B dose ranges and completion-scan ranges overlapped for
  both D1 and D2.
- Machine gate: `DOSE_TARGET_DECONFOUNDING_TECHNICALLY_CERTIFIED`.

## Backend replay

- Planned branches: 48.
- Replayed successfully: 45.
- Final invalid replays: 3.
- All three failures were the arms of the same frozen history,
  `target_A_H1`: `D0_ZERO`, `D1_THRESHOLD`, and `D2_HIGH`.
- Each failed arm exhausted the two frozen replay attempts.
- All six failed attempts reproduced the exact prefix graph structure but
  failed the preregistered zero-tolerance numerical prefix gate before suffix
  publication. Therefore no `graph_final.json` was created for these arms.
- Five of the six attempts had approximately 10.001 mm maximum node
  translation difference and 9.983 mm maximum edge-translation-measurement
  difference. One D2 attempt had larger differences; its repeat returned to
  the approximately 10 mm pattern.
- Because failure occurred before treatment suffix publication for every arm
  in this history, it cannot be interpreted as a dose-specific scientific
  response.

## Final gate

- Backend lock: `BACKEND_REPLAY_LOCKED_TECHNICALLY_INCOMPLETE`.
- Analysis authorization: false.
- Scientific endpoint read: false.
- Scientific contrasts computed: false.
- Automatic follow-up experiment started: false.
- Next registered recommendation:
  `STOP_AND_DIAGNOSE_CD_TECHNICAL_FAILURE`.

The next activity, if authorized, should be a technical diagnosis of the
`target_A_H1` prefix numerical-repeatability failure. It must not inspect the
uncomputed scientific contrast or reinterpret this incomplete run as a
negative scientific result.
