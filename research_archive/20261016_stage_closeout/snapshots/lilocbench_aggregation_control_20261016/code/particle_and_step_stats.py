"""Recompute the delivered inspection summary from existing raw logs/trajectories only."""
from utils import *
import json
paths={'A0 91 R0':P/'results/A0_91_R0','A1 R0':R/'results/A1_R0'};out={}
for name,root in paths.items():
 ss=[]
 for line in (root/'launch.log').read_text(errors='replace').splitlines():
  if 'RECOVERY_SENSOR ' in line:
   a=line.split('RECOVERY_SENSOR ')[1].split();ss.append([float(a[1]),float(a[2])])
 ss=np.asarray(ss);a=np.loadtxt(root/'trajectory.txt');de=np.linalg.norm(np.diff(a[:,1:3],axis=0),axis=1);yaw=Rotation.from_quat(a[:,4:8]).as_euler('ZYX')[:,0];dy=abs(np.degrees(wrap(np.diff(yaw))))
 out[name]={'pre_sensor_particles_min_median_max':np.quantile(ss[:,0],[0,.5,1]).tolist(),'pre_resample_ESS_median':float(np.median(ss[:,1])),'pre_resample_ESS_over_N_median':float(np.median(ss[:,1]/ss[:,0])),'max_consecutive_raw_displacement_m':float(de.max()),'raw_steps_over2m':int((de>2).sum()),'max_consecutive_yaw_delta_deg':float(dy.max()),'yaw_steps_over45deg':int((dy>45).sum())}
(P/'results/particle_and_step_stats.json').write_text(json.dumps(out,indent=2))
