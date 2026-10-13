#!/usr/bin/python3
"""Bounded, read-only offline direction audit. Never imports a ROS runner."""
import ast
import csv
import importlib.util
import json
import math
import pickle
import time
import sys
import io
import contextlib
from types import SimpleNamespace
from pathlib import Path
from collections import Counter
import numpy as np
import networkx as nx
import scipy.linalg
from scipy.spatial import KDTree
from common import ROOT,ASSETS,OUT,DOC79,DOC80,Inputs,sha,write_json,csv_out,workspace_snapshot,path_length,wrap,base_pose
from candidates import local_candidates,global_candidates,select_geometric_baselines,validate_bundle
from headroom import formal_headroom
from gt_check import check_run
from maps import audit_maps
from legacy_loops import audit_legacy_loops


def load_pure_functions(path,names,namespace):
    """Extract exact author function AST, avoiding runner imports/side effects."""
    tree=ast.parse(path.read_text());selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in selected}!=set(names):raise ValueError('Missing source functions')
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


def frozen_information(reader):
    p=ROOT/'tools/realizability_pilot/continuous_revisit/analysis.py';reader.register(p)
    return load_pure_functions(p,['jacobian','information','target_score'],{'np':np,'math':math,
                         'cho_factor':scipy.linalg.cho_factor,'cho_solve':scipy.linalg.cho_solve})


def sanitized_bundle(reader,run,manifest,boundary,problem,historic_graph):
    """Only pre-cut scans are decoded. GT/world target fields never enter bundle."""
    boundaries=reader.json(run/'boundary_manifest.json');cut=boundaries[boundary]
    graph_path=run/('graph_'+cut['file_stem']+'_sync.json');graph=reader.json(graph_path)
    if sha(graph_path)!=cut['sync_file']['sha256']:raise ValueError('Boundary graph hash differs')
    watermark=cut['watermark'];samples=[]
    for s in reader.lines(run/'scan_stream.jsonl'):
        if s['index']>watermark['scan_index']:break
        if s.get('map_base') is not None:
            samples.append({'index':s['index'],'stamp':s['stamp'],'map_base':s['map_base'],
                            'odom_base':s['odom_base'],'map_base_age_s':s['map_base_age_s']})
    if not samples:raise ValueError('No pre-decision observed robot pose')
    if any(s['stamp']>watermark['stamp']+1e-9 for s in samples):raise ValueError('Pre-cut index contains future timestamp')
    b={'episode_id':manifest['episode_id'],'run_id':manifest['run_id'],'problem':problem,'boundary':boundary,'decision_stamp':watermark['stamp'],
       'watermark_validated':bool(cut['all_checks_passed']),'scan_index_cut':watermark['scan_index'],
       'export_node_count':cut['sync_file']['node_count'],'export_edge_count':cut['sync_file']['edge_count'],
       'frame':'map_base_from_laser','graph':graph,'graph_sha256':sha(graph_path),
       'history_state_ids':[n['state_id'] for n in historic_graph['nodes']],
       'history_unique_ids':[n['unique_id'] for n in historic_graph['nodes']],
       'current_base':samples[-1]['map_base'],'current_pose_age_s':samples[-1]['map_base_age_s'],
       'trajectory_pre':[samples[0],samples[-1]],'trajectory_pre_is_full_stream':False,
       'prefix_observed_pose_samples':len(samples),
       'trajectory_input_scope':'all prefix records checked locally; only first/last pose witnesses published, not per-frame stream',
       'online_map':None,'online_map_status':'no pre-decision occupancy file captured',
       'source_files':{'sync_graph':str(graph_path),'scan_stream':str(run/'scan_stream.jsonl')},
       'trajectory_frame_caveat':'recorded causal TF map poses; past corrections not retroactively applied; not a safety certificate'}
    if problem=='A1':
        frozen=reader.json(run/'frozen_target.json')
        b['anchor_state_id']=frozen['anchor']['id'];b['anchor_unique_id']=frozen['anchor']['unique_id']
    validate_bundle(b,problem)
    write_json('audit/pre_state_bundles/%s/%s.json'%(manifest['episode_id'],problem),b)
    return b


