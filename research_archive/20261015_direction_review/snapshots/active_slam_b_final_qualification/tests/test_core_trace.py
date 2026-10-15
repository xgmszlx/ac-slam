"""Diagnostic invariance gate. Existing pair files only; no ROS init or master."""
import argparse,os,subprocess,json,csv
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=Path('/home/wcqw/active_slam_ab_decision_20261014')
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
rows=[]
for name in ['corner','structure_view','changed_front','changed_side','symmetric_front','symmetric_side']:
 side=name.endswith('side') or name=='structure_view';guess=[.2,.40000000000000036,1.5907963267948966] if side else [.6000000000000003,0,.02]
 values=[]
 for label,pre in [('native',False),('traced',True)]:
  output=a.out/(name+'_'+label+'.tsv');env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',SLAM_TRACE_FILE=str(a.out/(name+'_events.jsonl')))
  env['LD_LIBRARY_PATH']=str(R/'catkin_ws/devel/lib')+':'+env.get('LD_LIBRARY_PATH','')
  env.pop('LD_PRELOAD',None)
  if pre:env['LD_PRELOAD']=str(R/'catkin_ws/devel/lib/libicp_call_trace.so')
  with (a.out/(name+'_'+label+'.log')).open('x') as log:
   ret=subprocess.run([str(B/'code/registration_probe'),str(B/'data/B_core_run01'/(name+'_a.xy')),str(B/'data/B_core_run01'/(name+'_b.xy')),*map(str,guess),str(output)],env=env,stdout=log,stderr=subprocess.STDOUT)
  if ret.returncode:raise RuntimeError((name,label,ret.returncode))
  values.append(next(csv.DictReader(output.open(),delimiter='\t')))
 events=[json.loads(x) for x in (a.out/(name+'_events.jsonl')).read_text().splitlines()]
 expected=['ICP_BEGIN','ICP_SUCCESS' if values[0]['accepted']=='1' else 'ICP_FAILED']
 rows.append(dict(case=name,identical=values[0]==values[1],event_pair_correct=[x['event'] for x in events]==expected,differences={k:[values[0][k],values[1][k]] for k in values[0] if values[0][k]!=values[1][k]}))
passed=all(r['identical'] and r['event_pair_correct'] for r in rows)
(a.out/'result.json').write_text(json.dumps(dict(pass_gate=passed,rows=rows),indent=2));print(json.dumps(dict(pass_gate=passed,rows=rows),indent=2));raise SystemExit(0 if passed else 1)
