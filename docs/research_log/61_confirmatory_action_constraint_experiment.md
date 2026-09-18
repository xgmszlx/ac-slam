# Phase v12: preregistered confirmatory action--constraint experiment

## Block ledger (all eight preregistered blocks)

| block | target | planned/active seed | canonical prefix SHA-256 | A1 | A3 | A2 | budget | primary eligible |
|---|---|---:|---|---|---|---|---|---|
| target_A_H1 | A | 51001 / 51001 | `b209f6c9edb81b5c0e720c609205c25425977f7a14acba392a65c695a44ef90e` | REPLAYED | REPLAYED | REPLAYED | PASS | yes |
| target_A_H2 | A | 51002 / 51002 | `bb0dc0c872836da0315a421a4f8a1c0e4f30eff8506fa5d5ec162ff34696b3db` | REPLAYED | REPLAYED | REPLAYED | PASS | yes |
| target_A_H3 | A | 51003 / 51003 | `ec9453e24d72760452215b09924203ba49d774124b1d11561bce55260966f427` | REPLAYED | REPLAYED | REPLAYED | PASS | yes |
| target_A_H4 | A | 51004 / 51004 | `93fb0a342b3352fda596a5f468bec1258a234f1961d91aad54cee3c036375453` | REPLAYED | REPLAYED | REPLAYED | PASS | yes |
| target_B_H1 | B | 52001 / 52005 | `e4b0c6dd3753d1bfec9ada0d6c89b2a64ebcdc645b459b570118307c7772f446` | CAPTURED | TECHNICAL_INVALID_PREFIX_FINAL | CAPTURED | FAIL | no |
| target_B_H2 | B | 52002 / 52002 | `a19307dd6a2281b79c943c6be7709c74dfcece96bd6644ecdda2d89bd4aa315b` | REPLAYED | REPLAYED | REPLAYED | FAIL | no |
| target_B_H3 | B | 52003 / 52003 | `b6d4c30d999ff9a467d6c52a81e99c96429997002d3405fbbfb127dd07bcb43c` | REPLAYED | REPLAYED | REPLAYED | FAIL | no |
| target_B_H4 | B | 52004 / 52004 | `43c45f65d2feb0d6a5ec85d777b36e8da5ac2451bb7b68ce960ce7ef7ee4619d` | REPLAYED | REPLAYED | REPLAYED | FAIL | no |

The final analysis set is therefore 4/8 blocks and 12/24 branches, all from
Target A. Target B contributes no scientific endpoint to this report.

## Material Passport

- Material ID: `ac-slam-v12-confirmatory-20260917`
- Type: preregistered matched-block mechanism experiment
- Status: `ANALYZED / CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`
- Protocol: `results/realizability_pilot/p1_confirmatory_v12_20260917/preregistration/v12_preregistration.json`
- Protocol SHA-256: `ade2339e3f5f112f4bacc5c826c1c702bc41178e88f91cfce9bbf0e6190c542d`
- Planned scale: 2 targets x 4 canonical histories x 3 arms = 24 branches
- Statistical unit: canonical-history block, never an individual branch
- Analysis scope: `DESCRIPTIVE_ONLY_VALID_TARGET_A_BLOCKS`

## A. Preregistration Integrity

The frozen arms were `A1_DWELL`, `A3_MIN_TRIGGER`, and `A2_SWEEP90`; A0 was
excluded. A1 used a 7.6 s static dwell. A2 reused Sweep90. A3 executed
`theta0 -> theta0 + 0.5439732814 rad -> theta0` followed by one globally frozen
3.5 s dwell. The primary fixed state was the same five-pose, 15-DoF `X_T` in
all arms of a block. The primary scalar and contrasts were unchanged:

`J_T = -logdet(Sigma_T)/15`, `D_view = A2-A3`,
`D_trigger = A3-A1`, and `D_total = A2-A1`.

Collection and analysis remained separated until `COLLECTION_COMPLETE`. No
scientific endpoint authorized a rerun or replacement. Four technical
amendments are retained with their hashes:

1. Amendment 01 implemented the already bounded two-replay technical retry.
2. Amendment 02 corrected reserve bookkeeping to the preregistered target-level pool.
3. Amendment 03, written before endpoint opening, made insufficient two-target data fail closed as `CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`.
4. Amendment 04 was outcome-aware and therefore is not represented as preregistered: it resolves only a floating-point reconstruction at the 0.52 rad keyscan boundary. It changed no graph, endpoint, contrast, or eligibility decision.

The original analysis SHA-256 and amendment chain are preserved. The final
frozen analysis SHA-256 is
`26c4561f0111e75c63ad9e44488e1af93b06e686cc330c0ea29a5be0e6de29cd`.
The post-analysis closeout script is separate and cannot change the final gate.

