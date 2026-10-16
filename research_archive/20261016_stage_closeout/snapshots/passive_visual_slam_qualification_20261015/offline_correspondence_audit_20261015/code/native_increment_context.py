import pathlib,json,numpy as np,csv
from geometry import pose_at,rotation,angle_deg
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;D=O/'data/rgbd_dataset_freiburg3_walking_xyz';P=json.loads((N/'protocol/design_v02.json').read_text());gt=np.loadtxt(D/'groundtruth.txt');out=[]
for tag in ['P1_01','P1_02','P1_03']:
 for mode,filename in [('online','OnlineTrajectory.txt'),('exported','CameraTrajectory.txt')]:
  a=np.loadtxt(O/'diagnostic_comparison_20261015/results/walking'/tag/filename)
  for pair in P['pairs']:
   ts=[float(f['stamp']) for f in pair['frames']];est=[];truth=[]
   for t in ts:
    idx=int(np.argmin(abs(a[:,0]-t)));assert abs(a[idx,0]-t)<1e-5;r=a[idx];T=np.eye(4);T[:3,:3]=rotation(r[4:8]);T[:3,3]=r[1:4];est.append(T);truth.append(pose_at(gt,t)[0])
   actual=np.linalg.inv(truth[0])@truth[1];pred=np.linalg.inv(est[0])@est[1];delta=np.linalg.inv(actual)@pred
   out.append({'pair':pair['id'],'window':pair['window'],'run':tag,'mode':mode,'supplemental_interval_s':ts[1]-ts[0],'GT_translation_m':float(np.linalg.norm(actual[:3,3])),'GT_rotation_deg':angle_deg(actual[:3,:3]),'estimated_translation_m':float(np.linalg.norm(pred[:3,3])),'estimated_rotation_deg':angle_deg(pred[:3,:3]),'increment_error_m':float(np.linalg.norm(delta[:3,3])),'increment_error_rotation_deg':angle_deg(delta[:3,:3]),'OFFLINE_DIAGNOSTIC':True,'not_replacing_frozen_1s_RPE':True})
with (N/'results/native_increment_context.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
