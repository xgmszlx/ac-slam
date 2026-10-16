import pathlib,json,hashlib,time,csv
import cv2,numpy as np
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent
assert not json.loads((N/'audit/P1_gate.json').read_text())['solves']
model=N/'models/mobilenet_iter_73000.caffemodel';proto=N/'audit/detector_source/deploy.prototxt'
assert 20000000<model.stat().st_size<30000000
cv2.setNumThreads(1)
net=cv2.dnn.readNetFromCaffe(str(proto),str(model));net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV);net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
summary={'model_commit':'bb17b6c3eef36d80be441ae8e5339be66e8e3b7a','model_sha256':sha(model),'model_bytes':model.stat().st_size,'prototxt_sha256':sha(proto),'opencv':cv2.__version__,'threshold':.5,'person_class':15,'input':'current RGB image only; imread BGR model convention','blob':'300x300 scale0.007843 mean127.5 swapRB=false crop=false','threads':1,'GT_or_future':False,'sequences':{}}
start=time.monotonic()
for name,step in [('walking',83),('sitting',122)]:
 d=O/'data'/('rgbd_dataset_freiburg3_'+name+'_xyz');rows=[r.split() for r in (d/'associations.txt').read_text().splitlines()];out=N/'masks'/name;out.mkdir(exist_ok=True)
 samples=sorted(set(list(range(0,len(rows),step))+[len(rows)-1]));data=[];tiles=[]
 for i,row in enumerate(rows):
  im=cv2.imread(str(d/row[1]),-1);assert im.shape==(480,640,3);before=hashlib.sha256(im.tobytes()).hexdigest();mask=np.zeros(im.shape[:2],np.uint8)
  t=time.monotonic();blob=cv2.dnn.blobFromImage(im,.007843,(300,300),127.5,swapRB=False,crop=False);net.setInput(blob);pred=net.forward();elapsed=time.monotonic()-t
  assert np.all(np.isfinite(pred));boxes=[]
  for det in pred[0,0]:
   if int(det[1])!=15 or det[2]<.5:continue
   x1,y1,x2,y2=(det[3:7]*[640,480,640,480]).astype(int);x1=max(0,min(640,int(x1)));x2=max(0,min(640,int(x2)));y1=max(0,min(480,int(y1)));y2=max(0,min(480,int(y2)))
   if x2<=x1 or y2<=y1:continue
   mask[y1:y2,x1:x2]=255;boxes.append({'xyxy':[x1,y1,x2,y2],'confidence':float(det[2])})
  assert before==hashlib.sha256(im.tobytes()).hexdigest()
  mp=out/(pathlib.Path(row[1]).stem+'.png');assert not mp.exists();assert cv2.imwrite(str(mp),mask)
  data.append({'index':i,'stamp':row[0],'rgb':row[1],'mask':mp.name,'rgb_file_sha256':sha(d/row[1]),'mask_sha256':sha(mp),'inference_s':elapsed,'area_fraction':float(np.mean(mask>0)),'detections':boxes,'valid':True})
  if i in samples:
   view=im.copy();view[mask>0]=(view[mask>0].astype(float)*.55+np.array([0,0,255])*.45).astype(np.uint8)
   for b in boxes:
    x1,y1,x2,y2=b['xyxy'];cv2.rectangle(view,(x1,y1),(x2-1,y2-1),(0,255,0),2)
   cv2.putText(view,f'{name} frame {i}, persons {len(boxes)}',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,255,255),2)
   tiles.append(cv2.resize(view,(320,240)))
  if i%200==0:print(name,i,'inference',round(elapsed,4),flush=True)
 (out/'manifest.json').write_text(json.dumps(data,indent=2))
 while len(tiles)%3:tiles.append(np.zeros_like(tiles[0]))
 sheet=np.vstack([np.hstack(tiles[k:k+3]) for k in range(0,len(tiles),3)]);cv2.imwrite(str(N/'figures'/('mask_quality_'+name+'.jpg')),sheet)
 times=[r['inference_s'] for r in data];summary['sequences'][name]={'frames':len(data),'valid_masks':len(data),'missing_or_failed':0,'zero_person_frames':sum(not r['detections'] for r in data),'sample_indices':samples,'total_inference_s':sum(times),'mean_inference_s':float(np.mean(times)),'p90_inference_s':float(np.quantile(times,.9)),'mean_area_fraction':float(np.mean([r['area_fraction'] for r in data])),'manifest_sha256':sha(out/'manifest.json')}
summary['total_wall_s']=time.monotonic()-start;(N/'audit/mask_generation.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
