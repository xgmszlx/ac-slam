import sys
sys.dont_write_bytecode=True
import pathlib,json,hashlib,csv,collections,subprocess,shutil
import numpy as np
from evaluate import read_rows
sys.path.append('/home/wcqw/ac-slam/evaluation/evo-1.31.1-target/site-packages')
import evo
from evo.core import trajectory,sync,metrics
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent
checks=[]
def load(p):
 a=np.asarray(read_rows(p),dtype=float);return trajectory.PoseTrajectory3D(positions_xyz=a[:,1:4],orientations_quat_wxyz=a[:,[7,4,5,6]],timestamps=a[:,0])
for seq in ['walking','sitting']:
 for p in sorted((N/'results'/seq).glob('*')):
  if not (p/'evaluation/exported/metrics.json').exists():continue
  for name,fn in [('exported','CameraTrajectory.txt'),('online','OnlineTrajectory.txt')]:
   gt=load(O/'data'/('rgbd_dataset_freiburg3_'+seq+'_xyz')/'groundtruth.txt');est=load(p/fn);gt,est=sync.associate_trajectories(gt,est,max_diff=.02);est.align(gt,correct_scale=False,correct_only_scale=False);ape=metrics.APE(metrics.PoseRelation.translation_part);ape.process_data((gt,est));ours=json.loads((p/'evaluation'/name/'metrics.json').read_text())['ate_m']['rmse'];delta=abs(ape.get_statistic(metrics.StatisticsType.rmse)-ours);checks.append({'sequence':seq,'run':p.name,'kind':name,'evo_ATE_m':ape.get_statistic(metrics.StatisticsType.rmse),'ours_ATE_m':ours,'difference_m':delta,'GT_pairs':gt.num_poses,'PASS_1e9':delta<1e-9})
(N/'audit/evo_crosscheck.json').write_text(json.dumps({'evo':evo.__version__,'checks':checks,'PASS':all(x['PASS_1e9'] for x in checks),'initial_full_agreement_assertion':'FAILED; retained initial script; inspect all deltas before concluding'},indent=2))
# Direct intervals, online/exported common pose displacement and reset evidence.
review=[]
for p in sorted((N/'results').glob('*/*')):
 if not (p/'frame_states.csv').exists():continue
 rows=list(csv.DictReader((p/'frame_states.csv').open()));intervals=[]
 for r in rows:
  if not intervals or intervals[-1]['state']!=int(r['state']):intervals.append({'state':int(r['state']),'first':int(r['index']),'last':int(r['index']),'n':1,'start':float(r['stamp']),'end':float(r['stamp'])})
  else:intervals[-1].update(last=int(r['index']),n=intervals[-1]['n']+1,end=float(r['stamp']))
 a={round(float(r[0]),6):np.asarray(r[1:4],float) for r in read_rows(p/'CameraTrajectory.txt')};b={round(float(r[0]),6):np.asarray(r[1:4],float) for r in read_rows(p/'OnlineTrajectory.txt')};common=sorted(a.keys()&b.keys());diff=[float(np.linalg.norm(a[t]-b[t])) for t in common]
 review.append({'run':str(p.relative_to(N)),'state_intervals':intervals,'online_export_same_raw_coordinate_difference_m':{'poses':len(common),'median':float(np.median(diff)),'max':max(diff)},'note':'raw-coordinate difference is export/backend revision diagnostic, not an error metric; reset gauges may differ'})
(N/'audit/state_export_review.json').write_text(json.dumps(review,indent=2))
tree=json.loads((N/'audit/detector_tree.json').read_text());meta=[]
for item in tree['tree']:
 p=N/'audit/detector_source'/item['path']
 if item['path'] in ['demo.py','deploy.prototxt','LICENSE'] and p.exists():
  b=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();assert blob==item['sha'];meta.append({'file':item['path'],'bytes':len(b),'git_blob_matches_fixed_commit':True,'sha256':hashlib.sha256(b).hexdigest()})
(N/'audit/detector_availability.json').write_text(json.dumps({'commit':tree['sha'],'source_verified':meta,'weights_expected_bytes':23306119,'weights_validated':False,'mask_status':'MASK_NOT_QUALIFIED','reason':'raw SSL failure, direct raw partial timeout, final API blob bounded transfer timeout; no inference attempted','no_more_download_attempts':True,'P2_executed':0},indent=2))
print('independent evo and state/source audits complete')
