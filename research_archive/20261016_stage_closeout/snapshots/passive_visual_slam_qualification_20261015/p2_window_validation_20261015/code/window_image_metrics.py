import pathlib,csv,json,collections,time
import cv2,numpy as np
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;D=O/'data/rgbd_dataset_freiburg3_walking_xyz';a=[l.split() for l in (D/'associations.txt').read_text().splitlines()];t0=float(a[0][0]);features=collections.defaultdict(list)
for r in csv.DictReader((N/'results/raw_ORB_features.csv').open()):features[int(r['index'])].append([float(r['x']),float(r['y']),float(r['depth_m'])])
old={int(r['index']):r for r in csv.DictReader((O/'results/walking_xyz/observer01/frame_states.csv').open())}
rows=[]
for i,row in enumerate(a):
 rel=float(row[0])-t0
 if rel<18 or rel>27:continue
 im=cv2.imread(str(D/row[1]),-1);dep=cv2.imread(str(D/row[3]),-1);gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);xy=np.array(features[i]);assert len(xy)>0
 counts=np.histogram2d(xy[:,1],xy[:,0],bins=(6,8),range=((0,480),(0,640)))[0];prob=counts.ravel()/len(xy);entropy=-np.sum(prob[prob>0]*np.log(prob[prob>0]))/np.log(48)
 evals=np.linalg.eigvalsh(np.cov((xy[:,:2]/[640,480]).T));valid=dep>0
 rows.append({'index':i,'stamp':row[0],'relative_s':rel,'depth_stamp':row[2],'RGB_depth_abs_dt_ms':abs(float(row[0])-float(row[2]))*1000,'laplacian_variance':float(cv2.Laplacian(gray,cv2.CV_64F).var()),'depth_valid_fraction':float(np.mean(valid)),'depth_valid_median_m':float(np.median(dep[valid])/5000),'raw_native_ORB_count':len(xy),'raw_ORB_depth_valid_fraction':float(np.mean(xy[:,2]>0)),'raw_ORB_8x6_occupied_fraction':float(np.mean(counts>0)),'raw_ORB_8x6_entropy':float(entropy),'raw_ORB_top_cell_fraction':float(counts.max()/len(xy)),'raw_ORB_xy_cov_ratio':float(evals[0]/evals[-1]),'old_P0_viewer_nonnull_pointers_NOT_P1_inliers':old[i]['n_nonnull_associations'],'P1_actual_inlier_IDs':'UNKNOWN'})
with (N/'results/window_image_metrics.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summ=[]
for name,lo,hi in [('normal_before',18,21),('critical',22,24.5),('normal_after',25,27)]:
 selected=[r for r in rows if lo<=r['relative_s']<=hi];res={'window':name,'start_s':lo,'end_s':hi,'frames':len(selected),'description':'raw extraction only, not optimizer inliers; blur/geometry quantities are proxies'}
 for key in ['RGB_depth_abs_dt_ms','laplacian_variance','depth_valid_fraction','raw_native_ORB_count','raw_ORB_depth_valid_fraction','raw_ORB_8x6_occupied_fraction','raw_ORB_8x6_entropy','raw_ORB_top_cell_fraction','raw_ORB_xy_cov_ratio']:
  v=[r[key] for r in selected];res[key]={'median':float(np.median(v)),'min':float(np.min(v)),'max':float(np.max(v))}
 summ.append(res)
(N/'audit/window_image_summary.json').write_text(json.dumps(summ,indent=2));print(json.dumps(summ,indent=2))
