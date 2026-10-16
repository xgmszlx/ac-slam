import pathlib,json,csv,cv2,numpy as np
N=pathlib.Path(__file__).resolve().parents[1];D=N.parent/'data/rgbd_dataset_freiburg3_walking_xyz';p=json.loads((N/'protocol/design_v02.json').read_text());old=list(csv.DictReader((N/'results/matches.csv').open()));orb=cv2.ORB_create(nfeatures=1000,scaleFactor=1.2,nlevels=8,edgeThreshold=31,firstLevel=0,WTA_K=2,scoreType=cv2.ORB_HARRIS_SCORE,patchSize=31,fastThreshold=20);cv2.setNumThreads(1);checks=[]
for pair in p['pairs']:
 desc=[]
 for f in pair['frames']:
  im=cv2.imread(str(D/f['rgb']),-1);keys,ds=orb.detectAndCompute(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),None);desc.append(ds)
 cross=cv2.BFMatcher(cv2.NORM_HAMMING,crossCheck=True).match(*desc);reference={(m.queryIdx,m.trainIdx) for m in cross};ours={(int(r['queryIdx']),int(r['trainIdx'])) for r in old if r['pair']==pair['id'] and r['mutual_NN']=='1'};assert reference==ours
 checks.append({'pair':pair['id'],'independent_crossCheck_matches':len(reference),'same_indices':True})
(N/'audit/matching_unit_tests.json').write_text(json.dumps({'PASS':True,'checks':checks,'scope':'independent OpenCV crossCheck matcher verifies saved mutual NN identities, not SLAM identities'},indent=2));print('9 pairs independent crossCheck identities PASS')
