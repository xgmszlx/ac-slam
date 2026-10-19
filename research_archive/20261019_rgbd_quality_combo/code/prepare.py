from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parents[1];acq=json.loads((P/'audit/data_acquisition.json').read_text());assert acq['qualified']
folders=list((P/'data').glob('**/rgb.txt'));assert len(folders)==1;D=folders[0].parent
rows=lambda p:[s.split() for s in p.read_text().splitlines() if s.strip() and not s.startswith('#')]
rgb=rows(D/'rgb.txt');dep=rows(D/'depth.txt');gt=np.loadtxt(D/'groundtruth.txt');assert np.all(np.diff(gt[:,0])>0)
a=np.array([float(x[0]) for x in rgb]);b=np.array([float(x[0]) for x in dep]);assert np.all(np.diff(a)>0) and np.all(np.diff(b)>0)
candidates=sorted((abs(t-b[j]),i,j) for i,t in enumerate(a) for j in range(np.searchsorted(b,t-.02,side='right'),np.searchsorted(b,t+.02,side='left')));seenr=set();seend=set();pairs=[]
for _,i,j in candidates:
 if i not in seenr and j not in seend:seenr.add(i);seend.add(j);pairs.append((i,j))
assoc=[[*rgb[i],*dep[j]] for i,j in sorted(pairs)];(P/'data/associations.txt').write_text(''.join(' '.join(q)+'\n' for q in assoc));(D/'associations.txt').write_text((P/'data/associations.txt').read_text())
valid=[];hashes={}
for q in assoc:
 im=Image.open(D/q[1]);z=np.array(Image.open(D/q[3]));assert im.size==(640,480) and z.shape==(480,640) and z.dtype==np.uint16;valid.append(float(np.mean(z>0)))
 for f in [q[1],q[3]]:hashes[f]=hashlib.sha256((D/f).read_bytes()).hexdigest()
(P/'data/image_hashes.json').write_text(json.dumps(hashes,indent=2))
yaml=Path('/home/wcqw/passive_rgbd_depth_screen_20261019/config/large_cabinet.yaml').read_text();params={'Camera1.fx':542.822841,'Camera1.fy':542.576870,'Camera1.cx':315.593520,'Camera1.cy':237.756098,'Camera1.k1':.039903,'Camera1.k2':-.099343,'Camera1.p1':-.000730,'Camera1.p2':-.000144,'Camera1.k3':0.0,'Camera.RGB':0}
import re
for k,v in params.items():yaml=re.sub(r'^'+re.escape(k)+r':.*$',k+': '+str(v),yaml,flags=re.M)
(P/'config/bonn.yaml').write_text(yaml)
counts={'path':str(D),'RGB_rows':len(rgb),'depth_rows':len(dep),'associated_inputs':len(assoc),'RGB_range':[a[0],a[-1]],'depth_range':[b[0],b[-1]],'input_duration_s':float(assoc[-1][0])-float(assoc[0][0]),'GT_rows':len(gt),'GT_range':[gt[0,0],gt[-1,0]],'GT_quaternion_norm_minmax':[float(np.linalg.norm(gt[:,4:8],axis=1).min()),float(np.linalg.norm(gt[:,4:8],axis=1).max())],'RGB_depth_dt_ms_max':max(abs(float(q[0])-float(q[2]))*1000 for q in assoc),'valid_depth_fraction_mean':float(np.mean(valid)),'calibration':params,'depth_scale':5000,'virtual_Stereo_b':.0747,'effective_bf':542.822841*.0747,'bf_note':'Preserved virtual Stereo.b=.0747 and ThDepth40 across S0/S1/S2; not a physical Bonn baseline.'}
(P/'audit/dataset.json').write_text(json.dumps(counts,indent=2))
# Only three fixed inspection pairs, 30/50/70% time, .2s apart, before labels/algorithm scores.
times=np.array([float(q[0]) for q in assoc]);ps=[]
for n,fraction in enumerate([.3,.5,.7]):
 t=times[0]+fraction*(times[-1]-times[0]);ids=[int(np.argmin(abs(times-(t+delta)))) for delta in [0,.2]];fs=[]
 for idx in ids:
  q=assoc[idx];fs.append({'index':idx,'stamp':q[0],'relative_s':float(q[0])-times[0],'rgb':q[1],'depth_stamp':q[2],'depth':q[3]})
 ps.append({'id':f'box_{n+1}','frames':fs})
(P/'protocol/inspection_pairs.json').write_text(json.dumps({'selection':'30/50/70 percent input duration, .2s target separation; no residual/SLAM score used','pairs':ps},indent=2))
sheet=Image.new('RGB',(1280,510*3),'white');dr=ImageDraw.Draw(sheet)
for n,p in enumerate(ps):
 for e,f in enumerate(p['frames']):sheet.paste(Image.open(D/f['rgb']),(e*640,n*510+30));dr.text((e*640+5,n*510+5),f"{p['id']} frame {f['index']} t={f['relative_s']:.3f}s",fill='black')
sheet.save(P/'annotations/inspection_raw.jpg');print(json.dumps(counts,indent=2));print(ps)
