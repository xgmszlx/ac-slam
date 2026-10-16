from common import *
import csv,time,hashlib
from scipy.special import logsumexp
native=Native();scans=json.loads((P/'data/scans.json').read_text());centers={r['id']:r for r in json.loads((P/'data/candidate_manifest.json').read_text())};rows=[];sums=[];sectors=[]
def csvout(name,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (P/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
for r in scans:
 z=np.load(P/'data'/f"{r['id']}_candidates.npz");poses=z['poses'];N=len(poses);la=np.empty(N);lp=np.empty(N)
 for start in range(0,N,2048):la[start:start+2048],lp[start:start+2048]=native.scores(r,poses[start:start+2048])
 cc=centers[r['id']]['centers'];gt=np.array(cc['GT']);named={};rawpz={};indices=None
 for name,c in cc.items():
  if c is None:continue
  aa,pp=native.scores(r,[c]);named[name]=(float(aa[0]),float(pp[0]));rawpz[name],indices,_,_,_=native.pz(r,[c]);rawpz[name]=rawpz[name][0]
  rows.append({'id':r['id'],'sequence':r['sequence'],'target_s':r['target_s'],'actual_s':r['actual_relative_s'],'candidate':name,'x':c[0],'y':c[1],'yaw_deg':float(np.degrees(c[2])),'xy_error_m':float(np.linalg.norm(np.array(c[:2])-gt[:2])),'yaw_error_deg':float(abs(np.degrees(np.arctan2(np.sin(c[2]-gt[2]),np.cos(c[2]-gt[2]))))),'add_log_score':float(aa[0]),'product_log_score':float(pp[0]),'add_delta_log_to_GT':float(aa[0]-named['GT'][0]),'product_delta_log_to_GT':float(pp[0]-named['GT'][1]),'add_rank_union':int(1+np.sum(la>aa[0]+1e-12)),'product_rank_union':int(1+np.sum(lp>pp[0]+1e-12)),'total_unique_candidates':N})
 err=np.linalg.norm(poses[:,:2]-gt[:2],axis=1);yawerr=np.abs(np.arctan2(np.sin(poses[:,2]-gt[2]),np.cos(poses[:,2]-gt[2])));near=(err<=.2+1e-12)&(yawerr<=np.deg2rad(10)+1e-12);far=err>.6+1e-12
 gi=z['grid_member_indices'][list(z['names']).index('GT')];nx=25;ny=25;na=21;rr,bb=native.prepare(r)
 sectoridx=np.digitize(np.degrees(r['angle_min']+indices*r['angle_increment']),[-81,-27,27,81]);assert set(sectoridx)<=set(range(5))
 for model,scores in [('add',la),('product',lp)]:
  win=int(np.argmax(scores));g=scores[gi];mass=np.exp(g-logsumexp(g));profile=g.reshape(nx,ny,na).max(axis=2);mask=profile>=profile.max()+np.log(.5);ix,iy=np.where(mask)
  sums.append({'id':r['id'],'sequence':r['sequence'],'target_s':r['target_s'],'actual_s':r['actual_relative_s'],'model':model,'valid_beams':len(indices),'physical_slots':91,'candidate_count':N,'best_x':float(poses[win,0]),'best_y':float(poses[win,1]),'best_yaw_deg':float(np.degrees(poses[win,2])),'best_xy_error_m':float(err[win]),'best_yaw_error_deg':float(np.degrees(yawerr[win])),'best_log_score':float(scores[win]),'GT_log_score':named['GT'][0 if model=='add' else 1],'GT_relative_to_union_best':float(np.exp(named['GT'][0 if model=='add' else 1]-scores[win])),'best_near_GT_log':float(scores[near].max()),'best_far_log':float(scores[far].max()) if far.any() else None,'far_minus_near_log':float(scores[far].max()-scores[near].max()) if far.any() else None,'GT_grid_score_ESS_proxy':float(1./np.sum(mass*mass)),'GT_grid_ESS_proxy_fraction':float(1./np.sum(mass*mass)/len(gi)),'GT_grid_half_height_xy_extent_x_m':float((ix.max()-ix.min())*.05),'GT_grid_half_height_xy_extent_y_m':float((iy.max()-iy.min())*.05),'GT_grid_half_height_xy_cell_fraction':float(mask.mean()),'width_note':'Bounding extents of max-over-yaw half-height support; may be disconnected/truncated; heuristic score for add, not calibrated covariance'})
 for name in named:
  if name=='GT':continue
  d0=rawpz[name]**3-rawpz['GT']**3;d1=np.log(rawpz[name])-np.log(rawpz['GT']);assert np.allclose(d1.sum(),named[name][1]-named['GT'][1],atol=1e-10)
  for sector in range(5):
   m=sectoridx==sector;sectors.append({'id':r['id'],'sequence':r['sequence'],'target_s':r['target_s'],'candidate':name,'sector':sector,'sector_start_deg':[-135,-81,-27,27,81][sector],'sector_end_deg':[-81,-27,27,81,135][sector],'valid_beams':int(m.sum()),'add_raw_score_delta_to_GT':float(d0[m].sum()),'product_log_score_delta_to_GT':float(d1[m].sum())})
 np.savez_compressed(P/'results'/f"{r['id']}_profiles.npz",add_log=la,product_log=lp,named_names=np.array(list(rawpz)),named_pz=np.array(list(rawpz.values())),valid_indices=indices)
 print(r['id'],len(poses),'candidates scored',flush=True)
csvout('results/named_candidate_scores.csv',rows);csvout('results/profile_summary.csv',sums);csvout('results/sector_contributions.csv',sectors)
(P/'results/summary.json').write_text(json.dumps({'named_candidates':rows,'profiles':sums,'unit':'OFFLINE_DIAGNOSTIC; same91 physical slots; invalid omitted equally; no historical particle support reconstruction','any_new_filter_run':False},indent=2))
