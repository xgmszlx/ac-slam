"""Existing final occupancy vs Stage-reference bitmap, EVALUATION ONLY.

Never supplies an occupancy map to candidate generation. Boundary metrics are
coverage/wall-thickness dependent and do not isolate active-revisit causality.
"""
import importlib.util
import sys
from common import ROOT,ASSETS,csv_out,sha


def load_evaluator(reader):
    p=ROOT/'tools/evaluate_mapping.py';reader.register(p)
    spec=importlib.util.spec_from_file_location('_alc_archived_map_evaluator',p)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def audit_maps(reader):
    ev=load_evaluator(reader);rows=[]
    for item in reader.csv(ASSETS/'results/phase4c/aggregate/run_table.csv'):
        run=ASSETS/item['run_dir'];record=reader.json(run/'mapping_metrics.json',False)
        if record is None:
            rows.append({'episode_id':item['map']+'_'+item['seed']+'_'+item['condition'],'status':'MISSING_RAW_MAP_METADATA'});continue
        try:
            grids={}
            for kind in ['gt','estimated']:
                metadata=record['grid'][kind]
                for ext in ['image','yaml']:
                    p=__import__('pathlib').Path(metadata[ext]);reader.register(p)
                    if sha(p)!=metadata[ext+'_sha256']:raise ValueError('Map SHA differs from archived evaluation')
                grids[kind]=ev.load_map(metadata['yaml'])
            metrics=ev.evaluate_maps(grids['gt'],grids['estimated'],boundary_tolerance_m=record['protocol']['boundary_tolerance_m'])
            diff=abs(metrics['occupied_boundary_f1']['f1']-float(item['boundary_f1']))
            if diff>1e-6:raise ValueError('Raw map F1 differs from aggregate')
            rows.append({'episode_id':item['map']+'_'+item['seed']+'_'+item['condition'],'map':item['map'],
                'method':item['method'],'validity':item['validity'],'status':'RAW_GRID_RECOMPUTED',
                'boundary_F1':metrics['occupied_boundary_f1']['f1'],'boundary_F1_archived_abs_difference':diff,
                'occupied_IoU':metrics['occupied_iou']['value'],'unknown_ratio':metrics['supporting']['estimated_unknown_ratio'],
                'registration':'saved identity map-frame, no fitted transform','tolerance_m':record['protocol']['boundary_tolerance_m'],
                'GT_permission':'Stage bitmap used for OFFLINE EVALUATION ONLY; not candidate generation',
                'limitations':'final map, no stage-synchronous pre/post grids; missing coverage and solid GT wall thickness affect score'})
        except (OSError,KeyError,ValueError) as exc:
            rows.append({'episode_id':item['map']+'_'+item['seed']+'_'+item['condition'],'map':item['map'],'status':'NOT_EVALUABLE','reason':str(exc)})
    csv_out('analysis/map_quality_audit.csv',rows)
    return rows
