from pathlib import Path
import json,hashlib,subprocess,os,time,shutil
b=Path('/home/wcqw/lilocbench_amcl_validation_20261016');r=Path('/home/wcqw/lilocbench_amcl_recovery_control_20261016');p=Path('/home/wcqw/lilocbench_likelihood_audit_20261016');p.mkdir(exist_ok=False)
for d in ['code','sources','audit','protocol','data','results','figures','build']:(p/d).mkdir()
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as q:
  for c in iter(lambda:q.read(1048576),b''):h.update(c)
 return h.hexdigest()
files={}
for root in [b,r]:
 for f in json.loads((root/'MANIFEST.json').read_text())['files']:
  ff=root/f
  if ff.is_file():files[str(ff)]=sha(ff)
 files[str(root/'MANIFEST.json')]=sha(root/'MANIFEST.json')
for f in Path('/home/wcqw').glob('*/REPORT.md'):
 if f.parent!=p:files[str(f)]=sha(f)
env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')
git={k:subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+a,env=env).decode() for k,a in [('head',['rev-parse','HEAD']),('status',['status','--porcelain=v1']),('diff',['diff','--binary'])]}
(p/'audit/protection_before.json').write_text(json.dumps({'files':files,'git':git,'free_bytes':shutil.disk_usage(p).free,'wall':time.time()},indent=2))
proto={'wall':time.time(),'scope':'OFFLINE_DIAGNOSTIC, static_0 and lt_changes_0 only, first 0-10s; no estimator/ROS startup','source_commit':'f13af47ee2bca6c3bf99db2965e46e55303f6e66','time_origin':'first official GT stamp independently per sequence','targets_s':[0,1,2,5,7,10],'scan_selection':'nearest original front scan whose stamp lies within [GT0,GT0+10]; ties earlier stamp; no score-based selection','trajectory_centers':'GT/A0/A1/A2 at exact scan time by linear XY and quaternion SLERP, no spatial fit or extrapolation; unavailable center explicitly omitted','references':{seq:{a:str(b/'results'/f'offline_seed1702_{seq}_{a}') for a in ['A0','A1','A2']} for seq in ['static_0','lt_changes_0']},'static_A0_actual_initial_seed':1,'all_other_reference_actual_initial_seeds':1702,'grid':{'centers':['GT','A0','A1','A2'],'dx_dy_m':{'min':-.6,'max':.6,'step':.05},'yaw_offset_deg':{'min':-20,'max':20,'step':2},'include_exact_centers':True,'union':'exact float64 pose triples, duplicates removed; center grids retained separately for widths and ESS proxies','no_expansion':True},'beam_indices':'0,9,...,810: all 91 physical slots; common validity and pz for both aggregations','model':{'z_hit':.95,'z_rand':.05,'sigma_hit':.2,'max_occ_dist':2.,'A0':'1 + sum(pz^3)','A1':'sum(log(pz)) preserved in log domain; normalized ratios only within model','beam_skip':'NOT applied; historical A2 masks/particle population unavailable; A2 is candidate pose only'},'validity':'native amcl_node min/max remapping and sensor max/NaN exclusion','sectors_deg':[-135,-81,-27,27,81,135.1],'sector_coordinates':'original laser scan bearing, not global map or candidate-specific sectors','grid_proxy':'ESS and half-height XY profile width computed only within uniform GT-centered grid; not actual PF ESS or calibrated uncertainty','numerical_test_tolerance':{'logscore_abs':1e-10,'pz_abs':1e-12},'sample_geometry_bins':'<=0.2m GT-near, >0.6m outside 3 initial xy SD, >1m severe; descriptive not changed historical failure definition','peak':'finite candidate set only, not full-map optimum','resource_reserve_bytes':5*1024**3,'output_budget_bytes':512*1024**2,'decision_boundary':'concentration alone does not prove wrong localization; GT support alone cannot prove actual PF particles included it','forbidden':['new data/weights/software','ROS/AMCL/Stage/Gazebo runs','source formula modification','beam-weight method design','extending beyond10s']}
(p/'protocol/design_frozen.json').write_text(json.dumps(proto,indent=2));print(p,'protected',len(files))
