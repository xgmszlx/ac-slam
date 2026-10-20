from pathlib import Path
import hashlib,json,subprocess,datetime
D=Path(__file__).resolve().parents[1]
assert not (D/'protocol/analysis_frozen.json').exists(), 'Do not overwrite frozen protocol'
O=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020')
A=Path('/home/wcqw/passive_rgbd_deletion_ablation_20261020')
runs={k:str(v) for k,v in {'S0':O/'results/S0','S1':O/'results/S1','S2':O/'results/S2','E1':A/'results/E1','E2':A/'results/E2','S0_02':A/'results/S0'}.items()}
paths=[]
for v in runs.values():
 p=Path(v)
 paths += [p/'frame_states.csv',p/'OnlineTrajectory.txt',p/'evaluation/online/ate.csv',p/'evaluation/online/rpe.csv',p/'evaluation/online/metrics.json']
paths += [O/'REPORT.md',A/'REPORT.md',O/'data/rgbd_bonn_moving_obstructing_box/groundtruth.txt',Path('/home/wcqw/passive_rgbd_combo_20261019/code/System_combo.cc'),Path('/home/wcqw/passive_rgbd_combo_20261019/code/Optimizer_trace.cc'),Path('/home/wcqw/passive_rgbd_combo_20261019/code/Combo.cc')]
def git(cmd):return subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+cmd).decode()
protection={'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'git_head':git(['rev-parse','HEAD']),'git_status':git(['status','--porcelain']),'git_diff_sha256':hashlib.sha256(git(['diff']).encode()).hexdigest()}
(D/'protocol/protection_before.json').write_text(json.dumps(protection,indent=2))
plan={'status':'OFFLINE_DIAGNOSTIC','frozen_at':datetime.datetime.now().astimezone().isoformat(),'runs':runs,'no_new_slam':True,'definitions':{'support':'retained_2d+retained_3d after TrackRGBD, nonnull MapPoint and !outlier; not complete PoseOptimization edges','deleted':'bad_2d_rejected+motion_rejected','deletion_fraction':'deleted/raw_N','timestamp_matching':'frame stamps exact across runs; evaluation rounded timestamp nearest unique within 2 microseconds; no interpolation','rpe_support':'support and actions at RPE start; forward approximately 1s error from saved evaluator','gt_motion':'same unique nearest GT matches as frozen evaluator, <=20ms; relative endpoint translation/rotation, offline only'},'statistics':['Pearson and Spearman descriptive only, no p values or iid confidence intervals','2s fixed time-bin centered residual correlations','residual correlations after OLS fixed 2s phase indicators plus GT 1s displacement and rotation','first-difference correlation within consecutive RPE-start pairs','paired differences relative S0 at same timestamps, raw and phase/motion adjusted','quartile support bins per run; data-dependent descriptive edges, no threshold claim'],'window_selection':'fixed disjoint physical 2s bins [0,2),...,[18,20), only RPE pairs with both endpoints inside; rank bins by max(S1 RMS RPEt - S0 RMS RPEt,S2 RMS RPEt - S0 RMS RPEt), select top 3; outcome-selected exploratory, never altered by count patterns','figures':3,'budget_new_runs':0}
(D/'protocol/analysis_frozen.json').write_text(json.dumps(plan,indent=2))
print('Frozen',len(paths),'source files; no scores calculated')
