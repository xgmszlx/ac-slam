"""Bounded sequential matrix. Stop on any technical failure; never retry."""
from pathlib import Path
import json,subprocess,time,sys,shutil
p=Path(__file__).resolve().parents[1];protocol=json.loads((p/'protocol/native_offline_amendment02.json').read_text());eval_python=sys.executable
first=protocol['runs'][0]['id'];deadline=time.monotonic()+220
while not (p/'results'/first/'run.json').exists():
 if time.monotonic()>deadline:raise TimeoutError('initial native qualification never completed')
 time.sleep(.5)
for i,spec in enumerate(protocol['runs']):
 key=spec['id'];out=p/'results'/key
 if shutil.disk_usage(p).free<protocol['reserve_bytes']:raise RuntimeError('disk reserve gate')
 if i>0:
  c=subprocess.run(['/usr/bin/python3',str(p/'code/run_native_offline.py'),key],stdout=(p/'audit'/(key+'_orchestrator.log')).open('w'),stderr=subprocess.STDOUT)
  if c.returncode:raise RuntimeError('run failed, no retry: '+key)
 with (out/'evaluation.log').open('w') as f:
  c=subprocess.run([eval_python,str(p/'code/evaluate_one.py'),key],stdout=f,stderr=subprocess.STDOUT)
 if c.returncode:raise RuntimeError('technical evaluation failed, no retry: '+key)
 text=(out/'launch.log').read_text(errors='replace')
 # Actual native failure strings, not harmless repeated-identical-TF warnings.
 bad=[x for x in text.splitlines() if ('extrapolation' in x or 'Unable to transform min/max' in x or "Couldn't determine robot" in x)]
 if bad:raise RuntimeError('native offline TF failure, stop before further matrix: '+key)
 metric=json.loads((out/'metrics.json').read_text())
 print(json.dumps({'completed':i+1,'maximum':len(protocol['runs']),'id':key,'position_rmse_m':metric['official_position_RMSE_m'],'yaw_rmse_deg':metric['official_yaw_RMSE_deg'],'fallbacks':metric['fallback_events']}),flush=True)
(p/'protocol/matrix_completed.json').write_text(json.dumps({'completed':len(protocol['runs']),'extra_retries':0,'time':time.time()},indent=2))
