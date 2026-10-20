import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from evaluate import rigid_align, associate
import numpy as np
from scipy.spatial.transform import Rotation
import tempfile
from evaluate import evaluate

def test_rigid_transform_no_scale():
    x=np.random.default_rng(0).normal(size=(50,3))
    r=Rotation.from_rotvec([.1,.3,-.5]).as_matrix();t=np.array([3,2,1])
    a,b=rigid_align(x,x@r.T+t)
    assert np.allclose(a,r) and np.allclose(b,t)
    a,b=rigid_align(x,2*x)
    assert np.linalg.norm(x@a.T+b-2*x)>1 # scale cannot be silently fit

def test_association_no_duplicates_or_extrapolation():
    assert associate(np.array([0.,.01,1.]),np.array([.009,2.]))==[(1,0)]
    assert associate(np.array([0.,1.]),np.array([.02,1.01]))==[(1,1)]

def test_end_to_end_metric_and_missing_denominator():
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory); seq=p/'sequence';run=p/'run';seq.mkdir();run.mkdir()
        stamps=10+np.arange(91)/30
        gt=np.c_[stamps,np.arange(91)/30,np.zeros((91,2)),np.tile([0,0,0,1],(91,1))]
        estimated=gt.copy();estimated[:,1]=2*gt[:,1]+3
        np.savetxt(seq/'groundtruth.txt',gt,fmt='%.9f')
        np.savetxt(run/'CameraTrajectory.txt',estimated,fmt='%.9f')
        np.savetxt(run/'KeyFrameTrajectory.txt',estimated[::10],fmt='%.9f')
        (seq/'associations.txt').write_text(''.join(f'{t:.9f} rgb.png {t:.9f} depth.png\n' for t in stamps))
        result=evaluate(seq,run,p/'eval')
        assert abs(result['rpe_1s_translation_m']['rmse']-1)<1e-8
        assert result['rpe_1s_rotation_deg']['rmse']<1e-8
        assert result['saved_pose_fraction_of_input']==1
        np.savetxt(run/'CameraTrajectory.txt',np.delete(estimated,np.arange(30,40),axis=0),fmt='%.9f')
        result=evaluate(seq,run,p/'eval_missing')
        assert result['saved_camera_poses']==81 and result['input_associated_frames']==91
        assert result['missing_output_intervals'][0]['n']==10
        assert result['rpe_1s_translation_m']['n']<61

if __name__=='__main__':
    test_rigid_transform_no_scale();test_association_no_duplicates_or_extrapolation()
    test_end_to_end_metric_and_missing_denominator();print('3 tests PASS (SE3, time association, analytic RPE and missing coverage)')