def doc79_analysis(reader):
    info=frozen_information(reader);inventory=[];states=[];local=[];global_=[];scores=[];value=[];costs=[];excluded=[];gt_rows=[];edge_rows=[]
    archived={(r['episode_id'],r['attempt']):r for r in reader.csv(DOC79/'analysis/per_episode_metrics.csv')}
    # Secondary task metric is kept separate from graph information, and is
    # checked against the underlying graph + acceptance/GT streams below.
    corrected=reader.csv(DOC80/'analysis/corrected_target_map_gt.csv')
    for f in sorted((DOC79/'runs').glob('*/attempt_*/run_manifest.json')):
        m=reader.json(f);run=f.parent;boundaryfile=run/'boundary_manifest.json'
        row={'dataset_id':'doc79','episode_id':m['episode_id'],'run_dir':str(run),'source_commit':m['baseline_commit'],
            'actual_executed_action':m['action_id'],'recorded_validity':m['technical_validity'],
            'raw_trajectory_available':(run/'scan_stream.jsonl').is_file(),'pre_decision_state':'two synchronous graphs',
            'usable_for_A1':'pre-state geometry, actual rotation outcomes; no competing translated-path outcomes',
            'usable_for_A2':'pre-return historical regions, actual single target; other target outcomes unknown'}
        inventory.append(row)
        if m['technical_validity']!='MEASUREMENT_VALIDATED':
            excluded.append(dict(row,reason='not per-run measurement validated'));continue
        before=reader.json(run/'graph_before_return_sync.json');arrival=reader.json(run/'graph_arrival_sync.json')
        before_ids={n['state_id'] for n in before['nodes']};frozen=reader.json(run/'frozen_target.json')
        a1=sanitized_bundle(reader,run,m,'G_arrival','A1',before)
        a2=sanitized_bundle(reader,run,m,'G_before_return','A2',before)
        lc=local_candidates(a1);gc=global_candidates(a2);local.extend(lc);global_.extend(gc)
        for b in [a1,a2]:
            states.append({'episode_id':m['episode_id'],'problem':b['problem'],'boundary':b['boundary'],
                'decision_stamp':b['decision_stamp'],'scan_index_cut':b['scan_index_cut'],
                'nodes':len(b['graph']['nodes']),'edges':len(b['graph']['edges']),'history_nodes':len(before_ids),
                'online_occupancy_available':False,'current_pose_age_s':b['current_pose_age_s'],
                'bundle_path':'audit/pre_state_bundles/%s/%s.json'%(m['episode_id'],b['problem'])})
        ranking=select_geometric_baselines(gc)
        for c in gc:
            if 'target_state_id' not in c:continue
            scores.append({'episode_id':m['episode_id'],'decision_boundary':'G_before_return',
              'candidate_id':c['candidate_id'],'target_state_id':c['target_state_id'],
              'accepted_state_gap':c['accepted_state_gap'],
              'B0_euclidean_lower_bound_m':c['euclidean_lower_bound_m'],
              'B0_selected_proxy':c['candidate_id']==ranking['B0_EUCLIDEAN_NEAREST_PROXY'],
              'B1_RAL_score':None,'B1_status':'NOT_EVALUABLE: historical clusters are not author prior/TSP state',
              'B2_P_ALC_reward':None,'B2_status':'CONCEPTUAL_BASELINE_ONLY; no calibrated model/view score',
              'B3_target_historical_support_count':c['B3_target_support_count'],
              'B3_selected_proxy':c['candidate_id']==ranking['B3_HISTORY_SUPPORT_PROXY'],
              'actual_target_gain':None,'outcome_status':'COUNTERFACTUAL_OUTCOME_UNOBSERVED',
              'B0_cost_scope':'Euclidean proxy only; not nearest reachable A-star target'})
        # Outcomes are decoded ONLY AFTER candidate generation, with explicit
        # phase/episode join. No outcome is attributed to a translated candidate.
        result=reader.json(run/'episode_result.json');boundaries=reader.json(boundaryfile)
        scans=list(reader.lines(run/'scan_stream.jsonl'));targets=frozen['target_state_ids']
        graphs={stage:reader.json(run/('graph_'+stage+'_sync.json')) for stage in ['before_return','arrival','action_done','final']}
        gt_rows.extend(check_run(reader,run,m,graphs,scans,result,frozen,corrected))
        js={stage:info['target_score'](g,targets)['J_T'] for stage,g in graphs.items()}
        archived_row=archived[(m['episode_id'],run.name)]
        for stage in js:
            if abs(js[stage]-float(archived_row['J_'+stage+'_sync']))>1e-8:raise ValueError('Information recomputation mismatch')
        # Verify post graph raw files, ledger, GT and provenance availability.
        for name in ['gt_stream.jsonl','rosout.log','keyscan_stream.jsonl','native_processing_ledger.jsonl','mapper_params.yaml']:
            reader.register(run/name)
        prov=list(reader.lines(run/'karto_edge_provenance.jsonl'))
        # Synchronous graph edge indices are zero-based; native provenance is
        # creation_sequence (one-based). Validate endpoints before joining.
        by_index={int(p['creation_sequence'])-1:p for p in prov if p.get('record_type')=='constraint_created'}
        for e in graphs['final']['edges']:
            p=by_index.get(e['index'])
            if p is None or (p['source_state_id'],p['target_state_id'])!=(e['source_state_id'],e['target_state_id']):
                raise ValueError('Graph/provenance edge identity mismatch')
        stage_errors={stage:[float(r['map_error_translation_m']) for r in corrected if r['episode_id']==m['episode_id'] and r['stage']==stage and r['status']=='EVALUABLE'] for stage in graphs}
        return_start=boundaries['G_before_return']['watermark']['scan_index'];arrival_end=boundaries['G_arrival']['watermark']['scan_index']
        return_scans=[s for s in scans if return_start<=s['index']<=arrival_end and s.get('odom_base') is not None]
        obs0=result['action_start_scan_index'];obs=[s for s in scans if obs0<=s['index']<obs0+result['action_scan_count']]
        for stage,previous in [('arrival','before_return'),('action_done','arrival'),('final','action_done')]:
            prior_indices={e['index'] for e in graphs[previous]['edges']}
            fresh=[e for e in graphs[stage]['edges'] if e['index'] not in prior_indices]
            oldnew=[e for e in fresh if (e['source_state_id'] in before_ids)!=(e['target_state_id'] in before_ids)]
            for e in fresh:
                if abs(e['source_state_id']-e['target_state_id'])<=1:continue
                p=by_index[e['index']]
                edge_rows.append({'episode_id':m['episode_id'],'stage':stage,'edge_index':e['index'],
                    'source_state_id':e['source_state_id'],'target_state_id':e['target_state_id'],
                    'source_unique_id':e['source_unique_id'],'target_unique_id':e['target_unique_id'],
                    'scan_index_gap':abs(e['source_state_id']-e['target_state_id']),
                    'touches_first_history':e['source_state_id'] in before_ids or e['target_state_id'] in before_ids,
                    'creation_provenance':p['creation_provenance'],'creation_sequence':p['creation_sequence'],
                    'sim_time':p['sim_time'],'match_response':p['match_response'],
                    'covariance_trace':float(np.trace(e['covariance_3x3'])),
                    'information_role':'edge count/response alone is NOT task benefit or additive information gain'})
            reduced=dict(graphs[stage],edges=[e for e in graphs[stage]['edges'] if e['index'] not in {x['index'] for x in oldnew}])
            try:
                contribution=js[stage]-info['target_score'](reduced,targets)['J_T']
                factor_status='EVALUABLE_FIXED_LINEARIZATION'
            except np.linalg.LinAlgError:
                contribution=None
                factor_status='NOT_EVALUABLE_EDGE_REMOVAL_DISCONNECTS_ANCHORED_GRAPH'
            sources=Counter(by_index.get(e['index'],{}).get('creation_provenance','UNKNOWN') for e in oldnew)
            value.append({'episode_id':m['episode_id'],'place':m['place_id'],'actual_action':m['action_id'],
                 'stage':stage,'previous_stage':previous,'gain_source':'SYNCHRONOUS_DUMP',
                 'J_before':js[previous],'J_after':js[stage],'actual_delta_J':js[stage]-js[previous],
                 'fresh_edges':len(fresh),'first_history_to_new_edges':len(oldnew),
                 'source_counts':json.dumps(dict(sources),sort_keys=True),
                 'old_new_factor_contribution_fixed_linearization':contribution,
                 'factor_diagnostic_status':factor_status,
                 'factor_diagnostic_not_stage_gain':True,
                 'target_mean_gt_before_m':np.mean(stage_errors[previous]) if stage_errors[previous] else None,
                 'target_mean_gt_after_m':np.mean(stage_errors[stage]) if stage_errors[stage] else None,
                 'GT_source':'Doc80 corrected stage node laser-to-base, pre-action rigid alignment; audited code/raw inputs',
                 'counterfactual_outcomes':'unobserved; independent episodes not same initial SLAM graph'})
        costs.append({'episode_id':m['episode_id'],'actual_action':m['action_id'],'return_actual_distance_m':path_length([s['odom_base'] for s in return_scans]),
           'return_actual_time_s':return_scans[-1]['stamp']-return_scans[0]['stamp'],
           'return_cost_scope':'odom length between synchronized boundary watermarks, includes settle, not simulator GT',
           'action_actual_rotation_rad':result['action_cumulative_rotation_rad'],'action_actual_distance_m':result['action_path_length_m'],
           'action_observation_budget':result['action_frames_target'],'action_motion_frames_at_completion':result['action_done_valid_frames'],
           'total_action_observation_time_s':boundaries['G_final']['watermark']['stamp']-obs[0]['stamp'],
           'motion_completion_driver_time_s':obs[result['action_done_valid_frames']-1]['stamp']-obs[0]['stamp'],
           'synchronous_action_done_boundary_time_s':boundaries['G_action_done']['watermark']['stamp']-obs[0]['stamp'],
           'G_final_delta_J_vs_before_return':js['final']-js['before_return'],
           'estimated_candidate_distance_m':None,'predicted_vs_actual':'not mixed; hypothesis costs in candidate tables'})
    csv_out('analysis/local_path_candidates.csv',local);csv_out('analysis/global_target_candidates.csv',global_)
    csv_out('analysis/baseline_score_comparison.csv',scores);csv_out('analysis/historical_constraint_value.csv',value)
    csv_out('analysis/actual_revisit_cost.csv',costs);csv_out('audit/available_decision_states.csv',states)
    csv_out('analysis/independent_doc79_target_GT.csv',gt_rows)
    csv_out('analysis/historical_constraint_edges.csv',edge_rows)
    csv_out('audit/excluded_doc79_attempts.csv',excluded)
    write_json('analysis/candidate_geometry.json',{'A1':local,'A2':global_})
    csv_out('analysis/revisit_candidate_inventory.csv',[{'episode_id':s['episode_id'],'problem':s['problem'],
        'geometric_candidates':sum(c['episode_id']==s['episode_id'] for c in (local if s['problem']=='A1' else global_)),
        'certified_safe_moving_candidates':0,'true_alternative_outcomes':0,'pre_decision_map_available':False} for s in states])
    return inventory,value,costs


