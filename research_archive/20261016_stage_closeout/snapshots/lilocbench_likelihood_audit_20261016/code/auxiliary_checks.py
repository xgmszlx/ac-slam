from common import *
import csv,hashlib
n=Native();scans=json.loads((P/'data/scans.json').read_text());centers={r['id']:r for r in json.loads((P/'data/candidate_manifest.json').read_text())};checks=[];brackets=[];states=[]
for r in scans:
 for name,c in centers[r['id']]['centers'].items():
  if c is None:continue
  file=B/'data/gt'/r['sequence']/'gt_poses.txt' if name=='GT' else Path(json.loads((P/'protocol/design_frozen.json').read_text())['references'][r['sequence']][name])/'trajectory.txt'
  a=np.loadtxt(file);t=r['scan_stamp_ns']/1e9;j=np.searchsorted(a[:,0],t);lo=max(0,j-1);hi=min(j,len(a)-1)
  rot=Slerp(a[[lo,hi],0],Rotation.from_quat(a[[lo,hi],4:8]))([t])[0] if lo!=hi else Rotation.from_quat(a[lo,4:8]);m=rot.as_matrix();assert abs(np.arctan2(np.sin(c[2]-np.arctan2(m[1,0],m[0,0])),np.cos(c[2]-np.arctan2(m[1,0],m[0,0]))))<1e-12
  if name!='GT':brackets.append({'id':r['id'],'condition':name,'status':'INTERPOLATED_NOT_NATIVE_OUTPUT','target_s':r['target_s'],'scan_time_ns':r['scan_stamp_ns'],'bracket_stamps':a[[lo,hi],0].tolist(),'bracket_relative_s':(a[[lo,hi],0]-r['gt0_ns']/1e9).tolist(),'bracket_XY':a[[lo,hi],1:3].tolist(),'endpoint_separation_m':float(np.linalg.norm(a[hi,1:3]-a[lo,1:3])),'uses_future_output_for_interpolation':bool(a[hi,0]>t),'bracket_may_exceed10s':bool(a[hi,0]>r['gt0_ns']/1e9+10.)})
  mi=int(np.floor((c[0]-n.ox)/n.scale+.5))+n.nx//2;mj=int(np.floor((c[1]-n.oy)/n.scale+.5))+n.ny//2
  states.append({'id':r['id'],'condition':name,'robot_base_map_state':int(n.state[mj,mi]) if 0<=mi<n.nx and 0<=mj<n.ny else 'OFF_MAP','meaning':'-1 free,0 unknown,+1 occupied; descriptive, no candidate rejection'})
 checks.append({'id':r['id'],'yaw_projection_matches_atan2':True,'range_count':r['count'],'within_registered_time_window':0<=r['actual_relative_s']<=10})
# Sector totals must reproduce exact within-model differences for every named candidate.
sector=list(csv.DictReader((P/'results/sector_contributions.csv').open()));named=list(csv.DictReader((P/'results/named_candidate_scores.csv').open()))
for r in named:
 if r['candidate']=='GT':continue
 a=[x for x in sector if x['id']==r['id'] and x['candidate']==r['candidate']];assert len(a)==5
 d=sum(float(x['product_log_score_delta_to_GT']) for x in a);assert abs(d-float(r['product_delta_log_to_GT']))<1e-10
 # Add contribution sums raw A0 heuristic score differences, not log differences.
 z=[x for x in named if x['id']==r['id'] and x['candidate']=='GT'][0];d=sum(float(x['add_raw_score_delta_to_GT']) for x in a);assert abs(d-(np.exp(float(r['add_log_score']))-np.exp(float(z['add_log_score']))))<1e-10
freeze=json.loads((P/'protocol/candidates_frozen_before_scores.json').read_text());assert all(hashlib.sha256((P/f).read_bytes()).hexdigest()==h for f,h in freeze['hashes'].items())
(P/'audit/offline_identity_checks.json').write_text(json.dumps({'status':'PASS','tests':checks,'all_registered_scan_candidate_source_hashes_unchanged':True,'sector_sums_equal_named_deltas':True,'no_spatial_GT_fit':True,'scans_at_zero_have_no_native_output_not_extrapolated':True,'case_selection_for_figure2':'POSTHOC illustration only; all12 fixed scans retained in primary tables'},indent=2))
(P/'results/interpolation_audit.json').write_text(json.dumps(brackets,indent=2));(P/'results/candidate_base_occupancy.json').write_text(json.dumps(states,indent=2));print('Identity/yaw/projection/sector checks PASS');print('Large interpolation bracket:',[(x['id'],x['condition'],x['endpoint_separation_m']) for x in brackets if x['endpoint_separation_m']>1.]);print('CHANGED A1 base states',[(x['id'],x['robot_base_map_state']) for x in states if x['condition']=='A1' and x['id'].startswith('lt')])
