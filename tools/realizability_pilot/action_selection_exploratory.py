#!/usr/bin/python3
"""Independent descriptive analysis authorized 2026-10-10. Never launches ROS.

Reads incomplete CD Amendment 1 results without invoking or altering its locked
analysis pipeline. Writes only the new exploratory result root.
"""
import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
from scipy.linalg import cho_factor, cho_solve
import se2_information as reference

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / 'results/realizability_pilot'
CD = PILOT / 'p1_context_disentangle_confirmatory_amendment1_20260930'
ORIGINAL = PILOT / 'p1_context_disentangle_confirmatory_20260930'
V14 = PILOT / 'p1_v14_confirmatory_20260928'
OUT = PILOT / 'p1_action_selection_exploratory_20261010'
ARMS = ('D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH')
READ_HASHES = {}
GAPS = []

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def text(path):
    path = Path(path)
    READ_HASHES[str(path.relative_to(ROOT))] = digest(path)
    return path.read_text()

def load(path):
    return json.loads(text(path))

def jsonl(path):
    return [json.loads(line) for line in text(path).splitlines() if line.strip()]

def save(path, data):
    path = Path(path).resolve()
    if OUT.resolve() not in path.parents: raise ValueError('output outside independent result root')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')

def table(name, rows):
    rows = list(rows)
    path = OUT / 'analysis' / (name + '.csv')
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

def angle(value):
    return math.atan2(math.sin(value), math.cos(value))

def pose(node):
    return np.array([node['x'], node['y'], node['theta']], dtype=float)

def jacobian(a, b):
    c, s = math.cos(a[2]), math.sin(a[2]); dx, dy = b[0] - a[0], b[1] - a[1]
    return np.array([[-c, -s, -s*dx+c*dy, c, s, 0.],
                     [s, -c, -c*dx-s*dy, -s, c, 0.],
                     [0., 0., -1., 0., 0., 1.]])

def information(graph, exclude=(), historical_poses=None):
    nodes = {int(n['state_id']): n for n in graph['nodes']}
    ids = sorted(nodes); position = {i: j for j, i in enumerate(ids)}
    h = np.zeros((3*len(ids), 3*len(ids))); clipped = 0; eigmins = []
    for edge in graph['edges']:
        if edge['index'] in exclude: continue
        a, b = int(edge['source_state_id']), int(edge['target_state_id'])
        covariance = np.asarray(edge['covariance_3x3'], float)
        covariance = (covariance + covariance.T) / 2.
        eig, vectors = np.linalg.eigh(covariance)
        floor = max(1e-9, float(np.max(np.abs(eig))) * 1e-12)
        clipped += int(np.any(eig < floor)); eigmins.append(float(eig.min()))
        omega = (vectors / np.maximum(eig, floor)) @ vectors.T
        pa = historical_poses.get(a, pose(nodes[a])) if historical_poses else pose(nodes[a])
        pb = historical_poses.get(b, pose(nodes[b])) if historical_poses else pose(nodes[b])
        j = jacobian(pa, pb)
        ix = [3*position[a]+k for k in range(3)] + [3*position[b]+k for k in range(3)]
        h[np.ix_(ix, ix)] += j.T @ omega @ j
    return (h+h.T)/2., ids, {'covariance_clipped_edges': clipped,
                            'minimum_edge_covariance_eigenvalue': min(eigmins) if eigmins else None}

def score(graph, target_ids, exclude=(), historical_poses=None, crosscheck=False):
    h, ids, checks = information(graph, exclude, historical_poses)
    if len(target_ids) != 5 or ids[0] in target_ids: raise ValueError('invalid target/root contract')
    reduced = h[3:, 3:]
    eigen = np.linalg.eigvalsh(reduced)
    if eigen.min() <= max(float(abs(eigen).max()), 1.) * 1e-10:
        raise np.linalg.LinAlgError('singular or ill-conditioned anchored information')
    columns = [3*ids.index(i)+k-3 for i in target_ids for k in range(3)]
    select = np.eye(reduced.shape[0])[:, columns]
    solved = cho_solve(cho_factor(reduced, lower=True), select)
    marginal = (solved[columns, :] + solved[columns, :].T)/2.
    sign, logdet = np.linalg.slogdet(marginal)
    if sign <= 0: raise ValueError('nonpositive target marginal')
    j = -float(logdet)/15.
    checks.update(target_dimension=15, root_state_id=ids[0], target_state_ids=list(target_ids),
                  minimum_reduced_eigenvalue=float(eigen.min()),
                  reduced_condition_number=float(eigen.max()/eigen.min()),
                  target_covariance_trace=float(np.trace(marginal)))
    if crosscheck:
        r, _ = reference.v13_target_information_score(h, [ids.index(i) for i in target_ids])
        checks['cholesky_vs_repository_inverse_abs_difference'] = abs(r-j)
    return j, checks

