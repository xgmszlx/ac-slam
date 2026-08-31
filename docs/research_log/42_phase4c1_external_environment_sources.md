# Phase 4C-1 External Environment Sources

Date: 2026-08-31

## Scope

This inventory was assembled before any new-map A/B/C exploration. The maps are
geometry sources for evaluation infrastructure, not new performance evidence.
M2 remains frozen as author-provided `map8`.

## Provenance and licence

All four candidates are public occupancy-map renderings linked from the
[StachnissLab pre-2014 2-D laser dataset page](https://www.ipb.uni-bonn.de/datasets/).
The source page identifies the dataset/provider for each item. The
[Radish repository](https://radish.sourceforge.net/) states that repository data
are distributed under Creative Commons Attribution; this audit records the linked
[CC BY 1.0 licence](https://creativecommons.org/licenses/by/1.0/). Downstream use
must preserve dataset and provider attribution.

| candidate | dataset / provider | original file | SHA-256 | effective scale | environment |
|---|---|---|---|---:|---|
| `radish_csail` | MIT CSAIL / Cyrill Stachniss | `csail.corrected.png` | `86345085...54f7` | 0.10 m/px, inferred | indoor laboratory/building |
| `radish_intel` | Intel Research Lab / Dirk Haehnel | `intel.gfs.png` | `82c2a35b...d607` | 0.05 m/px, GFS/raster agreement | indoor office/lab |
| `radish_fr079` | Freiburg Building 079 / Cyrill Stachniss | `fr079-complete.gfs.png` | `87e60978...16d2` | 0.05 m/px, GFS/raster agreement | corridor/room building |
| `radish_mexico` | Acapulco Convention Center / Nick Roy | `mexico.gfs.png` | `cda44567...a308` | 0.05 m/px, inferred | large indoor convention centre |

Full URLs, hashes, licence fields and resolution-status text are in
`results/phase4c1/candidate_inventory.csv`. Original PNG files are retained under
`results/phase4c1/source_maps/`.

## Deterministic conversion

`tools/build_phase4c1_external_environments.py` performs:

`source raster -> thresholded free mask -> largest cleaned free component ->`
`binary Stage bitmap -> world/yaml -> method-neutral skeleton prior -> draw.io XML`.

No raster was manually edited. Generated Stage bitmaps intentionally remove
unknown/unconnected exterior space and one-pixel scan-ray artefacts; this means the
Stage geometry is a documented conversion, not a claim that the original Radish
map is ground truth. Scale inference for CSAIL and Mexico remains a specific risk.
