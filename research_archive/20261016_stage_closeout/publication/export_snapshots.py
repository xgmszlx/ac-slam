"""Read-only compact export. Does not execute any experiment or imported research code."""
from pathlib import Path
import os, json, hashlib, shutil
ROOT=Path(__file__).resolve().parents[1]
NAMES=['active_mapping_d1_exploratory_20261015','passive_visual_slam_qualification_20261015','passive_visual_slam_v2_v3_screen_20261015','passive_visual_slam_v3_cables3_20261015','lilocbench_amcl_validation_20261016','lilocbench_amcl_recovery_control_20261016','lilocbench_likelihood_audit_20261016','lilocbench_aggregation_control_20261016','slam_stage_closeout_20261016','v3_cables3_data_gate_20261016']
CHILDREN={'diagnostic_comparison_20261015','p2_window_validation_20261015','offline_correspondence_audit_20261015'}
PRUNE={'sources','code_snapshots','catkin_ws','diagnostic_ws','diagnostic_ws_v2','frontier_build_ws','build','build_pangolin','local','lib','runtime','models','masked_source','frame_test_source','__pycache__','.git','masks','ros_logs','ros_home','tf','keras','downloads'}
REJECT_NAMES={'trajectory.txt','CameraTrajectory.txt','KeyFrameTrajectory.txt','OnlineTrajectory.txt','matches.csv','local_motion.csv','window_image_metrics.csv','collector.json','owned_processes.json','scans.json','receipts.json','source_inventory.json','protection_before.json','protection_after.json','main_worktree_before.json'}
REJECT_SUFFIX={'.bag','.db','.pdf','.txt','.html','.response','.pyc','.so','.o','.a','.npz','.npy','.pgm','.pickle','.gz','.zip','.tar','.h5','.onnx','.caffemodel','.partial','.headers','.log','.stderr'}
FIGURES={'main_timelines.png','changed_map_cases.png','recovery_timelines.png','trajectories.png','onset_and_covariance.png','01_profiles.png','02_map_scan_overlays.png','03_sector_contributions.png','comparison.png','particles_and_weights.png','two_windows.png','repeat_comparison.png','error_state_timeline.png','window_timeline.png','frozen_pair_comparison.png','correspondence_geometry_critical.png','correspondence_geometry_after.png'}
def select(rel):
 parts=list(rel.parts)
 if parts[0] in CHILDREN:parts=parts[1:]
 name=parts[-1];suffix=Path(name).suffix.lower();top=parts[0]
 if name in REJECT_NAMES or name.startswith('MANIFEST') or name.endswith('_native_errors.csv'):return 'raw_per_frame_or_local_manifest'
 if suffix in REJECT_SUFFIX:return 'raw_binary_download_or_machine_log'
 if len(parts)==1:return None if suffix in {'.md','.json'} else 'outside_top_documents'
 if top in {'code','scripts','tests','patches'}:return None if suffix in {'.py','.cc','.cpp','.c','.h','.hpp','.sh','.patch','.md','.json'} else 'not_code'
 if top in {'protocol','config','annotations','literature','failures'}:return None if suffix in {'.json','.jsonl','.yaml','.yml','.md','.csv','.patch','.launch'} else 'not_protocol_or_review'
 if top=='audit':
  if any(s in name.lower() for s in ['protection','inventory','receipts','legacy_hashes','protected','workspace_before','frozen_artifacts']):return 'large_local_inventory'
  return None if suffix in {'.json','.csv','.md','.patch'} else 'machine_log'
 if top=='results':
  if any(s in name.lower() for s in ['cloud','particle_snapshot','observation','sensor_update_events','recovery_events','events.csv','points','per_frame','native_errors']):return 'per_frame_or_particle_stream'
  return None if suffix in {'.json','.csv','.md','.tsv'} else 'raw_result'
 if top=='figures':return None if name in FIGURES else 'unselected_figure_or_dataset_image'
 return 'outside_compact_scope'
def main():
 target=ROOT/'snapshots';target.mkdir(exist_ok=False);records=[];pruned=[]
 for name in NAMES:
  source=Path('/home/wcqw')/name
  for base,dirs,files in os.walk(source,followlinks=False):
   bp=Path(base)
   for d in list(dirs):
    if d in PRUNE or d=='data' or d.startswith('build_'):
     dirs.remove(d);pruned.append({'root':name,'path':str((bp/d).relative_to(source)),'reason':'upstream_or_raw_data_or_build_directory'})
   for f in sorted(files):
    p=bp/f
    if p.is_symlink():continue
    rel=p.relative_to(source);reason=select(rel);size=p.stat().st_size
    if reason is None and size>(2*1024**2 if rel.suffix=='.png' else 512*1024):reason='above_compact_size_limit'
    record={'root':name,'path':str(rel),'bytes':size,'included':reason is None}
    if reason:record['reason']=reason
    else:
     payload=p.read_bytes();record['sha256']=hashlib.sha256(payload).hexdigest();q=target/name/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(payload)
    records.append(record)
 # Small authored native bridge only; exclude whole third-party source trees.
 s=Path('/home/wcqw/lilocbench_likelihood_audit_20261016/sources/native_probe.cpp');rel='sources/native_probe.cpp';payload=s.read_bytes();q=target/'lilocbench_likelihood_audit_20261016'/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(payload);records.append({'root':'lilocbench_likelihood_audit_20261016','path':rel,'bytes':len(payload),'included':True,'sha256':hashlib.sha256(payload).hexdigest()})
 out={'status':'BYTE_EXACT_SELECTED_SNAPSHOTS','records':records,'pruned_directories':pruned,'included_files':sum(r['included'] for r in records),'included_bytes':sum(r['bytes'] for r in records if r['included']),'note':'Not a standalone runnable environment; source local paths and hashes retained. Large/raw originals remain local.'};(ROOT/'publication/source_inventory.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print({k:v for k,v in out.items() if k not in {'records','pruned_directories'}})
if __name__=='__main__':main()