## B. Canonical Histories

All four final Target A histories produced exact canonical prefixes. A/H1 first
failed target matching and A/H3 first failed exact canonical replay; the same
seeds succeeded on their second bounded attempts. These failures remain in the
ledger.

B/H1 primary seed 52001 failed exact replay twice. Target-level reserve 52005
then produced a canonical history, but the A3 branch failed exact prefix replay
after the finite retry cap. Reserve 52005 was not silently reused elsewhere.
B/H2 first failed target matching and then succeeded on the same seed. B/H2--H4
had exact arm prefixes, but subsequently failed the physical-budget gate.

## C. Target Reference Matching

Every final canonical history matched exactly five monotonic historical states
within the frozen 0.60 m / 0.25 rad tolerances. Target A used IDs 14--18 except
H3, which used 13--17; its maximum position/heading errors by block were:

| block | max position error (m) | max heading error (rad) |
|---|---:|---:|
| A/H1 | 0.1256 | 0.0277 |
| A/H2 | 0.1009 | 0.0556 |
| A/H3 | 0.0558 | 0.0303 |
| A/H4 | 0.0839 | 0.0221 |

Target B used IDs 19--23. Its maxima ranged from 0.3965--0.5726 m and
0.1015--0.1816 rad. These final matches were valid; the exclusion of Target B
was caused by prefix/budget failures, not by changing the target-state count.

## D. Budget Matching

All Target A blocks passed every frozen gate:

| block | distance range (m) | time range (s) | raw-scan relative range |
|---|---:|---:|---:|
| A/H1 | 0.0126 | 0.9 | 1.35% |
| A/H2 | 0.0114 | 1.4 | 2.13% |
| A/H3 | 0.0117 | 0.9 | 1.37% |
| A/H4 | 0.0191 | 1.0 | 1.66% |

All Target B blocks failed the frozen time and raw-scan gates while passing the
distance gate. Their time ranges were 3.8--3.9 s and raw-scan relative ranges
were 7.17--7.71%, versus limits of 1.5 s and 3%. In each B block, A2 lasted
about 3.8--3.9 s longer and collected about 35--39 more raw scans than A1/A3.
This is a systematic target-dependent budget failure, not random loss of one
episode. The preregistered rule forbids tolerance relaxation or outcome-driven
replacement, so none of B/H1--H4 enters endpoint analysis.

## E. A3 Manipulation Check

For the four valid Target A blocks:

| arm | accepted keyscans | heading-triggered | mean distance-triggered | mean action-stream yaw excursion (rad) |
|---|---|---|---:|---:|
| A1 | 28, 27, 26, 29 | 14, 14, 14, 15 | 13.25 | 9.307 |
| A3 | 29, 28, 27, 29 | 15, 15, 15, 15 | 13.25 | 10.361 |
| A2 | 30, 29, 28, 30 | 16, 16, 16, 16 | 13.25 | 10.957 |

A3 added one heading-triggered keyscan opportunity in three blocks and matched
A1 in H4. Its heading-triggered distribution was consistently one below A2.
The frozen study-level implementation therefore reports
`A3_keyscan_control_manipulation_weak = false`.

However, the action-wide 180-degree LiDAR FOV union saturated at 360 degrees
for all 12 analyzed branches. That aggregate cannot establish a pure
broader-FOV mechanism. The intention-to-treat A2--A3 action contrast remains
valid descriptively, but it must not be renamed a pure viewpoint/FOV effect.

## F. Primary Posterior Result

The two-target primary result is **not evaluable**. Descriptive Target A means
for the local linear-Gaussian posterior are:

| arm | mean J_T | mean trace(Sigma_T) | mean terminal trace |
|---|---:|---:|---:|
| A1 | 8.96660 | 0.013791 | 0.003597 |
| A3 | 9.02427 | 0.012608 | 0.003410 |
| A2 | 9.09514 | 0.012366 | 0.003184 |

The ordering is favorable on Target A, but it is not a confirmatory result:
the 7/8 rule and the required Target B 3/4 condition cannot be evaluated.

## G. A2-A3 Broad-Sweep Contrast

| Target A block | D_view = J_T(A2)-J_T(A3) |
|---|---:|
| H1 | +0.07006 |
| H2 | +0.05008 |
| H3 | +0.10542 |
| H4 | +0.05791 |

Target A is 4/4 positive, mean +0.07087 and median +0.06399. The descriptive
one-sided exact sign-test value is 0.0625; the Target-A-only block bootstrap
mean interval is [0.05399, 0.09354]. These numbers are not a substitute for the
missing Target B stratum. Formal verdict:
`NOT_EVALUABLE_TECHNICAL_INCOMPLETENESS`.

