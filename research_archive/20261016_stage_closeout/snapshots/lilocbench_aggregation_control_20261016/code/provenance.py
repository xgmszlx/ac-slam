from utils import *
import json,csv,time
proto=json.loads((P/'protocol/design_frozen.json').read_text());gt=np.loadtxt(B/'data/gt/lt_changes_0/gt_poses.txt');gt0=gt[0,0];od=np.load(P/'results/odom_tf.npz');odom=np.c_[od['stamp_ns']/1e9,od['poses']];scans=[r for r in json.loads((L/'data/scans.json').read_text()) if r['sequence']=='lt_changes_0' and r['target_s']>0];cm={r['id']:r for r in json.loads((L/'data/candidate_manifest.json').read_text())};rows=[];origins=[]
for r in scans:
 t=r['scan_stamp_ns']/1e9;g,_,_=interp(gt,t)
 for name in ['A1 ON','A1 R0','A2 ON','A2 R0']:
  root=Path(proto['reference_runs'][name]);a=np.loadtxt(root/'trajectory.txt');pos,lo,hi=interp(a,t);j=int(np.argmin(abs(a[:,0]-t)));raw=pose_row(a[j]);graw,_,_=interp(gt,a[j,0]);o1,_,_=interp(odom,a[lo,0]);o2,_,_=interp(odom,a[hi,0]);separation=float(np.linalg.norm(a[hi,1:3]-a[lo,1:3]));yaw=float(abs(np.degrees(wrap(pose_row(a[hi])[2]-pose_row(a[lo])[2]))));unsafe=separation>1. or yaw>45.
  rows.append({'target_s':r['target_s'],'fixed_scan_relative_s':r['actual_relative_s'],'fixed_scan_stamp_ns':r['scan_stamp_ns'],'condition':name,'source_run':str(root),'recovery_enabled':name.endswith('ON'),'interp_x':float(pos[0]),'interp_y':float(pos[1]),'interp_yaw_deg':float(np.degrees(pos[2])),'interpolated_position_error_m':float(np.linalg.norm(pos[:2]-g[:2])),'nearest_raw_stamp':float(a[j,0]),'nearest_raw_relative_s':float(a[j,0]-gt0),'nearest_raw_position_error_m':float(np.linalg.norm(raw[:2]-graw[:2])),'nearest_raw_x':float(raw[0]),'nearest_raw_y':float(raw[1]),'nearest_raw_yaw_deg':float(np.degrees(raw[2])),'interpolation_bracket_stamps':json.dumps(a[[lo,hi],0].tolist()),'bracket_output_separation_m':separation,'bracket_output_yaw_change_deg':yaw,'bracket_odom_translation_m':float(np.linalg.norm(o2[:2]-o1[:2])),'bracket_odom_yaw_deg':float(abs(np.degrees(wrap(o2[2]-o1[2])))),'interpolation_crosses_large_jump':unsafe})
  if name=='A1 ON' and r['target_s'] in [5,7]:
   old=np.array(cm[r['id']]['centers']['A1']);assert np.max(np.abs(old-pos))<1e-12
   origins.append({'audit_id':r['id'],'exact_match_to_previous_candidate':True,'source':str(root),'recovery':'ON','is_raw_output':False,'interpolated_error_m':float(np.linalg.norm(pos[:2]-g[:2])),'not_A1_R0':True,'bracket_output_separation_m':separation})
with (P/'results/provenance_details.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
md=['| 目标s / 实际扫描s | A1-ON | A1-R0 | A2-ON | A2-R0 | 该插值区间odom位移m |','|---|---:|---:|---:|---:|---:|']
for t in [1,2,5,7,10]:
 rr=[r for r in rows if r['target_s']==t];s=[f"{r['interpolated_position_error_m']:.3f}{'†' if r['interpolation_crosses_large_jump'] else ''} ({r['nearest_raw_position_error_m']:.3f})" for r in rr];md.append('| '+f"{t} / {rr[0]['fixed_scan_relative_s']:.6f}"+' | '+' | '.join(s)+f" | {rr[0]['bracket_odom_translation_m']:.3f} |")
(P/'results/provenance_table.md').write_text('\n'.join(md))
(P/'audit/candidate_origin.json').write_text(json.dumps({'wall':time.time(),'filter_started':False,'previous_errors_8p747_and_7p367':origins,'notation':'interpolated error (nearest native output error), meters; dagger flags large-jump interpolation, not a real PF hypothesis','odometry_note':'All four prior output stamp sequences equal; odom displacement evaluated at same native bracketing stamps; not GT aligned'},indent=2));print('\n'.join(md));print(json.dumps(origins,indent=2))
