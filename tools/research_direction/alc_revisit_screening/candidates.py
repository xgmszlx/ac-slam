"""Pure geometric screening, NOT a planner and NOT a counterfactual simulator.

Candidate functions accept a sanitized single-episode pre-decision bundle only.
Missing online maps -> hypotheses, never certified safe motion candidates.
Historical keyframe chords are not treated as the actual recorded drive path.
"""
import math
from collections import defaultdict
from common import base_pose,distance,path_length,wrap

ALLOWED_STAGES={'A1':'G_arrival','A2':'G_before_return'}
UNOBSERVED='COUNTERFACTUAL_OUTCOME_UNOBSERVED'


def validate_bundle(b,problem):
    if b['problem']!=problem or b['boundary']!=ALLOWED_STAGES[problem]:
        raise ValueError('Wrong decision stage')
    if not b['episode_id'] or b['frame']!='map_base_from_laser':raise ValueError('Episode/frame missing')
    if set(b)&{'gt','post_graph','outcomes','final_map','stage_world_map'}:raise ValueError('Forbidden decision input')
    if not b['watermark_validated']:raise ValueError('Unvalidated watermark')
    if b['graph']['run_id']!=b['run_id']:raise ValueError('Graph from another episode')
    if len(b['graph']['nodes'])!=b['export_node_count'] or len(b['graph']['edges'])!=b['export_edge_count']:
        raise ValueError('Graph from another boundary')
    if b['online_map'] is not None and b['online_map'].get('source')!='ONLINE_PRE_DECISION':
        raise ValueError('Ground truth/final map cannot be a decision input')
    nodes=b['graph']['nodes'];ids=[n['state_id'] for n in nodes];uids=[n['unique_id'] for n in nodes]
    if len(ids)!=len(set(ids)) or len(uids)!=len(set(uids)):raise ValueError('Duplicate state/UID')
    lookup={n['state_id']:n for n in nodes}
    if not set(b['history_state_ids']).issubset(lookup):raise ValueError('Missing historic state')
    if problem=='A2' and set(b['history_state_ids'])!=set(ids):raise ValueError('Return/post states in before-return history')
    for e in b['graph']['edges']:
        for side in ['source','target']:
            if e[side+'_state_id'] not in lookup:raise ValueError('Missing edge endpoint')
            if lookup[e[side+'_state_id']]['unique_id']!=e[side+'_unique_id']:raise ValueError('UID mismatch')
    if any(s['stamp']>b['decision_stamp']+1e-9 for s in b['trajectory_pre']):raise ValueError('Future sample')
    if problem=='A2' and 'anchor_state_id' in b:raise ValueError('A2 knows an already-selected target')
    if problem=='A1' and (b['anchor_state_id'] not in lookup or lookup[b['anchor_state_id']]['unique_id']!=b['anchor_unique_id']):
        raise ValueError('Frozen anchor UID mismatch')
    return lookup


def movement_status(online_map):
    # This screen implements no occupancy planner or collision checker. Even an
    # arbitrary provided map object cannot falsely certify a path.
    if online_map is None:return 'NOT_CERTIFIED_PRE_DECISION_MAP_MISSING'
    return 'NOT_CERTIFIED_COLLISION_CHECKER_NOT_IMPLEMENTED'


def unique_geometry(candidates):
    seen={};result=[]
    for c in candidates:
        key=tuple((round(p[0],3),round(p[1],3)) for p in c['path_base'])
        if key in seen and c['kind'] not in ('SKIP','STAY','CONTINUE_EXPLORATION','NO_ALC'):
            c=dict(c,duplicate_of=seen[key],eligibility='DUPLICATE_GEOMETRY')
        else:seen[key]=c['candidate_id']
        result.append(c)
    return result


def kinematic_cost(path,start_yaw):
    headings=[math.atan2(b[1]-a[1],b[0]-a[0]) for a,b in zip(path,path[1:]) if distance(a,b)>1e-6]
    angle=sum(abs(wrap(b-a)) for a,b in zip([start_yaw]+headings,headings))
    length=path_length(path)
    return length,angle,length/.4+angle/.5 # estimates only; explicit assumptions


def historical_support(b,path,radius=1.0):
    lookup={n['state_id']:n for n in b['graph']['nodes']}
    historical=[lookup[i] for i in b['history_state_ids']]
    endpoints=[n['state_id'] for n in historical if any(distance(base_pose(n),p)<=radius for p in path)]
    counts=[sum(distance(base_pose(n),p)<=radius for n in historical) for p in path]
    headings=[abs(wrap(n['theta']-p[2])) for p in path for n in historical if distance(base_pose(n),p)<=radius]
    linked=sum(e['source_state_id'] in endpoints and e['target_state_id'] in endpoints for e in b['graph']['edges'])
    return {'potential_history_state_ids':endpoints,'historical_support_count':len(endpoints),
            'preexisting_internal_edges':linked,'near_history_waypoint_fraction':sum(c>0 for c in counts)/max(1,len(counts)),
            'historical_heading_difference_mean_rad':sum(headings)/len(headings) if headings else None,
            'proxy_definition':'1m historical-pose proximity, not scan overlap or closure probability'}