def new_edges(before, after):
    original = {e['index']: e for e in before['edges']}
    return [e for e in after['edges'] if e['index'] not in original]

def keyscans(records, prefix_count, expected):
    # LocalizedScan.x/y/yaw are float32 on the ROS wire. Near 0.52 rad, using
    # the pre-serialization JSON doubles changes the predicted keyframe count.
    records=[{**r, **{k:float(np.float32(r[k])) for k in ('x','y','yaw')}} for r in records]
    previous = records[prefix_count-1]; accepted = []
    for index, row in enumerate(records[prefix_count:]):
        yaw = abs(angle(row['yaw'] - previous['yaw']))
        distance2 = (row['x']-previous['x'])**2+(row['y']-previous['y'])**2
        if yaw >= 0.52 or distance2 >= 1.-1e-6:
            accepted.append(index); previous = row
    return accepted, len(accepted) == expected

def hops_before(graph):
    adj = defaultdict(set); output = {}
    for edge in sorted(graph['edges'], key=lambda e:e['index']):
        a, b = edge['source_state_id'], edge['target_state_id']; queue = deque([(a,0)]); seen={a}; hop=None
        while queue:
            here, steps = queue.popleft()
            if here == b: hop=steps; break
            for nxt in adj[here]-seen: seen.add(nxt); queue.append((nxt,steps+1))
        output[edge['index']] = hop; adj[a].add(b); adj[b].add(a)
    return output

