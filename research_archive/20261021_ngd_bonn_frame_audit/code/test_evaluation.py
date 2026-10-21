"""Deterministic tests; raw geometry test uses saved fixed RGB-D probe results."""
from pathlib import Path
import json,sys,importlib.util
import numpy as np
from scipy.spatial.transform import Rotation
from pose_math import *
from evaluate_corrected import evaluate
D=Path(__file__).resolve().parents[1];checks={}
def check(name,condition):
    checks[name]=bool(condition)
    if not condition: raise AssertionError(name)

def se3(rv,t):
    h=np.eye(4);h[:3,:3]=Rotation.from_rotvec(rv).as_matrix();h[:3,3]=t;return h

marker=np.array([se3([.03*k,.07*np.sin(k),.1*k],[.2*k,np.sin(k),.1*np.cos(k)]) for k in range(8)])
camera=marker@E;recorded=Q@marker@Q
check('known_marker_camera_extrinsic_recovery',np.allclose(corrected(recorded),camera,atol=1e-12))
check('official_model_first_pose_formula_rigidized',np.allclose(corrected(recorded[0]),Q@recorded[0]@Q@E))
left=se3([.3,.2,-.6],[5,2,-3]);pred=camera.copy();pred[3:,:3,3]+=[.03,-.02,.01]
def rpe(g,p):
    d=np.linalg.inv(np.linalg.inv(g[:-1])@g[1:])@(np.linalg.inv(p[:-1])@p[1:]);return np.linalg.norm(d[:,:3,3],axis=1),angle(d[:,:3,:3])
a,b=rpe(camera,pred);c,d=rpe(left@camera,left@pred)
check('world_left_SE3_RPE_translation_invariant',np.allclose(a,c,atol=1e-12))
check('world_left_SE3_RPE_rotation_invariant',np.allclose(b,d,atol=2e-6))
qs=Rotation.from_matrix(camera[:,:3,:3]).as_quat()
check('quaternion_sign_equivalence',np.allclose(quat_matrix(qs),quat_matrix(-qs),atol=1e-14))
check('SO3_orthogonal_det_positive',np.allclose(E[:3,:3].T@E[:3,:3],np.eye(3),atol=1e-12) and abs(np.linalg.det(E[:3,:3])-1)<1e-12)
check('published_matrix_non_SE3_explicit',np.linalg.norm(TM[:3,:3].T@TM[:3,:3]-np.eye(3))>.2)
check('Q_inverse_equals_Q',np.array_equal(Q@Q,np.eye(4)))
check('quaternion_math_independent_scipy',np.allclose(quat_matrix(qs),Rotation.from_quat(qs).as_matrix(),atol=1e-14))
fixture_a=np.array([0.,.01,1.]);fixture_b=np.array([.002,.99,1.008])
pairs=associate(fixture_a,fixture_b)
check('GT_unique_matching',len(set(x[0] for x in pairs))==len(pairs)==len(set(x[1] for x in pairs)))
check('GT_tolerance_strict',associate([0],[.02])==[] and len(associate([0],[.019]))==1)
ts=np.arange(8)*.5
try:
    evaluate(camera,np.zeros(8),camera,ts,ts);duplicate_refused=False
except AssertionError: duplicate_refused=True
check('duplicate_output_timestamps_rejected',duplicate_refused)
try:
    rr=np.c_[ts,camera[:,:3,3],qs];interpolate(rr,-1);extrap_refused=False
except ValueError:extrap_refused=True
check('GT_extrapolation_rejected',extrap_refused)
geometry=json.loads((D/'corrected/geometry_summary.json').read_text())
check('independent_RGBD_official_vs_raw',geometry['official_rigid']['consistent']>geometry['raw_file_negative']['consistent'] and geometry['official_rigid']['median_of_pair_reprojection_medians_px']<geometry['raw_file_negative']['median_of_pair_reprojection_medians_px'])
check('independent_RGBD_wrong_extrinsic_negative',geometry['official_rigid']['consistent']>geometry['inverse_extrinsic_negative']['consistent'] and geometry['official_rigid']['consistent']>geometry['ignore_ROS_negative']['consistent'])
summary=json.loads((D/'corrected/metrics_summary.json').read_text())
old=json.loads(Path('/home/wcqw/ngd_scientific_baseline_20261020/results/M0_03/evaluation/metrics.json').read_text())
new=summary['NGD_walking_M0_03']['exported']['TUM_unchanged']
check('TUM_positive_control_ATE_unchanged',abs(old['ate_m']['rmse']-new['ATE_m']['rmse'])<1e-12)
check('TUM_positive_control_RPE_translation_unchanged',abs(old['rpe_1s_translation_m']['rmse']-new['RPEt_m']['rmse'])<1e-12)
check('TUM_positive_control_RPE_rotation_unchanged',abs(old['rpe_1s_rotation_deg']['rmse']-new['RPEr_deg']['rmse'])<1e-9)
# Independently recompute one Bonn corrected RPE using scipy quaternion rotations.
src=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box/groundtruth.txt');gt,g=poses(read(src));et,p=poses(read('/home/wcqw/ngd_region_prototype_20261021/results/M0/CameraTrajectory.txt'));g=corrected(g);rr=np.loadtxt(D/'corrected/NGD_M0/exported/official_rigid/rpe.csv',delimiter=',',skiprows=1)
match=dict(associate(et,gt));ind=[]
for t0,t1,_,_ in rr:
    i=int(np.argmin(abs(et-t0)));j=int(np.argmin(abs(et-t1)))
    dp=Rotation.from_matrix(p[i,:3,:3]).inv()*Rotation.from_matrix(p[j,:3,:3]);dg=Rotation.from_matrix(g[match[i],:3,:3]).inv()*Rotation.from_matrix(g[match[j],:3,:3]);ind.append((dg.inv()*dp).magnitude()*180/np.pi)
check('independent_scipy_RPE_rotation',np.max(abs(np.array(ind)-rr[:,3]))<1e-9)
out={'checks':checks,'pass':all(checks.values()),'count':len(checks),'geometry_not_dynamic_truth':True,'official_scale_physical_cause_unknown':True,'qualification':'rigidized official extrinsic convention supported; calibration uncertainty explicit'}
(D/'audit/evaluation_tests.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
