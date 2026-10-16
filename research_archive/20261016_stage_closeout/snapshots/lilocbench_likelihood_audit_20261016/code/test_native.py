from common import *
import hashlib,time
n=Native();records=json.loads((P/'data/scans.json').read_text());centers={r['id']:r for r in json.loads((P/'data/candidate_manifest.json').read_text())};rows=[]
for r in records:
 for name,pose in centers[r['id']]['centers'].items():
  if pose is None:continue
  la,lp=n.scores(r,[pose]);ca=n.native_score(r,pose,0);cp=n.native_score(r,pose,1)
  assert ca>0 and cp>0
  errA=abs(np.log(ca)-la[0]);errP=abs(np.log(cp)-lp[0]);assert errA<=1e-10 and errP<=1e-10,(r['id'],name,errA,errP)
  # Original A0 stride102 equivalence check is separate from the main common91 comparison.
  native102=n.native_score(r,pose,0,False);pz,_,_,_,_=n.pz(r,[pose],np.arange(0,811,8));py102=1.+np.sum(pz**3);err102=abs(np.log(native102)-np.log(py102));assert err102<=1e-10
  rows.append({'id':r['id'],'center':name,'common91_add_log_abs_error':float(errA),'common91_product_log_abs_error':float(errP),'native102_add_log_abs_error':float(err102)})
# Pure coordinate and probability edge controls without scores outside the fixed candidates.
assert len(np.arange(0,811,9))==91 and len(np.arange(0,811,8))==102
rr,bb=n.prepare(records[0]);assert np.all(np.diff(bb)>0)
pz=.95*np.exp(-2.*2./(.08))+.05/100.;assert pz>.0
meta={'width':n.nx,'height':n.ny,'scale_float32_promoted':n.scale,'AMCL_origin_xy':[n.ox,n.oy],'grid_origin_xy':[-25,-25],'states':{str(int(x)):int((n.state==x).sum()) for x in np.unique(n.state)},'native_distance_field':True,'lib_sha256':hashlib.sha256((B/'diagnostic_ws_v2/devel/lib/libamcl_sensors.so').read_bytes()).hexdigest()}
np.savez_compressed(P/'data/native_map.npz',state=n.state,distance=n.dist,metadata=np.array([n.nx,n.ny,n.scale,n.ox,n.oy]))
(P/'audit/map_metadata.json').write_text(json.dumps(meta,indent=2));(P/'audit/native_equivalence.json').write_text(json.dumps({'status':'PASS','scope':'Native installed map loader + fixed built AMCL cspace; native sensor static functions, no PF/ROS node; A0 common91 uses offline max_beams91 solely to select stride9; native stride102 checked separately','tests':rows,'max_log_abs_error':max(max(r[k] for k in r if k.endswith('error')) for r in rows),'scored_center_count':len(rows),'pointwise_pz_equivalence':'Native aggregate checks, not a separate complete per-beam native trace','GT_yaw_projection':'official intrinsic ZYX','map':meta},indent=2));print('PASS',len(rows),'center tests, max log error',max(max(r[k] for k in r if k.endswith('error')) for r in rows));print(meta)