def metric_branch(block, row, captures, protocol_label):
    directory = ROOT / row['selected_replay']; before=load(directory/'graph_pre.json'); final=load(directory/'graph_final.json')
    for filename, key in [('graph_pre.json','graph_pre_sha256'), ('graph_final.json','graph_final_sha256')]:
        if row.get(key) and digest(directory/filename) != row[key]: raise ValueError('ledger graph hash changed')
    targets=block['target_state_ids']; old={n['state_id']:n for n in before['nodes']}; nodes={n['state_id']:n for n in final['nodes']}
    for state, unique in zip(targets, block['target_unique_ids']):
        if old[state]['unique_id'] != unique or nodes[state]['unique_id'] != unique: raise ValueError('target identity mismatch')
    j, checks=score(final,targets,crosscheck=True); pre_j,_=score(before,targets)
    added=new_edges(before,final); historical=[e for e in added if {e['source_state_id'],e['target_state_id']}&old.keys()]
    target_edges=[e for e in historical if {e['source_state_id'],e['target_state_id']}&set(targets)]
    nonlocal_edges=[e for e in historical if abs(e['target_state_id']-e['source_state_id'])>1]
    records=jsonl(directory/'edge_provenance.jsonl')
    provenance={int(e['creation_sequence'])-1:e for e in records if e.get('record_type')=='constraint_created'}
    inherited={e['index']:e for e in before['edges']}
    changed_inherited=sum(e!=inherited[e['index']] for e in final['edges'] if e['index'] in inherited)
    capture_row=captures[(block['block_id'],row['arm'])]; capture_dir=ROOT/capture_row['selected_attempt']
    capture=load(capture_dir/'capture_result.json'); raw=jsonl(capture_dir/'scientific_treatment_stream.jsonl')
    combined_path=directory.parent/'combined_stream.jsonl'
    combined=jsonl(combined_path) if combined_path.exists() else []
    prefix_count=int(row['prefix_record_count']); accepted, count_ok=keyscans(combined,prefix_count,len(nodes)-len(old)) if combined else ([],False)
    completion=float(capture['maneuver_completion_time']); start=float(capture['treatment_start_time']); end=float(raw[-1]['stamp'])
    completion_count=sum(start<=r['stamp']<=completion for r in raw)
    accepted_moving=sum(raw[i]['stamp']<=completion for i in accepted) if count_ok else None
    stitch=load(directory.parent/'stitch_report.json'); prefix_tail=stitch['prefix_terminal_odom_laser']; native_first=stitch['probe_initial_odom_laser']
    descriptor_path=capture_dir/'pre_treatment_descriptor.json'
    descriptor=load(descriptor_path) if descriptor_path.exists() else {}
    fixed_poses={i:pose(n) for i,n in old.items()}
    fixed_j,_=score(final,targets,historical_poses=fixed_poses)
    removed_j,_=score(final,targets,exclude={e['index'] for e in nonlocal_edges},historical_poses=fixed_poses)
    family=Counter(provenance.get(e['index'],{}).get('creation_provenance','UNRECORDED') for e in added)
    historical_family=Counter(provenance.get(e['index'],{}).get('creation_provenance','UNRECORDED') for e in nonlocal_edges)
    result={'protocol':protocol_label,'block_id':block['block_id'],'target':block['target_label'],'seed':block['seed'],'arm':row['arm'],
            'J_T':j,'J_pre':pre_j,'gain_from_pre':j-pre_j,'gain_geometric_covariance_reduction_percent':100.*(-math.expm1(pre_j-j)),
            'J_shared_historical_linearization':fixed_j,'nonlocal_history_ablation_gain':fixed_j-removed_j,
            'accepted_keyframes':len(nodes)-len(old),'new_edges':len(added),'target_history_edges':len(target_edges),
            'historical_crosscut_edges_including_sequential_boundary':len(historical),'nonlocal_history_edges':len(nonlocal_edges),
            'changed_inherited_edges':changed_inherited,'families':json.dumps(dict(family),sort_keys=True),
            'historical_families':json.dumps(dict(historical_family),sort_keys=True),
            'explicit_history_loops':sum(provenance.get(e['index'],{}).get('creation_provenance')=='TRY_CLOSE_LOOP' for e in nonlocal_edges),
            'actual_yaw_rad':capture.get('actual_cumulative_yaw_rad',capture.get('treatment_yaw_excursion_rad')),
            'maneuver_s':completion-start,'total_observation_s':end-start,'first_to_last_scan_s':end-float(raw[0]['stamp']),
            'static_tail_s':end-completion,'completion_scan_index':completion_count,'post_maneuver_scan_count':len(raw)-completion_count,
            'N':len(raw),'keyframe_reconstruction_count_matches':count_ok,'keyframes_during_maneuver':accepted_moving,
            'keyframes_after_maneuver':len(accepted)-accepted_moving if count_ok else None,
            'native_prefix_to_probe_start_distance_m':math.hypot(prefix_tail[0]-native_first[0],prefix_tail[1]-native_first[1]),
            'stitch_yaw_abs_rad':abs(stitch['se2_alignment_yaw_rad']),
            'native_probe_x':native_first[0],'native_probe_y':native_first[1],
            'stitched_probe_x':prefix_tail[0],'stitched_probe_y':prefix_tail[1],
            'descriptor_strict_pre':descriptor.get('strictly_pretreatment'),
            'descriptor_timestamp_pre_action':float(descriptor['scan_stamp'])<=start if descriptor else None,
            'pre_graph_sha256':digest(directory/'graph_pre.json'),'graph_final_sha256':digest(directory/'graph_final.json')}
    anchor=block['anchor_state_id']
    result['replay_first_new_to_frozen_anchor_m']=(math.hypot(nodes[min(set(nodes)-set(old))]['x']-old[anchor]['x'],nodes[min(set(nodes)-set(old))]['y']-old[anchor]['y']) if set(nodes)-set(old) else None)
    quality=[]; hopping=hops_before(final)
    for edge in added:
        prov=provenance.get(edge['index'],{}); cov=np.array(edge['covariance_3x3']); eig=np.linalg.eigvalsh(cov)
        if edge in nonlocal_edges:
            drop_j,_=score(final,targets,exclude={edge['index']},historical_poses=fixed_poses)
            unique_gain=fixed_j-drop_j
        else: unique_gain=None
        a,b=edge['source_state_id'],edge['target_state_id']
        quality.append({'protocol':protocol_label,'block_id':block['block_id'],'target':block['target_label'],'arm':row['arm'],
                        'edge_index':edge['index'],'source':a,'destination':b,'state_index_gap':abs(b-a),
                        'historical_source':a in old,'historical_destination':b in old,'touches_target':edge in target_edges,
                        'nonlocal_history':edge in nonlocal_edges,'creation_provenance':prov.get('creation_provenance','UNRECORDED'),
                        'solver_add_constraint_called':prov.get('solver_add_constraint_called'), 'match_response':prov.get('match_response'),
                        'cov_min_eig':float(eig.min()),'cov_max_eig':float(eig.max()),'cov_xy_trace':float(np.trace(cov[:2,:2])),
                        'own_information_logdet':float(-np.linalg.slogdet(cov)[1]),
                        'hops_before_insertion':hopping[edge['index']], 'unique_target_score_contribution':unique_gain,
                        'measurement_dx':edge['measurement']['dx'],'measurement_dy':edge['measurement']['dy'],'measurement_dtheta':edge['measurement']['dtheta']})
    checks.update(block_id=block['block_id'],arm=row['arm'],protocol=protocol_label,
                  target_unique_ids=block['target_unique_ids'], prefix_processed_count=row.get('prefix_record_count'),
                  processed_final_count=row.get('processed_final_count'),
                  provenance_edge_identity_reconciled=all((provenance.get(e['index'],{}).get('source_state_id'),provenance.get(e['index'],{}).get('target_state_id'))==(e['source_state_id'],e['target_state_id']) for e in added))
    return result,quality,checks