def native_RAL_diagnostic(reader):
    source=ROOT/'baseline/Graph-Based_SLAM-Aware_Exploration/scripts/utils.py';reader.register(source)
    ns=load_pure_functions(source,['get_d_opt','get_path_length','get_normalized_weighted_spanning_trees'],
        {'np':np,'nx':nx,'scipy':scipy,'EIG_TH':1e-6})
    optimizer=ROOT/'baseline/Graph-Based_SLAM-Aware_Exploration/scripts/offline_tsp_evaluation.py';reader.register(optimizer)
    opt=load_pure_functions(optimizer,['calculate_edge_distance_over_priormap','greedy_tsp_update','offline_evaluate_tsp_path'],
         {'np':np,'nx':nx,'math':math,'sys':sys,'time':time,'KDTree':KDTree,'utils':SimpleNamespace(**ns)})
    rows=[]
    for item in reader.csv(ASSETS/'results/phase4c/aggregate/run_table.csv'):
        run=ASSETS/item['run_dir'];record=reader.json(run/'tsp_record.json',False)
        prior_files=list((run/'author_outputs').glob('prior_map*.pickle'))
        if not record or len(prior_files)!=1:continue
        reader.register(prior_files[0])
        # Local repository-owned pickles are trusted archived inputs; no remote pickle downloads.
        with prior_files[0].open('rb') as f:g=pickle.load(f)
        path=record['full_tsp_path'];edges=set(zip(path,path[1:]))|set(zip(path[1:],path))
        graph=g.edge_subgraph(edges).copy()
        if not all('d_opt' in g.edges[e] for e in g.edges):
            rows.append({'episode_id':item['map']+'_'+item['seed']+'_'+item['condition'],'status':'ARCHIVED_PRIOR_D_OPT_MISSING'});continue
        dopt=float(ns['get_normalized_weighted_spanning_trees'](graph,weight_type='D-opt',weight='d_opt'))
        dist=float(ns['get_path_length'](g,path,weight='weight'))
        dvalues=[float(g.edges[e]['d_opt']) for e in g.edges]
        event_rows=reader.csv(run/'events.csv')
        plans=[json.loads(e['data'])['path'] for e in event_rows if e['event']=='SLAM_PATH_CREATED']
        planned_path=plans[0] if plans else None
        # Exact original offline optimizer, with the SAVED initial TSP: no new
        # solver randomness, no invented cluster scoring, no ROS imports.
        with contextlib.redirect_stdout(io.StringIO()):result=opt['offline_evaluate_tsp_path'](g,path)
        is_optimized,recomputed_path,loop_indices,modified_utility,modified_dopt,modified_distance,_,_=result
        if not is_optimized:recomputed_path=path
        rows.append({'episode_id':item['map']+'_'+item['seed']+'_'+item['condition'],'map':item['map'],
            'status':'EXACT_AUTHOR_PURE_FUNCTION_DIAGNOSTIC','prior_nodes':len(g),'route_length_m':dist,
            'normalized_spanning_tree_D_opt':dopt,'D_opt_over_distance':dopt/dist,
            'min_prior_edge_dopt':min(dvalues),'max_prior_edge_dopt':max(dvalues),
            'recorded_modified_path_vertices':len(planned_path) if planned_path else None,
            'modified_path_distance_m':modified_distance,'modified_path_D_opt':modified_dopt,
            'modified_path_utility':modified_utility,
            'modified_vs_tsp_utility_ratio':modified_utility/(dopt/dist) if modified_utility else None,
            'recorded_path_matches_native_recalculation':planned_path==recomputed_path if planned_path else None,
            'reevaluated_native_loop_indices':json.dumps(sorted(loop_indices)),
            'optimizer_source_sha256':sha(optimizer),
            'actual_target_attributable_loops':item['target_attributable_loops'],
            'actual_executed_active_loops':item['executed_active_loops'],
            'actual_whole_run_ape_rmse_m':item['ape_rmse_m'],
            'native_source_sha256':sha(source),'candidate_score_scope':'native full-TSP utility, NOT a score on new historic clusters',
            'outcome_scope':'whole run observational; not target counterfactual or causal utility validation'})
    csv_out('analysis/native_RAL_utility_diagnostic.csv',rows)
    return rows


