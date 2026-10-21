"""Reevaluate saved outputs only. Camera extrinsic comes only from official source."""
from pathlib import Path
import json,csv,hashlib
import numpy as np
from scipy.spatial.transform import Rotation
from pose_math import *
D=Path(__file__).resolve().parents[1]
B=Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/data/rgbd_bonn_moving_obstructing_box')
W=Path('/home/wcqw/passive_visual_slam_qualification_20261015/data/rgbd_dataset_freiburg3_walking_xyz')
R=Path('/home/wcqw/ngd_region_prototype_20261021/results')
P=Path('/home/wcqw/passive_visual_slam_qualification_20261015/diagnostic_comparison_20261015/results/walking/P1_01')
jobs=[('NGD_M0',B,R/'M0',True),('NGD_M2',B,R/'M2',True),('ORB3_S0',B,Path('/home/wcqw/passive_rgbd_combo_20261019/e2e_20261020/results/S0'),True),('NGD_walking_M0_03',W,Path('/home/wcqw/ngd_scientific_baseline_20261020/results/M0_03'),False),('ORB3_walking_P1_01',W,P,False)]

def evaluate(ep,et,gp,gt,inputs):
    assert np.isfinite(ep).all() and np.isfinite(gp).all()
    assert len(np.unique(et))==len(et) and np.all(np.diff(et)>0)
    assert len(np.unique(gt))==len(gt) and np.all(np.diff(gt)>0)
    pairs=associate(et,gt); ei,gi=np.asarray(pairs).T
    r,t=align(ep[ei,:3,3],gp[gi,:3,3]); pos=ep[:,:3,3]@r.T+t
    err=np.linalg.norm(pos[ei]-gp[gi,:3,3],axis=1)
    valid=dict(pairs);rr=[]
    for e,g in pairs:
        j=int(np.argmin(abs(et-et[e]-1)))
        if j<=e or abs(et[j]-et[e]-1)>=.02 or j not in valid or np.any(np.diff(et[e:j+1])>.1): continue
        d=np.linalg.inv(np.linalg.inv(gp[g])@gp[valid[j]])@(np.linalg.inv(ep[e])@ep[j])
        rr.append([et[e],et[j],np.linalg.norm(d[:3,3]),float(angle(d[:3,:3]))])
    matched=associate(inputs,et,.00001)
    out={'frames':len(et),'input_frames':len(inputs),'GT_matched':len(pairs),'input_coverage':len(matched)/len(inputs),'GT_matched_fraction_input':len(pairs)/len(inputs),'timestamps_unique':True,'strictly_increasing':True,'ATE_m':describe(err),'RPEt_m':describe([x[2] for x in rr]),'RPEr_deg':describe([x[3] for x in rr]),'alignment':{'SE3_scale':1.,'R':r.tolist(),'t':t.tolist()}}
    return out,np.c_[et[ei],err],np.array(rr)

if __name__=='__main__':
    assert not (D/'corrected/metrics_summary.json').exists()
    source_hash=next(x['sha256'] for x in json.loads((D/'sources/fetch.json').read_text()) if x['name']=='compute_global_transformation.py')
    calib={'Q':Q.tolist(),'Tm_source':TM.tolist(),'singular_values':s.tolist(),'mean_scale':float(s.mean()),'source_det':float(np.linalg.det(TM[:3,:3])),'source_orthogonality_error':float(np.linalg.norm(TM[:3,:3].T@TM[:3,:3]-np.eye(3))),'rigid_E':E.tolist(),'right_factor_QE':(Q@E).tolist(),'right_factor_angle_deg':float(angle((Q@E)[:3,:3])),'rule':'H_WC(t)=Q^-1 G_file(t) Q E; E rotation is polar SO3(Tm_3x3), translation copied in meters; no scale fit','scale_origin':'Not explained by official page/script; mathematical near-uniform scale observed, not claimed to be known physical calibration cause','treatment':'remove source scale only from orientation, retain published lever-arm; do not rescale depth/GT translation/SLAM; explicit translation/s sensitivity','source_sha256':source_hash}
    (D/'protocol/calibration_frozen.json').write_text(json.dumps(calib,indent=2))
    summary={};flat=[];missing=[]
    for name,seq,run,is_bonn in jobs:
        if not run.is_dir(): missing.append({'job':name,'path':str(run),'reason':'run directory absent'});continue
        gt,g=poses(read(seq/'groundtruth.txt'));inputs=np.array([float(l.split()[0]) for l in (seq/'associations.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]);summary[name]={}
        if is_bonn:
            dst=D/'corrected'/name;dst.mkdir(exist_ok=True)
            corrected_rows=np.c_[gt,corrected(g)[:,:3,3],Rotation.from_matrix(corrected(g)[:,:3,:3]).as_quat()]
            np.savetxt(dst/'camera_groundtruth.txt',corrected_rows,fmt='%.12f')
        for typ,fn in [('online','OnlineTrajectory.txt'),('exported','CameraTrajectory.txt')]:
            if not (run/fn).exists():missing.append({'job':name,'type':typ,'reason':'original entry did not save online trajectory'});continue
            et,ep=poses(read(run/fn));variants=['official_rigid','raw_file_negative','translation_divide_scale_sensitivity','zero_translation_sensitivity'] if is_bonn else ['TUM_unchanged']
            summary[name][typ]={}
            for var in variants:
                gp=corrected(g,var) if is_bonn else g
                metrics,aa,rr=evaluate(ep,et,gp,gt,inputs);summary[name][typ][var]=metrics
                d=D/'corrected'/name/typ/var;d.mkdir(parents=True,exist_ok=True)
                (d/'metrics.json').write_text(json.dumps(metrics,indent=2));np.savetxt(d/'ate.csv',aa,delimiter=',',header='stamp,error_m',comments='');np.savetxt(d/'rpe.csv',rr,delimiter=',',header='stamp_start,stamp_end,translation_m,rotation_deg',comments='')
                row={'system':name,'type':typ,'protocol':var,'frames':metrics['frames'],'GT_matched':metrics['GT_matched'],'coverage':metrics['input_coverage']}
                for key in ['ATE_m','RPEt_m','RPEr_deg']:
                    row.update({key+'_'+k:metrics[key][k] for k in ['rmse','median','p90','p95']})
                flat.append(row)
    (D/'corrected/metrics_summary.json').write_text(json.dumps(summary,indent=2));(D/'corrected/unavailable.json').write_text(json.dumps(missing,indent=2))
    with (D/'corrected/all_metrics.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    print(json.dumps({'calibration':calib,'unavailable':missing,'main':[{k:v for k,v in r.items() if k in ['system','type','protocol','ATE_m_rmse','ATE_m_median','RPEt_m_rmse','RPEt_m_median','RPEt_m_p90','RPEr_deg_rmse','RPEr_deg_median']} for r in flat if r['protocol'] in ['official_rigid','TUM_unchanged']]},indent=2))