def complete_blocks(root):
    manifest=load(root/'qualification/frozen_history_manifest.json'); blocks=[b for values in manifest['selected_blocks'].values() for b in values]
    ledger=load(root/'collection/backend_replay_ledger.json'); captures=load(root/'collection/physical_collection_ledger.json')
    capture_map={(r['block_id'],r['arm']):r for r in captures}; row_map=defaultdict(dict)
    for row in ledger: row_map[row['block_id']][row['arm']]=row
    expected=ARMS if root==CD else ('A1_DWELL','A3_MIN_TRIGGER','A2_SWEEP90')
    usable=[]; missing=[]
    for block in blocks:
        entries=row_map[block['block_id']]
        okay=all(a in entries and entries[a].get('selected_replay') and (ROOT/entries[a]['selected_replay']/'graph_final.json').is_file() for a in expected)
        if okay: usable.append((block,[entries[a] for a in expected]))
        else: missing.append({'block_id':block['block_id'],'target':block['target_label'],'seed':block['seed'],
                              'reason':'missing complete three-arm backend graphs','arms':{a:entries.get(a,{}).get('status','MISSING') for a in expected}})
    return usable,capture_map,missing,blocks

def gt_sanity(block, rows):
    source=ORIGINAL/'qualification/candidates'/block['target_label']/('seed_'+str(block['seed']))/'attempt_01'
    slam_path=source/'trajectory_slam.txt'; gt_path=source/'trajectory_gt.txt'
    if not slam_path.exists() or not gt_path.exists(): return {'status':'MISSING_SOURCE_TRAJECTORY'},[]
    slam=np.array([[float(v) for v in l.split()] for l in text(slam_path).splitlines() if l.strip()]);gt=np.array([[float(v) for v in l.split()] for l in text(gt_path).splitlines() if l.strip()])
    lookup={row[0]:row for row in gt}; prefix=load(ROOT/rows[0]['selected_replay']/'graph_pre.json'); nodes=sorted(prefix['nodes'],key=lambda n:n['state_id'])
    if len(slam)!=len(nodes): return {'status':'SOURCE_GRAPH_COUNT_MISMATCH'},[]
    raw=jsonl(source/'replay_stream.jsonl'); canonical=jsonl(source.parent/'canonical_prefix.jsonl')
    if len(raw)!=len(nodes) or len(canonical)!=len(nodes): return {'status':'SOURCE_SCAN_COUNT_MISMATCH'},[]
    # The recorded /karto_out LaserScan headers are stamp0. Do not infer GT time
    # from those. Instead verify each original state-index / stored trajectory
    # pose against the simultaneously archived corrected graph, then use that
    # trajectory row's original acquisition timestamp for the exact GT join.
    snapshot=load(source/'pose_graph_before.json')
    archive_nodes={int(n['id']):n for n in snapshot['slam_path']}
    if sorted(archive_nodes)!=[n['state_id'] for n in nodes]: return {'status':'SOURCE_STATE_ID_ORDER_NOT_VERIFIED'},[]
    source_pose_error=max(math.hypot(archive_nodes[i]['x']-r[1],archive_nodes[i]['y']-r[2]) for i,r in enumerate(slam))
    # pubPathGT.cpp writes the double /slam_path poses with default ostream
    # precision (six significant digits). Verify this exact serialization,
    # rather than choosing a numerical tolerance after seeing the errors.
    serialized_xy_match=all(float(format(archive_nodes[i][key],'.6g'))==r[column]
                            for i,r in enumerate(slam) for key,column in [('x',1),('y',2)])
    if not serialized_xy_match: return {'status':'SOURCE_POSE_ROW_MAPPING_FAILED','maximum_error_m':source_pose_error},[]
    if any(slam[i][0] not in lookup for i in block['target_state_ids']): return {'status':'TARGET_GT_TIMESTAMP_MISSING'},[]
    from v14_estimator_sanity import freeze_world_gauge,target_state_errors
    pre_poses=[pose(n).tolist() for n in nodes]; paired_gt={}
    for i,row in enumerate(slam):
        if row[0] not in lookup: continue
        q=lookup[row[0]];paired_gt[i]=[q[1],q[2],2.*math.atan2(q[6],q[7])]
    matched=sorted(paired_gt)
    gauge=freeze_world_gauge([pre_poses[i] for i in matched],[paired_gt[i] for i in matched]); ids=[n['state_id'] for n in nodes]
    target_gt=[paired_gt[ids.index(i)] for i in block['target_state_ids']]
    before=target_state_errors([pose(nodes[ids.index(i)]) for i in block['target_state_ids']],target_gt,gauge)
    results=[]
    for row in rows:
        final=load(ROOT/row['selected_replay']/'graph_final.json'); final_nodes={n['state_id']:n for n in final['nodes']}
        after=target_state_errors([pose(final_nodes[i]) for i in block['target_state_ids']],target_gt,gauge)
        results.append({'block_id':block['block_id'],'target':block['target_label'],'arm':row['arm'],
                        'pre_target_position_rmse_m':before['translation_rmse_m'],'post_target_position_rmse_m':after['translation_rmse_m'],
                        'position_improvement_m':before['translation_rmse_m']-after['translation_rmse_m'],
                        'pre_heading_rmse_rad':before['heading_rmse_rad'],'post_heading_rmse_rad':after['heading_rmse_rad'],
                        'heading_improvement_rad':before['heading_rmse_rad']-after['heading_rmse_rad']})
    return {'status':'MATCHED_HISTORICAL_TARGET_GT_ONLY','gauge':gauge,'paired_history_poses':len(matched),
            'unmatched_history_state_ids':sorted(set(range(len(nodes)))-set(matched)),
            'source_state_to_trajectory_xy_max_error_m':source_pose_error,
            'source_pose_identity_rule':'exact default ostream six-significant-digit serialization of archived /slam_path x/y',
            'timestamp_source':'original stored trajectory row after archived state-pose identity check; not stamp0 /karto_out stream',
            'new_C_GT_not_used':'suffix-only transform does not share historical gauge; no valid whole-branch ATE/RPE',
            'frame_note':'GT history trajectory is recorded laser trajectory, not base; +0.2m mounting as capture code'},results