def provenance(reader,inventory):
    rows=[]
    for r in inventory:
        d79=r['dataset_id']=='doc79'
        rows.append({'dataset_id':r['dataset_id'],'source_commit':r.get('source_commit'),'episode_id':r['episode_id'],
          'decision_time':'G_before_return / G_arrival' if d79 else 'per-loop published pre-execution cache; target already selected',
          'available_pre_action_state':r['pre_decision_state'],'actual_executed_action':r.get('actual_executed_action',r.get('recorded_validity')),
          'candidate_action_set':'one actually executed arm; geometric alternatives newly enumerated, unexecuted' if d79 else 'A/B/C physical whole-run policies in independent histories',
          'actual_backend_constraints':'synchronous graph edges + provenance' if d79 else 'g2o/cached graph + explicit closure events; attribution needs qualification',
          'GT_availability':'raw GT stream, pre-action alignment + node identities' if d79 else 'raw GT world samples + author laser GT TUM',
          'map_quality_availability':'final occupancy only; NO online boundary occupancy' if d79 else 'final occupancy + Stage-reference grid metrics; no synchronous pre/post grids',
          'known_artifacts':'different initial graphs across actions; no certified moving-path safety' if d79 else 'selected run paths reuse phase4b for map3; published graph cache/accepted timestamp caveats; Mexico incomplete',
          'usable_for_A1':r['usable_for_A1'],'usable_for_A2':r['usable_for_A2'],
          'evidence_limitations':'unexecuted counterfactual unknown; no matched initial graph comparison',
          'raw_files_verified':r['raw_trajectory_available'],'run_dir':r['run_dir']})
    # Additional campaigns are audited as inventories/mechanism context, not
    # recounted as fresh independent observations or causal action experiments.
    for dataset,rel,limit in [('phase2b','results/phase2b','positive control and mechanism only'),
        ('phase4a','results/phase4a','earlier diagnostic/modified prior scenario, no clean A1/A2 counterfactual'),
        ('phase4b','results/phase4b','overlaps selected map3 runs above; do not double count'),
        ('doc76','results/realizability_pilot/p1_action_selection_exploratory_20261010','CD suffix geometry inconsistent; no physical action causal interpretation'),
        ('doc77','results/realizability_pilot/p1_continuous_revisit_actions_20261010','naive stage labels invalidated by published-cache lag'),
        ('doc78','results/realizability_pilot/p1_continuous_boundary_review_20261012','fixed-final-linearization attribution, not synchronous stage gain')]:
        p=ASSETS/rel;files=list(p.rglob('*.csv')) if p.exists() else []
        for f in files:
            if f.stat().st_size<4*1024*1024:reader.register(f)
        rows.append({'dataset_id':dataset,'episode_id':'CAMPAIGN_INVENTORY_ONLY','source_commit':'see archived manifests',
             'run_dir':str(p),'raw_files_verified':'only enumerated summary tables hashed; not every campaign raw stream',
             'available_pre_action_state':'not used for candidate generation','actual_executed_action':'see old logs',
             'candidate_action_set':'NOT_EVALUATED','actual_backend_constraints':'context only','GT_availability':'not independently reprocessed this campaign',
             'map_quality_availability':'not independently reprocessed this campaign','known_artifacts':limit,
             'usable_for_A1':'NO causal candidate comparison','usable_for_A2':'NO causal candidate comparison',
             'evidence_limitations':limit,'summary_csv_count':len(files),'directory_exists':p.exists()})
    csv_out('audit/dataset_inventory.csv',inventory);csv_out('audit/data_provenance_matrix.csv',rows)


