"""Offline validation only. Does not download, copy, infer, or start SLAM."""
import sys,pathlib,hashlib,json
p=pathlib.Path(sys.argv[1]);b=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
r={'file':str(p),'bytes':len(b),'git_blob_sha1':blob,'sha256':hashlib.sha256(b).hexdigest(),'fixed_author_commit':'bb17b6c3eef36d80be441ae8e5339be66e8e3b7a','PASS':len(b)==23306119 and blob=='253e5012dd6a17666fd7ae16cfa14a6860280ff7'}
print(json.dumps(r,indent=2));sys.exit(0 if r['PASS'] else 1)
