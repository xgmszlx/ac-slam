"""Doc81: small fixed-route problem screening, separate from all old pilots."""
import hashlib,json,random,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
ASSETS=Path('/home/wcqw/ac-slam')
OUT=ROOT/'results/research_direction/localization_recovery_phase0'
SEEDS=(271001,271002,271003)
MAX_TOTAL=15
SCENARIOS={
 'NORMAL_GEOMETRY':{'map':'map3','start':[-28.,-28.,0.],
                     'route':[[6.,0.,0.],[6.,10.,0.],[16.,10.,0.],[16.,6.,0.]],'distance_m':30.},
 'CORRIDOR_DEGENERACY':{'map':'corridor','start':[-15.,0.,0.],
                     'route':[[float(x),0.,0.] for x in range(5,31,5)],'distance_m':30.},
 'REPETITIVE_OR_TRANSITION_GEOMETRY':{'map':'map3','start':[-28.,-28.,0.],
                     'route':[[0.,10.,0.],[5.,10.,0.],[10.,10.,0.],[15.,10.,0.],[20.,10.,0.]],'distance_m':30.},
}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def create_json(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def atomic_json(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp')
    q.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n');q.replace(p)
def seeded_start(scenario,seed):
    rng=random.Random(seed);a=SCENARIOS[scenario]['start']
    return [a[0]+rng.uniform(-.03,.03),a[1]+rng.uniform(-.03,.03),rng.uniform(-.01,.01)]
def reserve_episode(episode_id,kind,spec):
    """Reserve BEFORE any ROS/Stage start. Aborted and interrupted count forever."""
    import fcntl
    path=OUT/'protocol/budget_ledger.json';lock=path.with_suffix('.lock')
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);ledger=json.loads(path.read_text())
        if len(ledger['attempts'])>=MAX_TOTAL:raise RuntimeError('total budget exhausted')
        limit=9 if kind=='baseline' else 6
        if sum(r['kind']==kind for r in ledger['attempts'])>=limit:raise RuntimeError(kind+' budget exhausted')
        run=OUT/kind/episode_id
        if run.exists() or any(r['episode_id']==episode_id for r in ledger['attempts']):raise RuntimeError('attempt cannot be overwritten/retried under same ID')
        run.mkdir(parents=True)
        row={'ordinal':len(ledger['attempts'])+1,'episode_id':episode_id,'kind':kind,'status':'RESERVED','spec':spec}
        ledger['attempts'].append(row);atomic_json(path,ledger)
        return run
def update_episode(episode_id,status,detail=None):
    path=OUT/'protocol/budget_ledger.json';ledger=json.loads(path.read_text())
    for r in ledger['attempts']:
        if r['episode_id']==episode_id:r.update(status=status,detail=detail)
    atomic_json(path,ledger)
def freeze():
    if (OUT/'protocol/preregistration.json').exists():raise RuntimeError('protocol already frozen')
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['protocol','audit','baseline','analysis','figures','literature','runtime']: (OUT/name).mkdir(exist_ok=True)
    matrix=[{'episode_id':s+'_'+str(seed),'scenario':s,'seed':seed,'arm':'BASELINE_CONTINUE','start':seeded_start(s,seed),
              'route':SCENARIOS[s]['route'],'distance_m':30.} for s in SCENARIOS for seed in SEEDS]
    create_json(OUT/'protocol/frozen_baseline_matrix.json',matrix)
    source={str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}
    original_files=['catkin_ws/devel/lib/nav2d_karto/mapper','catkin_ws/devel/lib/libMultiMapper.so',
       'doc79_ws/devel/lib/nav2d_karto/mapper','doc79_ws/devel/lib/libMultiMapper.so','doc79_ws/devel/lib/libOpenKarto.so',
       'tools/realizability_pilot/same_input_replay.py','tools/realizability_pilot/se2_information.py']
    protected={p:sha(ASSETS/p) for p in original_files if (ASSETS/p).exists()}
    old_roots=['docs/research_log','results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012',
               'results/realizability_pilot/p1_doc80_offline_research_convergence_20261013']
    # Scientific old files are never outputs. Hash critical frozen files, plus
    # all tracked old paths' Git objects; no old ignored capture parsing here.
    for directory in old_roots:
        for p in (ASSETS/directory).rglob('*.json'):
            if any(t in p.name for t in ('gate','protocol','manifest','state','lock','LOCK')):protected[str(p.relative_to(ASSETS))]=sha(p)
    create_json(OUT/'audit/protected_input_hashes.json',protected)
    pars={'id':'DOC81_LOCALIZATION_DEGRADATION_RECOVERY_FEASIBILITY','type':'FEASIBILITY_SCREENING',
          'baseline_commit':'4746834ffa44504443fd07214105fe850d6f94e6','date':'2026-10-13',
          'max_total_episode_attempts':15,'baseline_limit':9,'intervention_limit':6,
          'seeds':list(SEEDS),'seed_semantics':'frozen independent start x/y +/-0.03m and heading +/-0.01rad nuisance perturbations; NOT a TSP seed, NOT deterministic Karto/Stage threading',
          'task':'online mapping SLAM, fixed Nav2D tasks; no known map enters planner, map3 bitmap only defines physical simulator',
          'karto_parameters':'same committed mapper.yaml and ros.yaml; frozen Doc79 observation binary, no rebuild',
          'robot_odometry':'unchanged p3at explicit odom_error [0.05,0.05,0.1,0]; no injected noise or stress search',
          'alignment':'one initial stationary map-base to GT SE2 transform before StartMapping; never refit',
          'gt_sync':'linear x/y plus shortest-angle heading interpolation; bracketing gap <=0.15s; exact stamped TF only, missing stays missing',
          'healthy_calibration':'all three NORMAL_GEOMETRY episodes first; threshold=max(0.15m,3*max episode p95 error); freeze before other six',
          'degradation_event':'strict translation error > frozen threshold for >=2s with consecutive gap <=0.25s; GT is offline only',
          'first_gate':'at least 2/3 episodes of a weak scenario have events and are worse than healthy; geometry proxy not sufficient',
          'primary_metrics':['online GT translation/heading error','1s translation/rotation RPE','continuous error exceedance exposure','events','task completion','time','path length'],
          'geometry_proxy':'point-to-local-line normal Jacobian [dx,dy,L*dtheta], L=1m, unit weights; not Karto correlation matcher Hessian; no threshold fitted',
          'recovery':'only after first gate; protocol must be frozen separately before intervention. No automatic method development. Local geometry reposition must be safely reachable and informative; may be infeasible.',
          'no_extra_pressure_round':True,'no_gt_online_decision':True,'no_auto_retry':True,
          'hard_episode_wall_timeout_s':600,'goal_sim_timeout_s':150,'max_tf_record_missing_fraction':0.10,
          'frozen_code_sha256':source,'baseline_matrix_sha256':sha(OUT/'protocol/frozen_baseline_matrix.json')}
    create_json(OUT/'protocol/preregistration.json',pars)
    create_json(OUT/'protocol/preregistration_hash.json',{'sha256':sha(OUT/'protocol/preregistration.json')})
    create_json(OUT/'protocol/budget_ledger.json',{'maximum':15,'attempts':[]})
    return pars
