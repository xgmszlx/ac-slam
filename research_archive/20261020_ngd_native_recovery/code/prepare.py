from pathlib import Path,PurePosixPath
import hashlib,json,zipfile,tarfile,subprocess,os
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020')
main=Path('/home/wcqw/ac-slam');old=Path('/home/wcqw/ngd_slam_incremental_20261020')
h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
g=lambda a:subprocess.check_output(['git','-C',str(main)]+a).decode()
protected=[old/'REPORT.md',old/'REPRODUCE.md',old/'audit/source_version.json',main/'tools/realizability_pilot/same_input_replay.py',main/'tools/realizability_pilot/se2_information.py']
(D/'protocol/protection_before.json').write_text(json.dumps({'files':{str(p):h(p) for p in protected},'head':g(['rev-parse','HEAD']),'status':g(['status','--porcelain']),'diff_sha256':hashlib.sha256(g(['diff']).encode()).hexdigest()},indent=2))
p=main/'NGD-SLAM-a93a14c4019efc7a209be5fbf9fefa46f5d1d90f.zip';records={}
with zipfile.ZipFile(p) as z:
 root=z.infolist()[0].filename.split('/')[0]+'/';assert z.comment.decode()=='a93a14c4019efc7a209be5fbf9fefa46f5d1d90f'
 for i in z.infolist():
  rel=i.filename[len(root):]
  if not rel or i.is_dir():continue
  if not (rel.startswith(('src/','include/','Thirdparty/','Vocabulary/','cmake_modules/','Examples/','Examples_old/')) or rel in ['CMakeLists.txt','README.md','LICENSE','build.sh']):continue
  # Association lists are not build inputs; keep every example source/configuration.
  if rel.startswith(('Examples/','Examples_old/')) and not rel.endswith(('.cc','.cpp','.h','.hpp','.yaml','.yml','.cmake','CMakeLists.txt')):continue
  assert not PurePosixPath(rel).is_absolute() and '..' not in PurePosixPath(rel).parts
  b=z.read(i) # verifies CRC of every extracted member
  dst=E/'NGD-SLAM'/rel;dst.parent.mkdir(parents=True,exist_ok=True);assert not dst.exists();dst.write_bytes(b)
  records[rel]={'bytes':len(b),'git_blob':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'sha256':hashlib.sha256(b).hexdigest()}
 req=['src/Tracking.cc','include/System.h','Examples/RGB-D/rgbd_tum.cc','CMakeLists.txt','Thirdparty/YOLO/coco.names','Thirdparty/YOLO/yolo-fastest-xl.cfg','Thirdparty/YOLO/yolo-fastest-xl.weights']
 assert all(r in records for r in req)
 assert records[req[-1]]['bytes']==3650764 and records[req[-1]]['git_blob']=='9180f4fb2c97d8acbb94ed0936849847c936b454'
 source={'archive':str(p),'bytes':p.stat().st_size,'sha256':h(p),'comment':z.comment.decode(),'extracted_count':len(records),'files':records,'crc_scope':'all extracted necessary members; not unrelated unextracted association files'}
(D/'audit/source_acceptance.json').write_text(json.dumps(source,indent=2))
p=main/'opencv-4.5.5.tar.gz'
with tarfile.open(p) as t:
 for m in t.getmembers():
  assert not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts
 members=t.getmembers()
 t.extractall(E)
(D/'audit/opencv_archive.json').write_text(json.dumps({'path':str(p),'bytes':p.stat().st_size,'sha256':h(p),'source':'user-supplied official OpenCV 4.5.5 archive; local hash, not claimed independently published checksum','expanded_bytes':sum(m.size for m in members)},indent=2))
print('Accepted NGD required files',len(records),'and OpenCV source')