def stats(values):
    a=np.array(values,float)
    return {'n':len(a),'mean':float(a.mean()),'median':float(np.median(a)),
            'sd':float(a.std(ddof=1)) if len(a)>1 else 0.,'min':float(a.min()),'max':float(a.max())}

def summarize(branches):
    grouped=defaultdict(dict)
    for r in branches: grouped[r['block_id']][r['arm']]=r
    rows=[]; endpoints=[]
    for block,arms in grouped.items():
        if not all(a in arms for a in ARMS):continue
        j=[arms[a]['J_T'] for a in ARMS];best=max(range(3),key=lambda i:j[i])
        row={'block_id':block,'target':arms[ARMS[0]]['target'],'seed':arms[ARMS[0]]['seed'],
             **{a+'_J_T':arms[a]['J_T'] for a in ARMS},'D1_minus_D0':j[1]-j[0],
             'D2_minus_D1':j[2]-j[1],'D2_minus_D0':j[2]-j[0],
             'posthoc_best_arm':ARMS[best],'oracle_minus_fixed_D2':max(j)-j[2],
             'D2_minus_D1_shared_history_linearization':arms[ARMS[2]]['J_shared_historical_linearization']-arms[ARMS[1]]['J_shared_historical_linearization'],
             'all_pre_graph_hashes_equal':len({r['pre_graph_sha256'] for r in arms.values()})==1,
             'all_N_equal_347':all(r['N']==347 for r in arms.values())}
        rows.append(row)
    summary={}
    for target in ('target_A','target_B','all'):
        selected=[r for r in rows if target=='all' or r['target']==target]
        summary[target]={'contrasts':{k:stats([r[k] for r in selected]) for k in ('D1_minus_D0','D2_minus_D1','D2_minus_D0','oracle_minus_fixed_D2')},
                         'best_counts':dict(Counter(r['posthoc_best_arm'] for r in selected)),
                         'D2_above_D1_count':sum(r['D2_minus_D1']>0 for r in selected),
                         'D2_above_D0_count':sum(r['D2_minus_D0']>0 for r in selected),
                         'D1_above_D0_count':sum(r['D1_minus_D0']>0 for r in selected),
                         'pairing_units':len(selected)}
    table('cd_paired_history_results',rows);save(OUT/'analysis/cd_summary.json',summary)
    return rows,summary

