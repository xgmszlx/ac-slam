"""Published-cache endpoint diagnostic; never a synchronized active-loop label."""
import numpy as np
from common import ASSETS,csv_out,distance,base_pose
from headroom import accepted_times


def audit_legacy_loops(reader):
    rows=[];summary=[]
    table=reader.csv(ASSETS/'results/phase4c/aggregate/run_table.csv')
    for r in table:
        run=ASSETS/r['run_dir'];loops=reader.json(run/'loops.json')['loops']
        reader.register(run/'trajectory_slam.txt');tum=np.loadtxt(run/'trajectory_slam.txt',ndmin=2)
        times,uids=accepted_times(reader,run,tum)
        for loop in loops:
            if loop.get('actual_start_time') is None:continue
            a=reader.json(run/loop['snapshot_before']);b=reader.json(run/loop['snapshot_after'])
            nodes={int(k):v for k,v in a['pose_graph_nodes'].items()};before_indices={e['index'] for e in a['pose_graph_edges']}
            fresh=[e for e in b['pose_graph_edges'] if e['index'] not in before_indices]
            cross=[e for e in fresh if (e['start'] in nodes)!=(e['end'] in nodes) and abs(e['start']-e['end'])>1]
            target_points=loop.get('planned_loop_path',[])
            target_cross=[]
            for e in cross:
                old=e['start'] if e['start'] in nodes else e['end'];n=nodes[old]
                p=base_pose({'x':n['x'],'y':n['y'],'theta':n['theta']})
                if any(distance(p,q)<=1.0 for q in target_points):target_cross.append(e)
            last=max(nodes) if nodes else None
            age=loop['actual_start_time']-times[last] if last is not None and last in times else None
            rows.append({'episode_id':r['map']+'_'+r['seed']+'_'+r['condition'],'map':r['map'],'method':r['method'],
              'loop_id':loop['loop_id'],'execution_started':True,'waypoint_sequence_complete':loop.get('executed_loop'),
              'early_stopped':loop.get('early_stopped'),'published_new_edges':len(fresh),
              'published_nonsequential_old_new_crosslinks':len(cross),
              'crosslinks_to_planned_path_neighborhood':len(target_cross),
              'crosslink_endpoint_pairs':str([(e['start'],e['end']) for e in cross]),
              'explicit_Karto_events_during_execution':loop.get('accepted_closure_events_during_execution'),
              'actual_loop_distance_m':loop.get('extra_distance'),'actual_loop_time_s':loop.get('extra_time'),
              'pre_cache_last_accepted_stamp':times.get(last),
              'pre_cache_age_s':age,'graph_timestamp_identity':'native acceptance state_id/unique_id log; author TUM stamps agree <=1us; not raw scan acquisition time',
              'constraint_creation_provenance':'NOT_RECORDED in these old runs',
              'diagnostic_scope':'published-cache difference; can include edges outside actual action window; NOT confirmed active causal edge count',
              'target_attribution_scope':'1m from any planned waypoint; not original target association test or matching provenance'})
        summary.append({'episode_id':r['map']+'_'+r['seed']+'_'+r['condition'],'map':r['map'],'seed':r['seed'],
            'condition':r['condition'],'method':r['method'],'validity':r['validity'],
            'whole_run_APE_m':r['ape_rmse_m'],'whole_run_distance_m':r['total_exploration_distance_m'],
            'active_loop_distance_m':r['active_loop_distance_m'],'active_loop_time_s':r['active_loop_time_s'],
            'planned_loops':r['planned_active_loops'],'executed_loops':r['executed_active_loops'],
            'old_explicit_target_attributable_loops':r['target_attributable_loops'],
            'old_realization_definition':'explicit accepted-loop event with target-region attribution; NOT all historical information',
            'whole_map_boundary_F1':r['boundary_f1'],
            'counterfactual_limit':'no no-revisit or nearest-target arm with matched pre-state'})
    csv_out('analysis/legacy_loop_endpoint_diagnostic.csv',rows)
    csv_out('analysis/whole_run_outcomes_and_cost.csv',summary)
    paired=[]
    for map_id in ['map3','map8']:
        for seed in sorted({r['seed'] for r in summary if r['map']==map_id}):
            g={r['condition']:r for r in summary if r['map']==map_id and r['seed']==seed}
            for c in ['B','C']:
                a,b=g['A'],g[c]
                paired.append({'map':map_id,'seed':seed,'comparison':c+'-A',
                    'APE_difference_m':float(b['whole_run_APE_m'])-float(a['whole_run_APE_m']),
                    'total_distance_difference_m':float(b['whole_run_distance_m'])-float(a['whole_run_distance_m']),
                    'active_loop_distance_difference_m':float(b['active_loop_distance_m'])-float(a['active_loop_distance_m']),
                    'boundary_F1_difference':float(b['whole_map_boundary_F1'])-float(a['whole_map_boundary_F1']),
                    'scope':'existing policy-level paired seed; independent histories, NOT matched-state A1/A2 causal experiment'})
    csv_out('analysis/formal_descriptive_paired_outcomes.csv',paired)
    return rows
