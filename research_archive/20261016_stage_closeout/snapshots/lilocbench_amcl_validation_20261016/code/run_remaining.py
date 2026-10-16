from pathlib import Path
import json,subprocess,sys,shutil,time
p=Path(__file__).resolve().parents[1];protocol=json.loads((p/'protocol/seed_control_amendment03.json').read_text())
for i,spec in enumerate(protocol['runs']):
 key=spec['id'];out=p/'results'/key
 if shutil.disk_usage(p).free<protocol['reserve_bytes']:raise RuntimeError('disk reserve gate')
 with (p/'audit'/(key+'_orchestrator.log')).open('w') as f:c=subprocess.run(['/usr/bin/python3',str(p/'code/run_native_offline_v2.py'),key],stdout=f,stderr=subprocess.STDOUT)
 if c.returncode:raise RuntimeError('run failed; stop, no retry '+key)
 with (out/'evaluation.log').open('w') as f:c=subprocess.run([sys.executable,str(p/'code/evaluate_one.py'),key],stdout=f,stderr=subprocess.STDOUT)
 if c.returncode:raise RuntimeError('technical evaluation failed '+key)
 text=(out/'launch.log').read_text(errors='replace')
 if any(x in text for x in ['extrapolation','Unable to transform min/max',"Couldn't determine robot"]):raise RuntimeError('TF failure '+key)
 seeds=[x.split('AUDIT_GAUSSIAN_SEED ')[1].split()[0] for x in text.splitlines() if 'AUDIT_GAUSSIAN_SEED ' in x]
 assert seeds==['1702'],('unexpected Gaussian seed',key,seeds)
 metric=json.loads((out/'metrics.json').read_text());print(json.dumps({'completed_remaining':i+1,'maximum_remaining':len(protocol['runs']),'id':key,'position_rmse_m':metric['official_position_RMSE_m'],'yaw_rmse_deg':metric['official_yaw_RMSE_deg'],'fallbacks':metric['fallback_events'],'actual_initial_gaussian_seed':1702}),flush=True)
(p/'protocol/matrix_completed.json').write_text(json.dumps({'native_offline_completed':16,'early_failures_preserved':2,'actual_initial_seed_1702_runs':5,'seed_control_limitation':'second labelled static A0 already ran with Gaussian seed1; not repeated again','extra_science_runs':0,'time':time.time()},indent=2))
