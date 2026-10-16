"""Run a complete frozen RGB-D input list, keeping failures and exit evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

p=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('sequence');parser.add_argument('run_name')
parser.add_argument('--trace',action='store_true');parser.add_argument('--gdb',action='store_true')
parser.add_argument('--headless',action='store_true');a=parser.parse_args()
src=p/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4'
sequence=p/'data'/('rgbd_dataset_freiburg3_'+a.sequence)
out=p/'results'/a.sequence/a.run_name
out.mkdir(parents=True,exist_ok=False)
binary=src/'Examples/RGB-D'/('rgbd_tum_headless' if a.headless else ('rgbd_tum_trace' if a.trace else 'rgbd_tum'))
command=[str(binary),str(src/'Vocabulary/ORBvoc.txt'),str(src/'Examples/RGB-D/TUM3.yaml'),str(sequence),str(sequence/'associations.txt')]
target_command=list(command)
if a.gdb:
    command=['gdb','--batch','--return-child-result','-ex','set pagination off','-ex','run',
             '-ex','thread apply all bt 12','-ex','info threads','--args']+command
env=os.environ.copy();env['LD_LIBRARY_PATH']=str(p/'local/lib')+':'+env.get('LD_LIBRARY_PATH','')
x={'command':command,'working_directory':str(out),'official_commit':'4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4',
   'input_frames':len((sequence/'associations.txt').read_text().splitlines()),
   'library_sha256':hashlib.file_digest((src/'lib/libORB_SLAM3.so').open('rb'),'sha256').hexdigest(),
   'binary_sha256':hashlib.file_digest(binary.open('rb'),'sha256').hexdigest(),
   'calibration_sha256':hashlib.file_digest((src/'Examples/RGB-D/TUM3.yaml').open('rb'),'sha256').hexdigest(),
   'gt_in_command':False,'trace':a.trace,'debugger':a.gdb,'target_command':target_command,'start_unix':time.time()}
(out/'run.json').write_text(json.dumps(x,indent=2))
start=time.monotonic()
try:
    with (out/'stdout.log').open('w') as log:
        process=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    x['exit_status']=process.returncode
except subprocess.TimeoutExpired:
    x['exit_status']='TIMEOUT_900_SECONDS'
x.update(elapsed_wall_s=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
if a.gdb:
    text=(out/'stdout.log').read_text(errors='replace')
    x['debugger_signal_lines']=[line for line in text.splitlines() if 'received signal' in line or 'exited normally' in line or 'exited with code' in line]
x['outputs']={f.name:f.stat().st_size for f in out.iterdir() if f.is_file()}
(out/'run.json').write_text(json.dumps(x,indent=2));print(json.dumps(x,indent=2))
