# Doc 80 — offline convergence audit of the Doc-79 direction study

Pure offline review (`POST_HOC_OFFLINE_RESEARCH_CONVERGENCE_AUDIT`). No new
robot runs, no planner work, no Karto changes, no model training. Baseline
`4f290fc0691324e13158d72fa77c18278e28b71e`.

## Layout

```
audit/      input_integrity.json, local_only_file_verification.csv,
            target_freeze_consistency.csv, target_freeze_sensitivity.json,
            boundary_watermark_sensitivity.csv,
            state_identity_and_frame_audit.csv, provenance_identity_audit.csv,
            analysis_corrections.md, pre_action_bundles/ (firewalled inputs;
            scans_pre_action.jsonl kept local via .gitignore)
analysis/   corrected_target_map_gt.csv, target_gt_original_comparison.csv,
            corrected_robot_relative_gt.csv, pre_action_state_audit.csv,
            historical_link_classes.csv, factor_group_contributions.csv,
            doc79_contribution_comparisons.csv,
            directional_visibility_features.csv, feature_outcome_join.csv,
            directional_competing_hypotheses.csv, statistical_corrections.*,
            final_research_gate.json
figures/    fig1_target_gt_correction, fig2_historical_association_structure,
            fig3_pre_action_directional_visibility, fig4_final_research_evidence
```

## Reproduction

```bash
PYTHONPATH=catkin_ws/python:tools/realizability_pilot /usr/bin/python3 \
  -m doc80_offline_review.run_all
/usr/bin/python3 tools/realizability_pilot/doc80_offline_review/figures.py \
  --suite-dir results/realizability_pilot/p1_doc80_offline_research_convergence_20261013
PYTHONPATH=catkin_ws/python /usr/bin/python3 \
  tools/realizability_pilot/doc80_offline_review/test_doc80.py
```

## Headline

- Measurement/GT/feature-input validity: all pass.
- Mechanism: `A HISTORICAL_ASSOCIATION_MECHANISM_SUPPORTED` (first-visit
  links carry 94% of the action-stage set-level contribution).
- Next step: `A STOP_PURE_ROTATION_SELECTION`.

Research log: `docs/research_log/80_doc79_offline_direction_feasibility_review.md`.
Review packet: `REVIEW_PACKET.md` (handoff + uncertainties + questions).
