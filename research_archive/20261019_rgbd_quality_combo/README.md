# Local prototype archive

Current result: TECHNICAL_INCOMPLETE. No real Bonn SLAM runs (0/3); no trajectory benefit measured. See REPORT.md.

Own frontend code, a patch against the fixed official ORB-SLAM3 source, configuration and software tests are included. Generated full third-party source, binaries, partial downloads and raw data stay local. Build scripts record the qualified workstation paths and reuse its pinned original objects; this is not a portable standalone ORB-SLAM3 distribution. Reproduction on a different workstation requires mapping those paths and reconstructing the same dependencies/objects.

The three-condition execution guard requires complete data and actual frozen visual annotations. Do not manufacture the qualification file. No fetch loop or automatic fallback dataset is included. Old failures and frozen research remain intact.
