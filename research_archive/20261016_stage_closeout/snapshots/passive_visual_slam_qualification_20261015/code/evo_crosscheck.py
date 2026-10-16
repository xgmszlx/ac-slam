"""Independent existing evo core cross-check; no CLI/config or old-workspace writes."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json
import numpy as np
sys.path.append('/home/wcqw/ac-slam/evaluation/evo-1.31.1-target/site-packages')
import evo
from evo.core import trajectory, sync, metrics
from evaluate import read_rows

p=Path(__file__).resolve().parents[1]
name=sys.argv[1];run=p/'results'/name/'headless01'
def load(path):
    a=np.asarray(read_rows(path),dtype=float)
    return trajectory.PoseTrajectory3D(positions_xyz=a[:,1:4],
        orientations_quat_wxyz=a[:,[7,4,5,6]],timestamps=a[:,0])
reference=load(p/'data'/('rgbd_dataset_freiburg3_'+name)/'groundtruth.txt')
estimated=load(run/'CameraTrajectory.txt')
reference,estimated=sync.associate_trajectories(reference,estimated,max_diff=.02)
estimated.align(reference,correct_scale=False,correct_only_scale=False)
ape=metrics.APE(metrics.PoseRelation.translation_part);ape.process_data((reference,estimated))
x={'evo_version':evo.__version__,'scale_fitted':False,'evo_associated_frames':reference.num_poses,
   'evo_ate_rmse_m':ape.get_statistic(metrics.StatisticsType.rmse),
   'our_ate_rmse_m':json.loads((run/'evaluation/metrics.json').read_text())['ate_m']['rmse']}
x['absolute_difference_m']=abs(x['evo_ate_rmse_m']-x['our_ate_rmse_m'])
(run/'evaluation/evo_crosscheck.json').write_text(json.dumps(x,indent=2));print(json.dumps(x,indent=2))
assert x['absolute_difference_m']<1e-9
