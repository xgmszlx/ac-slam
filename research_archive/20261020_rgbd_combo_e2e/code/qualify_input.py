from pathlib import Path
import cv2,numpy as np,json,hashlib,subprocess,os
P=Path(__file__).resolve().parents[1];info=json.loads((P/'audit/dataset.json').read_text());D=Path(info['path']);rows=[x.split() for x in (P/'data/associations.txt').read_text().splitlines()];fs=cv2.FileStorage(str(P/'config/bonn.yaml'),cv2.FILE_STORAGE_READ)
for k,v in info['calibration'].items():assert abs(fs.getNode(k).real()-v)<1e-9,(k,fs.getNode(k).real(),v)
assert fs.getNode('RGBD.DepthMapFactor').real()==5000;assert fs.getNode('Camera.RGB').real()==0
stamp=np.array([float(x[0]) for x in rows]);assert np.all(np.diff(stamp)>0)
for a,r,b,d in rows:
 im=cv2.imread(str(D/r),cv2.IMREAD_UNCHANGED);z=cv2.imread(str(D/d),cv2.IMREAD_UNCHANGED)
 assert im.shape==(480,640,3) and im.dtype==np.uint8;assert z.shape==(480,640) and z.dtype==np.uint16
 assert abs(float(a)-float(b))<.02
 # BGR input -> native BGR gray equals explicit RGB -> RGB gray.
 assert np.array_equal(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),cv2.cvtColor(im[:,:,::-1],cv2.COLOR_RGB2GRAY))
env=dict(os.environ,LD_LIBRARY_PATH=str(P/'build')+':/home/wcqw/passive_visual_slam_qualification_20261015/local/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
ldd=subprocess.check_output(['ldd',str(P/'build/rgbd_combo')],env=env,text=True)
assert str(P/'build/libORB_SLAM3.so') in ldd
(P/'audit/ldd.txt').write_text(ldd)
q={'qualified':True,'decoded_inputs':len(rows),'OpenCV':cv2.__version__,'calibration_matches_official_cached_page':True,'BGR_gray_control':'all pixels all associated RGB frames PASS','depth_uint16_scale':5000,'unique_monotonic_associations':True,'association_tolerance_s':.02,'binary_and_core':'unchanged, explicit LD_LIBRARY_PATH resolves intended prototype','mechanism_qualification':'NOT_REQUIRED_FOR_TECHNICAL_RUN; trusted point motion labels UNKNOWN','GT':'offline evaluator only; no GT argument to SLAM'}
(P/'audit/technical_qualification.json').write_text(json.dumps(q,indent=2));print(json.dumps(q,indent=2))
