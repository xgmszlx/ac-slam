"""Offline-only screening IO. All writes confined to this new worktree."""
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
ASSETS=Path('/home/wcqw/ac-slam')
OUT=ROOT/'results/research_direction/alc_revisit_screening'
DOC79=ASSETS/'results/realizability_pilot/p1_doc79_synchronous_revisit_validation_20261012'
DOC80=ASSETS/'results/realizability_pilot/p1_doc80_offline_research_convergence_20261013'
BASELINE='4746834ffa44504443fd07214105fe850d6f94e6'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def write_json(relative,obj):
    p=OUT/relative
    try:p.resolve().relative_to(OUT.resolve())
    except ValueError:raise ValueError('Output escapes screening root')
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def csv_out(relative,rows):
    rows=list(rows)
    if not rows:return
    p=OUT/relative
    try:p.resolve().relative_to(OUT.resolve())
    except ValueError:raise ValueError('Output escapes screening root')
    p.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


class Inputs:
    def __init__(self):self.files={};self.missing=[]
    def register(self,p):
        p=Path(p)
        if not p.is_file():self.missing.append(str(p));return False
        if str(p) not in self.files:self.files[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
        return True
    def json(self,p,required=True):
        if not self.register(p):
            if required:raise FileNotFoundError(str(p))
            return None
        return json.loads(Path(p).read_text())
    def csv(self,p):
        if not self.register(p):return []
        with Path(p).open() as f:return list(csv.DictReader(f))
    def lines(self,p):
        if not self.register(p):return
        with Path(p).open() as f:
            for line in f:
                if line.strip():yield json.loads(line)
    def verify(self):
        changed=[p for p,r in self.files.items() if not Path(p).is_file() or sha(p)!=r['sha256']]
        write_json('audit/input_integrity.json',{'checked_files':len(self.files),'all_unchanged':not changed,
                   'changed':changed,'missing':sorted(set(self.missing)),'source_commit':BASELINE,
                   'no_ros_or_simulation_started':True,'scope':'files actually registered/read; not all ignored old raw'})
        write_json('audit/input_hashes.json',self.files)
        if changed:raise RuntimeError('Read input modified: '+str(changed))


def wrap(a):return math.atan2(math.sin(a),math.cos(a))
def compose(a,b):
    c,s=math.cos(a[2]),math.sin(a[2]);return [a[0]+c*b[0]-s*b[1],a[1]+s*b[0]+c*b[1],wrap(a[2]+b[2])]
def base_pose(n):return compose([n['x'],n['y'],n['theta']],[-.2,0.,0.])
def distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])
def path_length(points):return sum(distance(a,b) for a,b in zip(points,points[1:]))
def turning(points):return sum(abs(wrap(b[2]-a[2])) for a,b in zip(points,points[1:]))


def workspace_snapshot():
    report={}
    for key,path in [('main',ASSETS),('doc81',Path('/home/wcqw/ac-slam_doc81'))]:
        commands={name:subprocess.check_output(['git','-C',str(path)]+args).decode().strip() for name,args in
                  [('head',['rev-parse','HEAD']),('branch',['branch','--show-current']),('status',['status','--porcelain'])]}
        commands['user_file_sha256']={n:sha(path/n) for n in ('tools/realizability_pilot/same_input_replay.py','tools/realizability_pilot/se2_information.py') if (path/n).is_file()}
        report[key]=commands
    return report
