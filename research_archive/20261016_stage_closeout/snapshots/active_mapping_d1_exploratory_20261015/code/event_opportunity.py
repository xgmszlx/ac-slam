"""Audit saved native map timestamps/state completeness, no simulation or GT."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
base=Path('/home/wcqw/ac-slam/results/phase1')
records=[]
for method in ['A_nearest_frontier','B_prior_tsp','C_slam_aware']:
    source=base/('smoke_'+method+'_map3_run1')
    m=json.loads((source/'metrics.json').read_text());manifest=json.loads((source/'manifest.json').read_text())
    maps=list(source.rglob('*.pgm'))
    records.append({'method':method,'native_map_files':[str(p) for p in maps],
                    'mapping_start_s':m['explore_start_sim_time'],'final_map_stamp_s':m['final_map']['stamp'],
                    'exploration_duration_s':m['total_exploration_time'],'final_map_within_300s_of_task_start':m['final_map']['stamp']-m['explore_start_sim_time']<=300,
                    'serialized_scan_matcher_state':False,'recorded_navigation_costmap':False,
                    'occupancy_time_series_available':len(maps)>1,'source_commit':manifest['git_commit'],
                    'metrics_sha256':hashlib.sha256((source/'metrics.json').read_bytes()).hexdigest()})
result={'status':'NO_QUALIFIED_WITHIN_BUDGET_EVENT_EVIDENCE','records':records,
        'continuous_occupancy_sequence_available':False,'can_infer_first_CNN_stop_time':False,
        'near_complete_state_restore':'NOT_QUALIFIED_PGM_AND_POSE_GRAPH_DO_NOT_RESTORE_KARTO_AND_NAVIGATION',
        'within_300s_event':'UNKNOWN_NOT_PROVEN_ABSENT','scene_selection':'UNCHANGED_MAP3_NO_OUTCOME_BASED_REPLACEMENT',
        'new_ROS_allowed_by_phase2':False,
        'warning':'Completion time beyond 300s does not prove CNN cannot stop earlier. Final-map p_EX also cannot establish its first crossing.'}
(R/'results/phase2_event_opportunity.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