def main():
    reader=Inputs();before=workspace_snapshot()
    # Preserve old files, including Doc81. All inputs remain read-only.
    for workspace in [ASSETS,Path('/home/wcqw/ac-slam_doc81')]:
        for pattern in ['docs/research_log/7[6-9]*.md','docs/research_log/80*.md','docs/research_log/81*.md']:
            for f in workspace.glob(pattern):reader.register(f)
    for f in ROOT.glob('tools/research_direction/alc_revisit_screening/*.py'):reader.register(f)
    for rel in ['tools/evaluate_slam_run.py','tools/analyze_phase4c_formal.py',
                'baseline/Graph-Based_SLAM-Aware_Exploration/src/pubPathGT.cpp',
                'baseline/Graph-Based_SLAM-Aware_Exploration/scripts/path_planner.py']:
        reader.register(ASSETS/rel)
    inventories,headroom,preloop=formal_headroom(reader)
    maps=audit_maps(reader)
    legacy=audit_legacy_loops(reader)
    inv,value,costs=doc79_analysis(reader);inventories+=inv
    native=native_RAL_diagnostic(reader);provenance(reader,inventories)
    old_document_and_positive_audit(reader)
    after=workspace_snapshot();unchanged=before==after
    write_json('audit/workspace_protection.json',{'before':before,'after':after,'unchanged':unchanged,
         'scope':'worktree HEAD/branch/status and original user-file hashes; registered raw files separately hashed'})
    if not unchanged:raise ValueError('Other worktree state changed')
    reader.verify()
    print(json.dumps({'formal_selected_runs':len(headroom),'doc79_valid_runs':len(costs),
         'synchronous_stage_rows':len(value),'native_RAL_diagnostics':len(native),
         'final_occupancy_maps_recomputed':len(maps),
         'published_cache_active_loop_diagnostics':len(legacy),
         'registered_read_files':len(reader.files),'missing_files':len(set(reader.missing)),
         'other_worktrees_unchanged':unchanged},indent=2))


