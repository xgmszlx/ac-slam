"""Offline TUM RGB-D SE(3) trajectory evaluation. No scale fit; GT never feeds SLAM."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

def read_rows(path):
    return [line.split() for line in Path(path).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]

def associate(a, b, tolerance=0.02):
    """TUM-style globally greedy unique nearest timestamp association."""
    candidates = []
    for i, t in enumerate(a):
        lo = np.searchsorted(b, t-tolerance, side='right')
        hi = np.searchsorted(b, t+tolerance, side='left')
        candidates.extend((abs(t-b[j]), i, j) for j in range(lo, hi))
    used_a, used_b, matches = set(), set(), []
    for _, i, j in sorted(candidates):
        if i not in used_a and j not in used_b:
            used_a.add(i); used_b.add(j); matches.append((i,j))
    return sorted(matches)

def rigid_align(source, target):
    a, b = source.mean(0), target.mean(0)
    u, _, vt = np.linalg.svd((source-a).T @ (target-b))
    d = np.eye(3); d[-1,-1] = np.linalg.det(vt.T @ u.T)
    r = vt.T @ d @ u.T
    return r, b-r@a

def transforms(rows):
    a = np.asarray(rows, dtype=float)
    out = np.tile(np.eye(4), (len(a),1,1))
    out[:,:3,:3] = Rotation.from_quat(a[:,4:8]).as_matrix()
    out[:,:3,3] = a[:,1:4]
    return a[:,0], out

def stats(values):
    a = np.asarray(values)
    if not len(a): return {'n':0}
    return {'n':len(a),'rmse':float(np.sqrt(np.mean(a*a))),
            'median':float(np.median(a)),'p90':float(np.quantile(a,.9)),
            'max':float(a.max()),'mean':float(a.mean())}

def evaluate(sequence, run, output):
    sequence, run, output = map(Path, (sequence, run, output))
    output.mkdir(parents=True, exist_ok=True)
    assoc = read_rows(sequence/'associations.txt')
    inputs = np.array([float(a[0]) for a in assoc])
    et, ep = transforms(read_rows(run/'CameraTrajectory.txt'))
    gt, gp = transforms(read_rows(sequence/'groundtruth.txt'))
    pairs = associate(et, gt)
    if len(pairs)<3: raise ValueError('Fewer than 3 GT matches; alignment not qualified')
    ei, gi = np.asarray(pairs).T
    r,t = rigid_align(ep[ei,:3,3], gp[gi,:3,3])
    aligned = np.einsum('ij,njk->nik',r,ep[:,:3,:3])
    pos = ep[:,:3,3]@r.T+t
    errors = np.linalg.norm(pos[ei]-gp[gi,:3,3],axis=1)
    # RPE: 1 second in timestamp, both endpoints within 20ms, no >100ms output gap.
    relative_t, relative_r, rpe_rows = [], [], []
    all_relative_t,all_relative_r,excluded_gap_pairs=[],[],0
    valid = {int(e):int(g) for e,g in pairs}
    for e,g in pairs:
        j = int(np.argmin(abs(et-(et[e]+1.0))))
        if j<=e or abs(et[j]-et[e]-1.0)>=.02 or j not in valid: continue
        h=valid[j]
        pred=np.linalg.inv(ep[e])@ep[j]
        truth=np.linalg.inv(gp[g])@gp[h]
        delta=np.linalg.inv(truth)@pred
        te=float(np.linalg.norm(delta[:3,3]))
        re=float(Rotation.from_matrix(delta[:3,:3]).magnitude()*180/np.pi)
        all_relative_t.append(te);all_relative_r.append(re)
        if np.any(np.diff(et[e:j+1])>.1):
            excluded_gap_pairs+=1
            continue
        relative_t.append(te);relative_r.append(re);rpe_rows.append([et[e],et[j],te,re])
    saved_matches = associate(inputs, et, 0.00001)
    input_gt = associate(inputs, gt)
    rgb_count=len(read_rows(sequence/'rgb.txt')) if (sequence/'rgb.txt').exists() else len(inputs)
    gaps = []
    output_for_input = {i:e for i,e in saved_matches}
    missing = [i for i in range(len(inputs)) if i not in output_for_input]
    for i in missing:
        if not gaps or i!=gaps[-1][-1]+1:gaps.append([i])
        else:gaps[-1].append(i)
    durations = np.r_[np.diff(inputs),np.median(np.diff(inputs))]
    result={'input_associated_frames':len(inputs),'saved_camera_poses':len(et),
            'all_rgb_frames':rgb_count,
            'saved_keyframes':len(read_rows(run/'KeyFrameTrajectory.txt')),
            'gt_rows':len(gt),'gt_time_range':[float(gt[0]),float(gt[-1])],
            'input_frames_with_gt':len(input_gt),'saved_poses_with_gt':len(pairs),
            'saved_pose_fraction_of_input':len(saved_matches)/len(inputs),
            'saved_gt_matched_fraction_of_input':len(pairs)/len(inputs),
            'saved_pose_fraction_of_all_rgb':len(saved_matches)/rgb_count,
            'saved_gt_match_fraction_of_gt_eligible_input':len(pairs)/len(input_gt) if input_gt else None,
            'duplicate_saved_timestamps':int(len(et)-len(np.unique(et))),
            'nonincreasing_saved_time_steps':int(sum(np.diff(et)<=0)),
            'saved_trajectory_time_fraction':float(sum(durations[list(output_for_input)])/sum(durations)),
            'saved_time_range':[float(et[0]),float(et[-1])],
            'alignment':{'type':'SE3','scale':1.0,'rotation':r.tolist(),'translation':t.tolist(),
                         'policy':'single transform using all matched camera positions'},
            'ate_m':stats(errors),'rpe_1s_translation_m':stats(relative_t),
            'rpe_1s_rotation_deg':stats(relative_r),
            'rpe_1s_timestamp_eligible_pairs':len(all_relative_t),
            'rpe_pairs_excluded_for_intervening_output_gap':excluded_gap_pairs,
            'auxiliary_rpe_1s_including_gaps_translation_m':stats(all_relative_t),
            'auxiliary_rpe_1s_including_gaps_rotation_deg':stats(all_relative_r),
            'rpe_policy':'1s +/-20ms; no intervening saved-output gap >100ms; camera-to-world relative transforms',
            'missing_output_intervals':[{'first_input':a[0],'last_input':a[-1],
                 'start':float(inputs[a[0]]),'end':float(inputs[a[-1]]),'n':len(a)} for a in gaps],
            'warning':'missing exported pose is not by itself a LOST state; see native export code and state trace'}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    with (output/'ate.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['stamp','error_m']);w.writerows(zip(et[ei],errors))
    with (output/'rpe.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['stamp_start','stamp_end','translation_m','rotation_deg']);w.writerows(rpe_rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,2,figsize=(11,7))
    ax[0,0].plot(gp[:,0,3],gp[:,1,3],label='GT',color='black')
    ax[0,0].plot(pos[:,0],pos[:,1],label='ORB-SLAM3 SE3 aligned');ax[0,0].axis('equal');ax[0,0].legend();ax[0,0].set(xlabel='x (m)',ylabel='y (m)')
    ax[0,1].plot(et[ei]-inputs[0],errors);ax[0,1].set(xlabel='time (s)',ylabel='ATE (m)')
    present=np.array([i in output_for_input for i in range(len(inputs))])
    ax[1,0].step(inputs-inputs[0],present.astype(int),where='post');ax[1,0].set(xlabel='time (s)',ylabel='exported pose',ylim=(-.1,1.1))
    ax[1,1].hist(errors,bins=30);ax[1,1].set(xlabel='ATE (m)',ylabel='frames')
    status=json.loads((run/'run.json').read_text()).get('exit_status','UNKNOWN') if (run/'run.json').exists() else 'synthetic test'
    fig.suptitle(sequence.name+' / '+run.name+' / exit '+str(status));fig.tight_layout();fig.savefig(output/'trajectory_errors.png',dpi=160);plt.close(fig)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sequence');p.add_argument('run');p.add_argument('output')
    a=p.parse_args();print(json.dumps(evaluate(a.sequence,a.run,a.output),indent=2))
