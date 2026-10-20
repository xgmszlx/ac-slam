from pathlib import Path
import json,subprocess,resource,os
D=Path(__file__).resolve().parents[1];E=Path('/media/wcqw/KESU/slam_research/ngd_ccl_compat_20261020');B=E/'ccl_probe';plan=json.loads((D/'protocol/plan.json').read_text());rows=[]
ldd=subprocess.check_output(['/usr/bin/ldd',str(B)]).decode();assert 'libopencv_' in ldd and '.so.4.2' not in ldd;(D/'audit/ccl_ldd.txt').write_text(ldd)
for name in plan['repro_cases']:
 for threads in plan['threads']:
  for alg in plan['algorithms']:
   key=f'{name}_{threads}_{alg}';prefix=E/'probe_outputs'/key;cmd=[str(B),alg,name,str(threads),str(prefix)]
   with (D/'audit'/f'{key}.log').open('w') as log:p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=15,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
   row={'case':name,'threads':threads,'algorithm':alg,'command':cmd,'returncode':p.returncode,'signal':-p.returncode if p.returncode<0 else None}
   if p.returncode==0:row['geometry']=json.loads(prefix.with_suffix('.json').read_text())
   rows.append(row)
comparisons=[]
for n in plan['repro_cases']:
 for t in plan['threads']:
  group=[r for r in rows if r['case']==n and r['threads']==t];good=[r for r in group if r['returncode']==0]
  if len(good)==2:
   a,b=[Path(r['command'][-1]) for r in good];comparisons.append({'case':n,'threads':t,**{k:Path(str(a)+'.'+k).read_bytes()==Path(str(b)+'.'+k).read_bytes() for k in ['partition','max','final']}})
result={'issue':'https://github.com/opencv/opencv/issues/21366','tests':rows,'successful_default_vs_sauf':comparisons}
(D/'results/ccl_tests.json').write_text(json.dumps(result,indent=2))
failed=next((r for r in rows if r['returncode']<0),None)
if failed:
 cmd=['/usr/bin/timeout','20','/usr/bin/gdb','-nx','-batch','-ex','set pagination off','-ex','run','-ex','thread apply all bt 8','--args']+failed['command']
 with (D/'audit/ccl_gdb.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=25)
print(json.dumps({'cases':len(rows),'default_crashes':sum(r['returncode']<0 for r in rows if r['algorithm']=='default'),'sauf_failures':sum(r['returncode']!=0 for r in rows if r['algorithm']=='sauf'),'valid_comparisons':comparisons},indent=2))