def repeatability(blocks):
    f2=PILOT/'p1_cd_prefix_forensic_f2_20261008';plan=load(f2/'technical/prefix_only_run_manifest.json'); byblock={b['block_id']:b for b in blocks};records=[]
    for r in plan['rows']:
        p=f2/'technical/runs'/('run_%02d'%r['ordinal'])/'graph_pre.json'
        if not p.exists(): GAPS.append(str(p.relative_to(ROOT)));continue
        try:j,_=score(load(p),byblock[r['block']]['target_state_ids'])
        except Exception as exc: GAPS.append(str(p)+': '+str(exc));continue
        records.append({'evidence':'production_prefix_only','block_id':r['block'],'run':r['ordinal'],'mode':r['mode'],'J_T':j})
    # Existing full-stream repetitions, not a new replay nor a CD branch repeat.
    full=PILOT/'p1_dir_dec_v8_20260916/replay_same_input_recheck'
    source=PILOT/'p1_dir_dec_v8_20260916/replay_source/episodes/0001_replay_source/attempt_01/frozen_target.json'
    if source.exists():
        target=load(source).get('historical_scan_ids',[])
        if len(target)==5:
            for p in sorted((full/'runs').glob('graph_*.json')):
                j,_=score(load(p),target);records.append({'evidence':'legacy_full_stream_not_CD','block_id':'v8_source','run':p.stem,'J_T':j})
    else:GAPS.append('legacy full-stream frozen target not present: '+str(source.relative_to(ROOT)))
    table('existing_repeated_graph_J_T',records)
    groups=defaultdict(list)
    for r in records:groups[(r['evidence'],r['block_id'])].append(r['J_T'])
    save(OUT/'analysis/repeatability_summary.json',{
        str(k):{**stats(v),'range':max(v)-min(v),'can_bound_CD_final_branch_noise':False} for k,v in groups.items()})

def plots(branches,paired):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    OUT.joinpath('figures').mkdir(exist_ok=True)
    colors={'D0_ZERO':'#888888','D1_THRESHOLD':'#2878b5','D2_HIGH':'#d95319'}
    fig,axs=plt.subplots(1,2,figsize=(11,4.4),sharey=True)
    for ax,target in zip(axs,('target_A','target_B')):
        rows=[r for r in paired if r['target']==target]
        for r in rows:
            ax.plot([0,1,2],[0,r['D1_minus_D0'],r['D2_minus_D0']],'-o',lw=1,ms=3,alpha=.75,label=r['block_id'].split('_')[-1])
        ax.set_xticks([0,1,2],['D0: static','D1: 1.088 rad','D2: pi rad']);ax.set_title(target+' (paired histories)');ax.grid(alpha=.2);ax.legend(ncol=2,fontsize=8)
    axs[0].set_ylabel('Final J_T minus the same-history D0')
    fig.suptitle('CD: 347 scans per arm; each line is one history');fig.tight_layout();fig.savefig(OUT/'figures/01_paired_gains.png',dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4))
    for ax,target in zip(axs,('target_A','target_B')):
        subset=[r for r in branches if r['target']==target];x=np.arange(3)
        movement=[np.mean([r['maneuver_s'] for r in subset if r['arm']==a]) for a in ARMS]
        total=[np.mean([r['total_observation_s'] for r in subset if r['arm']==a]) for a in ARMS]
        ax.bar(x,movement,color=[colors[a] for a in ARMS],label='Maneuver');ax.bar(x,np.array(total)-movement,bottom=movement,color='#dddddd',label='Post-maneuver observation')
        ax.set_xticks(x,['D0','D1','D2']);ax.set_ylabel('Simulated seconds to final 347-scan endpoint');ax.set_title(target);ax.legend(fontsize=8);ax.set_ylim(0,38)
    fig.tight_layout();fig.savefig(OUT/'figures/02_actual_budget.png',dpi=180);plt.close(fig)
    row=next(r for r in branches if r['block_id']=='target_A_H2' and r['arm']=='D2_HIGH')
    p=CD/'collection/replays/target_A/target_A_H2/D2_HIGH/attempt_01';g=load(p/'graph_pre.json');nodes={n['state_id']:n for n in g['nodes']};targets=[13,16,18,21,25]
    fig,ax=plt.subplots(figsize=(7,6));ax.plot([n['x'] for n in g['nodes']],[n['y'] for n in g['nodes']],'.-',color='#888888',label='Common prefix (estimated laser poses)')
    ax.scatter([nodes[i]['x'] for i in targets],[nodes[i]['y'] for i in targets],c='#2878b5',s=55,label='Frozen target states')
    ax.scatter(row['native_probe_x'],row['native_probe_y'],marker='*',s=180,c='green',label='Native treatment start odom')
    ax.scatter(row['stitched_probe_x'],row['stitched_probe_y'],marker='x',s=110,c='#d95319',label='Stitched treatment start odom')
    ax.annotate('',xy=(row['stitched_probe_x'],row['stitched_probe_y']),xytext=(row['native_probe_x'],row['native_probe_y']),arrowprops={'arrowstyle':'->','linestyle':'--','color':'black'})
    ax.set_aspect('equal');ax.set_xlabel('x [m]');ax.set_ylabel('y [m]');ax.legend(fontsize=8);ax.grid(alpha=.2);ax.set_title('CD A H2: suffix-only registration moves the observation\nPrefix stays fixed; this is not a whole-trajectory gauge transform')
    fig.tight_layout();fig.savefig(OUT/'figures/03_registration_audit.png',dpi=180);plt.close(fig)