def old_document_and_positive_audit(reader):
    document_rows=[]
    roots=[ASSETS/'results/realizability_pilot'/n for n in [
      'p1_action_selection_exploratory_20261010','p1_continuous_revisit_actions_20261010',
      'p1_continuous_boundary_review_20261012','p1_doc79_synchronous_revisit_validation_20261012',
      'p1_doc80_offline_research_convergence_20261013']]
    for root in roots:
        for name in ['README.md','STATUS.md','REVIEW_PACKET.md']:
            p=root/name;available=p.is_file()
            if available:reader.register(p)
            document_rows.append({'path':str(p),'available':available,'sha256':sha(p) if available else None,
                                  'read_only':True,'missing_is_not_synthesized':True})
        for p in root.glob('analysis/*gate*.json'):
            reader.json(p);document_rows.append({'path':str(p),'available':True,'sha256':sha(p),'read_only':True})
    csv_out('audit/archived_document_inventory.csv',document_rows)
    rows=[]
    for trial in [1,2,4]:
        root=ASSETS/('results/phase2b/positive_control/trial_%02d'%trial)
        d=reader.json(root/'positive_control.json');manifest=reader.json(root/'manifest.json')
        before=reader.json(root/'pose_graph_before.json');after=reader.json(root/'pose_graph_after.json')
        g2o=root/'pose_graph.g2o';reader.register(g2o)
        with g2o.open() as f:lines=list(f)
        rows.append({'trial':trial,'source_commit':manifest.get('commits',{}).get('root'),
          'native_accepted_events_during_explicit_revisit':len(d['karto_accepted_loop_events_during_revisit']),
          'resolved_new_nonlocal_marker_edges':len(d['marker_nonlocal_history_link_edges']),
          'final_g2o_nodes':sum(l.startswith('VERTEX_SE2') for l in lines),
          'final_g2o_edges':sum(l.startswith('EDGE_SE2') for l in lines),
          'incremental_graph_nodes_before':before['pose_graph_node_count'],
          'incremental_graph_nodes_after':after['pose_graph_node_count'],
          'positive_control_success_recorded':d['positive_control_success'],
          'claim_scope':'Karto can accept a historical closure; marker-resolved endpoint corroboration; cached graph alone stale',
          'measurement_limitation':'not synchronous before/after; not a GT improvement or A1/A2 policy comparison'})
    csv_out('audit/positive_control_raw_verification.csv',rows)


if __name__=='__main__':main()
