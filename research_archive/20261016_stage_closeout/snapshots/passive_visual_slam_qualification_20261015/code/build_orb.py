"""Build pinned official source with only audited dependency compatibility changes."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess
import tarfile

p=Path(__file__).resolve().parents[1]
archive=p/'sources/orb_official.tar.gz'
if (p/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4').exists():
    raise RuntimeError('Use a fresh workspace; existing source/results must not be overwritten')
with tarfile.open(archive) as tar:
    members=tar.getmembers()
    # Unrelated TUM inertial text assets account for most of the official tree.
    chosen=[m for m in members if '/TUM_IMU/' not in m.name]
    (p/'audit/source_extraction.json').write_text(json.dumps({
        'archive_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),
        'all_file_bytes':sum(m.size for m in members if m.isfile()),
        'extracted_file_bytes':sum(m.size for m in chosen if m.isfile()),
        'excluded':[m.name for m in members if m not in chosen]},indent=2))
    tar.extractall(p/'sources',members=chosen,filter='data')
src=p/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4'
patch=[]
for name in ['CMakeLists.txt','Thirdparty/DBoW2/CMakeLists.txt']:
    path=src/name;old=path.read_text();new=old.replace('find_package(OpenCV 4.4)','find_package(OpenCV 4.2)')
    if old!=new:
        (p/'sources'/('pristine_'+name.replace('/','_'))).write_text(old)
        path.write_text(new)
        patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),'a/'+name,'b/'+name))
(p/'patches/build_opencv42.patch').write_text(''.join(patch))
commands=[]
for name in ['Thirdparty/DBoW2','Thirdparty/g2o']:
    d=src/name
    commands.extend([['cmake','-S',str(d),'-B',str(d/'build'),'-DCMAKE_BUILD_TYPE=Release'],
                     ['cmake','--build',str(d/'build'),'-j2']])
commands.extend([['cmake','-S',str(src),'-B',str(src/'build'),'-DCMAKE_BUILD_TYPE=Release',
                 '-DPangolin_DIR='+str(p/'local/lib/cmake/Pangolin')],
                 ['cmake','--build',str(src/'build'),'--target','rgbd_tum','-j2']])
(p/'audit/orb_build_commands.json').write_text(json.dumps(commands,indent=2))
with (p/'audit/orb_build01.log').open('w') as log:
    for command in commands:
        log.write('\nCOMMAND '+str(command)+'\n');log.flush()
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        print('exit',result.returncode,command[:4],flush=True)
        if result.returncode:raise SystemExit(result.returncode)
vocab=src/'Vocabulary/ORBvoc.txt'
if not vocab.exists():
    with tarfile.open(src/'Vocabulary/ORBvoc.txt.tar.gz') as tar:tar.extractall(vocab.parent,filter='data')
print('BUILD COMPLETE',flush=True)
