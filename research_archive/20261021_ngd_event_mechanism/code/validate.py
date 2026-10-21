from pathlib import Path
import csv,json
D=Path(__file__).resolve().parents[1]
f=list(csv.DictReader((D/'results/paired_frame_evidence.csv').open()));w=list(csv.DictReader((D/'results/common_RPE_windows.csv').open()));s=json.loads((D/'results/summary.json').read_text())
checks={}
checks['two_outputs_all589_inputs']=len(f)==1178 and all(len([x for x in f if x['type']==t])==589 for t in ['online','exported'])
checks['same558_window_endpoints']= [(x['i'],x['j']) for x in w if x['type']=='online']==[(x['i'],x['j']) for x in w if x['type']=='exported'] and len(w)==1116
checks['same_M0_strata_across_outputs']=[x['stratum'] for x in w if x['type']=='online']==[x['stratum'] for x in w if x['type']=='exported']
checks['actual_extra_LK301_ORB216']=sum(int(x['M2_lk_deleted_extra']) for x in f if x['type']=='online')==301 and sum(int(x['M2_orb_deleted_extra']) for x in f if x['type']=='online')==216
checks['three_actual_acceptance_frames']=[int(x['index']) for x in f if x['type']=='online' and int(x['M2_accepted'])>0]==[271,292,299]
checks['pre_intervention_divergence_not_hidden']=s['differences']['tx']['first']==3 and s['pre_first_intervention_max_online_separation_m']>.09
checks['missing_event_masks_explicit']=all(json.loads((D/'events'/str(i)/'evidence.json').read_text())['event_mask_pixels']=='NOT_RECORDED' for i in [271,292,299])
checks['backend_step_uses_actual_saved_poses']=s['M2_largest_adjacent_online_step']['index']==493 and s['M2_largest_adjacent_online_step']['M2_online_step_m']>.8 and s['M2_largest_adjacent_online_step']['GT_step_m']<.004
assert all(checks.values()),checks
(D/'audit/checks.json').write_text(json.dumps({'pass':True,'checks':checks},indent=2));print(json.dumps(checks))