## H. A3-A1 Trigger-Package Contrast

| Target A block | D_trigger = J_T(A3)-J_T(A1) |
|---|---:|
| H1 | +0.08570 |
| H2 | +0.11095 |
| H3 | -0.00249 |
| H4 | +0.03652 |

Target A is 3/4 positive, mean +0.05767 and median +0.06111. The descriptive
one-sided exact sign-test value is 0.3125; the Target-A-only block bootstrap
mean interval is [0.01702, 0.09832]. Formal verdict:
`NOT_EVALUABLE_TECHNICAL_INCOMPLETENESS`.

For completeness, descriptive `D_total = A2-A1` is 4/4 positive (mean
+0.12854, median +0.12935; Target-A-only bootstrap mean interval
[0.09868, 0.15839]) and is also not confirmatory-evaluable.

## I. Constraint-Generation Mechanism

Aggregated over the four valid Target A blocks:

| arm | all new edges | E_T | E_N | local | PREVIOUS_SCAN | RUNNING_SCAN_CHAIN | NEAR_CHAIN |
|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | 181 | 8 | 51 | 122 | 110 | 58 | 13 |
| A3 | 188 | 12 | 52 | 124 | 113 | 63 | 12 |
| A2 | 197 | 15 | 57 | 125 | 117 | 70 | 10 |

The per-block target-edge counts were normally A1/A3/A2 = 2/3/4, with H4 =
2/3/3. All 566 observed new factors were created at
`ADD_EDGES_BEFORE_TRY_CLOSE_LOOP`; matcher provenance was 531 sequential
running-buffer and 35 sequential near-chain constraints. No factor in this
valid subset came from `TRY_CLOSE_LOOP`. The action changed the realized factor
set, but this evidence concerns Karto's sequential factor-generation process,
not successful classical loop closure.

## J. Graph Utility / Posterior Decomposition

Mean frozen target-factor graph contribution `Delta U_T` was 595.49 (A1),
839.14 (A3), and 984.39 (A2). This co-varies with additional target and
non-target factors and with the posterior ordering; it does not isolate a
single causal covariance channel.

History-edge removal disconnected every one of the 12 analyzed graphs.
Accordingly, the only valid report is `HISTORY_CONNECTIVITY_CRITICAL`; finite
`U_without_history` values are not interpreted as a continuous `Delta U_H`.

The exact target-edge endpoint sets differed across arms in all four blocks.
Each block shared one target edge across all arms, but the remaining target
factor identities/topology differed. A covariance-only swap would therefore
also change edge identity/topology. Verdict:
`COUNTERFACTUAL_SWAP_NOT_IDENTIFIABLE`.

Consequently, v12 Target A data do not separate target-factor covariance from
surrounding-graph context. The posterior change is a realized-factor-set
effect, not evidence that target-edge covariance alone caused the gain.

## K. Target-wise Consistency

Target A provides a coherent descriptive signal: D_view is 4/4 positive,
D_trigger is 3/4 positive, and D_total is 4/4 positive. Target B has zero
eligible blocks, so direction, heterogeneity, and cross-target replication are
unknown. It would be scientifically incorrect to label this either supported
cross-target consistency or target-dependent heterogeneity.

## L. Literature-Boundary Interpretation

The strongest defensible statement is narrow:

> Under four budget-valid Target A canonical histories, assigned action changed
> Karto's actual sequential factor-generation set and the local Gaussian
> posterior over the same five historical states.

This is not evidence of a first in-place rotation, panoramic observation,
active loop-closure probability model, future topology planner, or data-
association-uncertainty method. It also does not yet establish a general
realizability predictor. The causal language remains bounded to:

`executed action -> actual factor generation -> realized factor set -> local Gaussian posterior`.

## M. Final Scientific Gate

`CONFIRMATORY_EXPERIMENT_TECHNICALLY_INCOMPLETE`

Reason: the preregistered design required four usable blocks from each of two
targets. It obtained four from Target A and zero from Target B. The positive
Target A pattern is retained as descriptive evidence, not upgraded into a
supported mechanism. No predictor, planner integration, fifth control, new
target, threshold relaxation, or additional outcome-driven history is started
from this gate.

Machine-readable evidence:

- `analysis/block_ledger.csv`
- `analysis/branch_metrics.csv`
- `analysis/paired_contrasts.csv`
- `analysis/constraint_mechanism.csv`
- `analysis/descriptive_mechanism_closeout.json`
- `analysis/target_edge_identity.csv`
- `decision/final_gate.json`