def derived_audits(branches, paired, factors, checks, gt, vrows):
    """Compact interpretation inputs, with no fitted subgroup or selector."""
    import scipy
    import matplotlib
    for block in {r['block_id'] for r in branches}:
        rr=[r for r in branches if r['block_id']==block]
        assert len({r['pre_graph_sha256'] for r in rr})==1
        assert all(r['N']==347 and r['keyframe_reconstruction_count_matches'] for r in rr)
        assert all(r['descriptor_timestamp_pre_action'] for r in rr)
    common_rows=[]
    for pair in paired:
        rr={r['arm']:r for r in branches if r['block_id']==pair['block_id']}
        js=[rr[a]['J_shared_historical_linearization'] for a in ARMS]
        common_rows.append({'block_id':pair['block_id'],'target':pair['target'],
                            'shared_H_D1_minus_D0':js[1]-js[0], 'shared_H_D2_minus_D1':js[2]-js[1],
                            'shared_H_D2_minus_D0':js[2]-js[0],
                            'shared_H_best_arm':ARMS[int(np.argmax(js))],
                            'original_best_arm':pair['posthoc_best_arm']})
    table('common_historical_linearization_sensitivity',common_rows)
    vpaired=[]
    for block in sorted({r['block_id'] for r in vrows}):
        rr={r['arm']:r for r in vrows if r['block_id']==block}
        vpaired.append({'block_id':block,'target':next(iter(rr.values()))['target'],
                        'A2_minus_A3_J_T':rr['A2_SWEEP90']['J_T']-rr['A3_MIN_TRIGGER']['J_T'],
                        'A3_minus_A1_J_T':rr['A3_MIN_TRIGGER']['J_T']-rr['A1_DWELL']['J_T'],
                        'A2_minus_A3_nonlocal_edges':rr['A2_SWEEP90']['nonlocal_history_edges']-rr['A3_MIN_TRIGGER']['nonlocal_history_edges']})
    table('v14_paired_results',vpaired)
    gt_summary={}
    for target in ('target_A','target_B'):
        gt_summary[target]={a:stats([r['position_improvement_m'] for r in gt if r['target']==target and r['arm']==a]) for a in ARMS}
    save(OUT/'analysis/historical_target_GT_summary.json',gt_summary)
    save(OUT/'analysis/numerical_and_mechanism_summary.json',{
        'same_pre_graph_hash_within_each_complete_group':True,
        'cholesky_vs_repository_max_abs_difference':max(r['cholesky_vs_repository_inverse_abs_difference'] for r in checks),
        'clipped_covariances':sum(r['covariance_clipped_edges'] for r in checks),
        'all_provenance_endpoint_identities_match':all(r['provenance_edge_identity_reconciled'] for r in checks),
        'all_inherited_edges_unchanged':all(r['changed_inherited_edges']==0 for r in branches),
        'common_historical_linearization_best_arm_unchanged':all(r['shared_H_best_arm']==r['original_best_arm'] for r in common_rows),
        'new_nonlocal_history_provenance':dict(Counter(r['creation_provenance'] for r in factors if r['nonlocal_history'])),
        'new_nonlocal_history_sources':sorted({r['source'] for r in factors if r['nonlocal_history']}),
        'all_new_edges_inserted_in_solver':all(r['solver_add_constraint_called'] for r in factors),
        'total_target_history_edges':sum(r['target_history_edges'] for r in branches),
        'total_keyframes_after_maneuver':sum(r['keyframes_after_maneuver'] for r in branches),
        'registration_distance_m':stats([r['native_prefix_to_probe_start_distance_m'] for r in branches])})
    save(OUT/'analysis/environment.json',{'python':sys.version,'python_executable':sys.executable,
        'numpy':np.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__,
        'ros_processes_launched':False,'units':{'time':'recorded simulation seconds','yaw':'radian','position':'metre'},
        'analysis_design':'complete-history paired descriptive analysis; no tests, optimized thresholds or fitted selector'})

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protected=[]
    for r in (CD,ORIGINAL,V14,PILOT/'p1_v14_heterogeneity_20260928'):
        for p in sorted(r.rglob('*')):
            if p.is_file() and (p.name.endswith('LOCK.json') or 'preregistration' in p.parts or p.name=='final_gate.json' or p.name=='pipeline_state.json'):
                text(p);protected.append(str(p.relative_to(ROOT)))
    usable,captures,missing,blocks=complete_blocks(CD)
    save(OUT/'analysis/data_availability.json',{'planned_histories':len(blocks),'complete_histories':len(usable),'successful_branches':sum(len(r) for b,r in usable),'missing':missing,
                                              'authorization':'2026-10-10 explicit user permission for new exploratory Amendment1 analysis; original locks unchanged'})
    branches=[];factors=[];checks=[];gt=[];gt_reports={}
    for b,entries in usable:
        for row in entries:
            metric,edges,audit=metric_branch(b,row,captures,'CD');branches.append(metric);factors.extend(edges);checks.append(audit)
        status,values=gt_sanity(b,entries);gt_reports[b['block_id']]=status;gt.extend(values)
    paired,summary=summarize(branches)
    table('cd_branches',branches);table('cd_new_factor_details',factors);table('information_construction_audit',checks);table('historical_target_GT_sanity',gt)
    save(OUT/'analysis/gt_pairing_audit.json',gt_reports)
    v_usable,v_cap,v_missing,_=complete_blocks(V14);vrows=[];vfactors=[]
    for b,entries in v_usable:
        for row in entries:
            metric,edges,audit=metric_branch(b,row,v_cap,'v14');vrows.append(metric);vfactors.extend(edges)
    table('v14_recomputed_branches',vrows);table('v14_recomputed_factors',vfactors)
    overlap=[]
    for protocol,rows,ff,order in [('CD',branches,factors,ARMS),('v14',vrows,vfactors,('A1_DWELL','A3_MIN_TRIGGER','A2_SWEEP90'))]:
        for b in sorted({r['block_id'] for r in rows}):
            for low,high in zip(order,order[1:]):
                a={(f['source'],f['destination']) for f in ff if f['block_id']==b and f['arm']==low and f['nonlocal_history']}
                c={(f['source'],f['destination']) for f in ff if f['block_id']==b and f['arm']==high and f['nonlocal_history']}
                # Destination IDs can refer to different scan orientations across actions.
                sa={x for pair in a for x in pair[:1]};sc={x for pair in c for x in pair[:1]}
                overlap.append({'protocol':protocol,'block_id':b,'comparison':high+' minus '+low,
                                'low_edges':len(a),'high_edges':len(c),'common_id_pairs':len(a&c),'low_only_id_pairs':len(a-c),'high_only_id_pairs':len(c-a),
                                'common_old_source_ids':json.dumps(sorted(sa&sc)),'low_only_old_source_ids':json.dumps(sorted(sa-sc)), 'high_only_old_source_ids':json.dumps(sorted(sc-sa)),
                                'endpoint_pair_identity_caveat':'new scan ids are ordinal, not common physical observations across arms'})
    table('historical_factor_set_comparison',overlap)
    repeatability(blocks);plots(branches,paired)
    derived_audits(branches,paired,factors,checks,gt,vrows)
    summary_budget={}
    for target in ('target_A','target_B'):
        summary_budget[target]={a:{k:stats([r[k] for r in branches if r['target']==target and r['arm']==a]) for k in ('actual_yaw_rad','maneuver_s','total_observation_s','static_tail_s','post_maneuver_scan_count','accepted_keyframes','nonlocal_history_edges','target_history_edges','nonlocal_history_ablation_gain')} for a in ARMS}
    save(OUT/'analysis/budget_mechanism_summary.json',summary_budget)
    mismatches=[p for p,v in READ_HASHES.items() if digest(ROOT/p)!=v]
    save(OUT/'analysis/input_integrity_manifest.json',{'read_file_sha256':READ_HASHES,'protected_lock_and_gate_files':protected,'after_read_all_unchanged':not mismatches,'mismatches':mismatches,
                                                     'repo_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=str(ROOT),text=True).strip(),
                                                     'analysis_code_sha256':digest(Path(__file__)), 'gaps':GAPS})
    assert not mismatches
    print(json.dumps({'complete_histories':len(usable),'missing':missing,'summary':summary,
                      'CD_target_constraint_total':sum(r['target_history_edges'] for r in branches),
                      'protected_inputs_unchanged':not mismatches,'GT_status_counts':dict(Counter(r['status'] for r in gt_reports.values()))},indent=2))

if __name__=='__main__':main()