def make_candidate(b,kind,path,ids,eligibility=None):
    # Facing directions are route tangents for forward differential-drive
    # travel, not reused outgoing historical yaws on the return leg.
    path=[list(p) for p in path]
    for i,p in enumerate(path[:-1]):
        next_p=next((q for q in path[i+1:] if distance(p,q)>1e-6),None)
        if next_p is not None:p[2]=math.atan2(next_p[1]-p[1],next_p[0]-p[0])
    length,turn,time=kinematic_cost(path,b['current_base'][2])
    moving=length>1e-9
    d={'episode_id':b['episode_id'],'problem':b['problem'],'decision_boundary':b['boundary'],
       'decision_stamp':b['decision_stamp'],'candidate_id':b['episode_id']+'_'+kind,'kind':kind,
       'path_base':path,'path_state_ids':ids,'estimated_distance_m':length,'estimated_turn_rad':turn,
       'estimated_motion_time_s':time,'time_model':'v=.4m/s,w=.5rad/s; excludes navigation delay and observation dwell',
       'eligibility':eligibility or (movement_status(b['online_map']) if moving else 'ZERO_MOTION_REFERENCE'),
       'diff_drive_compatibility':'piecewise translate plus in-place turn; footprint clearance unverified' if moving else 'zero extra motion',
       'safety_verified':False if moving else None,'actual_gain':None,'actual_constraint_count':None,
       'outcome_status':UNOBSERVED,'geometric_input':'same pre-decision graph; historic keyframe chords NOT certified driven corridors'}
    d.update(historical_support(b,path));return d


def local_candidates(b):
    lookup=validate_bundle(b,'A1');anchor=b['anchor_state_id'];hist=sorted(b['history_state_ids'])
    if anchor not in hist:raise ValueError('Anchor not in first history')
    current=b['current_base'];out=[make_candidate(b,'SKIP',[current],[]),make_candidate(b,'STAY',[current],[])]
    out[1]['estimated_observation_dwell_s']=5.0 # candidate definition, NOT observed cost
    position=hist.index(anchor)
    for kind,direction,budget in [('FIXED_RETRACE',1,2.0),('LOCAL_PATH_A',-1,4.0),('LOCAL_PATH_B',1,4.0)]:
        ids=[anchor];points=[base_pose(lookup[anchor])];accumulated=0.
        for k in range(position+direction,len(hist) if direction>0 else -1,direction):
            pose=base_pose(lookup[hist[k]]);accumulated+=distance(points[-1],pose);ids.append(hist[k]);points.append(pose)
            if accumulated>=budget:break
        if len(points)<2 or accumulated<.5:
            out.append(make_candidate(b,kind,[current],ids,'INSUFFICIENT_HISTORY_SEGMENT'));continue
        path=[current]+points+list(reversed(points[:-1]))+[current]
        c=make_candidate(b,kind,path,ids)
        c['corridor_family']='EARLIER_HISTORICAL_SEGMENT' if direction<0 else 'LATER_HISTORICAL_SEGMENT'
        c['diversity_note']='FIXED_RETRACE and LOCAL_PATH_B share a corridor; different lengths are not independent route families'
        out.append(c)
    return unique_geometry(out)


def global_candidates(b):
    lookup=validate_bundle(b,'A2');groups=defaultdict(list)
    for i in sorted(b['history_state_ids']):
        p=base_pose(lookup[i]);groups[(math.floor(p[0]/4.),math.floor(p[1]/4.))].append(i)
    out=[];current=b['current_base'];history=sorted(b['history_state_ids']);last=history[-1]
    for cell,ids in sorted(groups.items()):
        center=[sum(base_pose(lookup[i])[d] for i in ids)/len(ids) for d in (0,1)]
        representative=min(ids,key=lambda i:(distance(base_pose(lookup[i]),center),i))
        j=history.index(representative);route_ids=list(reversed(history[j:]));path=[current]+[base_pose(lookup[i]) for i in route_ids]
        c=make_candidate(b,'REGION_%s_%s'%cell,path,route_ids)
        c.update(region_id='%s_%s'%cell,target_state_id=representative,target_unique_id=lookup[representative]['unique_id'],
                 target_base=base_pose(lookup[representative]),euclidean_lower_bound_m=distance(current,base_pose(lookup[representative])),
                 accepted_state_gap=last-representative,
                 gap_definition='keyframe state gap, NOT raw scan-index gap or a complete Karto/P-ALC admissibility test',
                 historical_cluster_state_ids=ids,global_reachability='UNRESOLVED_WITHOUT_PRE_DECISION_OCCUPANCY')
        # B3 counts at TARGET, not the whole return path; explicitly non-probabilistic.
        support=historical_support(b,[c['target_base']]);c['B3_target_support_count']=support['historical_support_count']
        c['B1_native_RAL_score']=None;c['B2_P_ALC_probability']=None
        out.append(c)
    out.extend(make_candidate(b,k,[current],[]) for k in ('CONTINUE_EXPLORATION','NO_ALC'))
    return unique_geometry(out)


def select_geometric_baselines(candidates):
    regions=[c for c in candidates if 'target_state_id' in c]
    if not regions:return {}
    return {'B0_EUCLIDEAN_NEAREST_PROXY':min(regions,key=lambda c:(c['euclidean_lower_bound_m'],c['target_state_id']))['candidate_id'],
            'B3_HISTORY_SUPPORT_PROXY':min(regions,key=lambda c:(-c['B3_target_support_count'],c['euclidean_lower_bound_m'],c['target_state_id']))['candidate_id']}


def actual_outcome(candidate,executed_candidate_id,outcome):
    if candidate['candidate_id']!=executed_candidate_id:return {'status':UNOBSERVED,'gain':None,'constraints':None}
    if outcome['episode_id']!=candidate['episode_id']:raise ValueError('Cross-episode outcome join')
    return dict(outcome)


def deployable_motion_candidates(candidates):
    """Fail closed: this offline screen certifies no new moving path."""
    return [c for c in candidates if c['eligibility']=='CERTIFIED_SAFE_REACHABLE' and c['safety_verified'] is True]
