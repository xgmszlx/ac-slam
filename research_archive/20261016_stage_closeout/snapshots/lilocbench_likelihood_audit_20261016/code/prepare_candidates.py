from common import *
import hashlib,time
protocol=json.loads((P/'protocol/design_frozen.json').read_text());scans=json.loads((P/'data/scans.json').read_text());records=[]
off=np.stack(np.meshgrid(np.arange(-12,13)*.05,np.arange(-12,13)*.05,np.deg2rad(np.arange(-10,11)*2),indexing='ij'),axis=-1).reshape(-1,3)
for r in scans:
 stamp=r['scan_stamp_ns']/1e9;centers={};support={}
 centers['GT'],support['GT']=interpolate(B/'data/gt'/r['sequence']/'gt_poses.txt',stamp)
 for a in ['A0','A1','A2']:centers[a],support[a]=interpolate(Path(protocol['references'][r['sequence']][a])/'trajectory.txt',stamp)
 assert centers['GT'] is not None
 grids=[];names=[]
 for name,center in centers.items():
  if center is None:continue
  grid=np.array(center)+off;grid[:,2]=np.arctan2(np.sin(grid[:,2]),np.cos(grid[:,2]));grids.append(grid);names.append(name)
 poses,inverse=np.unique(np.concatenate(grids),axis=0,return_inverse=True)
 member=inverse.reshape(len(names),len(off));np.savez_compressed(P/'data'/f"{r['id']}_candidates.npz",poses=poses,grid_member_indices=member,offsets=off,names=np.array(names))
 records.append({'id':r['id'],'centers':centers,'support':support,'grid_names':names,'per_center_count':len(off),'unique_candidate_count':len(poses)})
(P/'data/candidate_manifest.json').write_text(json.dumps(records,indent=2))
files=list((P/'data').glob('*'))+[P/'protocol/design_frozen.json',P/'sources/native_probe.cpp',P/'build/native_probe.so',P/'code/common.py',P/'code/prepare_candidates.py']
(P/'protocol/candidates_frozen_before_scores.json').write_text(json.dumps({'wall':time.time(),'any_likelihood_computed':False,'centers_and_grids':records,'hashes':{str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}},indent=2))
print('Frozen 12 scans and all candidates before scoring:',sum(r['unique_candidate_count'] for r in records));print('Missing centers:',[(r['id'],[k for k,v in r['centers'].items() if v is None]) for r in records])
