import hashlib, json, pathlib, subprocess, shutil
ROOT = pathlib.Path('/home/wcqw/passive_visual_slam_v2_v3_screen_20261015')
OLD = pathlib.Path('/home/wcqw/passive_visual_slam_qualification_20261015')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def snapshot():
    files={}; manifest_checks=[]
    for sub in ['', 'diagnostic_comparison_20261015','p2_window_validation_20261015','offline_correspondence_audit_20261015']:
        d=OLD/sub; manifest=d/'MANIFEST.json'; m=json.loads(manifest.read_text())
        files[str(manifest)]=sha(manifest)
        for rel,v in m.items():
            p=d/rel
            if not p.is_file():
                manifest_checks.append({'file':str(p),'status':'MISSING'}); continue
            actual=sha(p); files[str(p)]=actual
            if actual!=v['sha256']: manifest_checks.append({'file':str(p),'status':'MISMATCH'})
    git={}
    for name,args in [('head',['rev-parse','HEAD']),('status',['status','--porcelain=v1']),('diff',['diff','--binary'])]:
        git[name]=subprocess.check_output(['git','-C','/home/wcqw/ac-slam']+args).decode()
    disk=shutil.disk_usage('/')
    return dict(files=files,checked_files=len(files),manifest_issues=manifest_checks,git=git,disk_free_bytes=disk.free)
if __name__=='__main__':
    import sys
    x=snapshot(); mode=sys.argv[1]
    if mode=='after':
        b=json.loads((ROOT/'audit/protection_before.json').read_text())
        x['files_equal']=x['files']==b['files']; x['git_equal']=x['git']==b['git']
    (ROOT/f'audit/protection_{mode}.json').write_text(json.dumps(x,indent=2))
    print(json.dumps({k:v for k,v in x.items() if k not in ['files','git']}))
