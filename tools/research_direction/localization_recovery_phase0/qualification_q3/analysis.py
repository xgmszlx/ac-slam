"""Offline evaluation of sealed initial window and technical coverage, not science."""
import argparse
import bisect
import csv
import json
import math
import sys
from pathlib import Path
from common import OUT,OLD,create,atomic,read,sha
from timestamps import compose,inverse,wrap
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from metrics import interpolate_gt,error


def jsonl(p):
    with Path(p).open() as f:return [json.loads(x) for x in f if x.strip()]


def make_alignment(data):
    window=data['window']; scans=data['scans'];gt=data['gt']
    if not (window['initialization_completed_ros_s']<window['start']<window['end']):
        raise ValueError('Alignment must be after completed initialization')
    if not data['no_task_motion_yet']:raise ValueError('Task motion already started')
    paired=[]
    for s in scans:
        if not window['start']<=s['stamp']<=window['end'] or s.get('map_base') is None:continue
        truth,gap=interpolate_gt(gt,s['stamp'],.15)
        if truth is not None:paired.append((s,truth,gap))
    if len(paired)<15:raise ValueError('Insufficient stationary alignment pairs')
    paired.sort(key=lambda p:p[0]['stamp'])
    transform=compose(paired[0][1],inverse(paired[0][0]['map_base']))
    residual=[error(compose(transform,s['map_base']),g)[0] for s,g,_ in paired]
    if max(residual)>.03:raise ValueError('Static initial window residual exceeds original 0.03m requirement')
    return {'alignment_window_start':window['start'],'alignment_window_end':window['end'],
        'initialization_completed_ros_s':window['initialization_completed_ros_s'],
        'alignment_samples':len(paired),'alignment_residual_max_m':max(residual),
        'alignment_transform':transform,'alignment_rule':'first strictly paired static pose; no future refit',
        'gt_max_bracket_s':.15,'alignment_frozen_before_motion':True,
        'offline_closed_file_only':True,'gt_online_navigation_input':False,
        'initial_scan_identity':{'index':paired[0][0]['index'],'seq':paired[0][0]['seq'],'stamp':paired[0][0]['stamp']}}


def freeze_alignment():
    path=OUT/'raw/alignment_input.json';data=read(path)
    report=make_alignment(data);report['input_sha256']=sha(path)
    create(OUT/'results/gt_alignment_report.json',report)


def final_reports():
    clock_path=OUT/'raw/clock_stream.jsonl'
    if clock_path.exists():
        clocks=jsonl(clock_path)
        if len(clocks)>1:
            wall=clocks[-1]['wall_monotonic_s']-clocks[0]['wall_monotonic_s']
            simulated=clocks[-1]['sim_s']-clocks[0]['sim_s']
            atomic(OUT/'results/clock_pacing_report.json',{'clock_samples':len(clocks),'sim_elapsed_s':simulated,
                'wall_elapsed_s':wall,'sim_wall_ratio':simulated/wall,
                'strictly_monotonic':all(b['sim_s']>a['sim_s'] for a,b in zip(clocks,clocks[1:])),
                'original_gui_world':True,'allowed_ratio':[.25,2.5]})
    if not (OUT/'results/navigation_report.json').exists():return
    nav=read(OUT/'results/navigation_report.json')
    if 'qualification_record_start_ros_s' not in nav:return
    scans=jsonl(OUT/'raw/scan_stream.jsonl');resolved=jsonl(OUT/'raw/scan_tf_evaluation.jsonl');gt=jsonl(OUT/'raw/gt_stream.jsonl')
    mapping={r['index']:r for r in resolved}
    start=nav['qualification_record_start_ros_s'];end=nav['task_end_ros_s']
    native=[s for s in scans if start<=s['stamp']<=end]
    task=[s for s in native if s['stamp']>=nav['task_start_ros_s']]
    evaluated=[];tfvalid=0;gtvalid=0;pairvalid=0;taskvalid=0
    alignment=read(OUT/'results/gt_alignment_report.json') if (OUT/'results/gt_alignment_report.json').exists() else None
    for s in native:
        r=mapping.get(s['index']);truth,gap=interpolate_gt(gt,s['stamp'],.15)
        gtvalid+=truth is not None
        if r is None or r.get('map_base') is None:continue
        tfvalid+=1
        if truth is None or alignment is None:continue
        pairvalid+=1;taskvalid+=s['stamp']>=nav['task_start_ros_s']
        estimate=compose(alignment['alignment_transform'],r['map_base']);xy,yaw=error(estimate,truth)
        evaluated.append({'index':s['index'],'seq':s['seq'],'stamp':s['stamp'],'translation_error_m':xy,
                          'heading_error_rad':yaw,'gt_bracket_s':gap,'tf_bracket_s':r['tf_interpolation_span'],
                          'tf_resolved_wall_latency_s':r['tf_resolved_wall_time']-r['scan_received_wall_time'],
                          'tf_status':r['tf_status'],'technical_only':True})
    report={'qualified_native_scans':len(native),'task_native_scans':len(task),'qualified_tf_resolved':tfvalid,
      'qualified_gt_pairable':gtvalid,'qualified_joint_pairs':pairvalid,'task_joint_pairs':taskvalid,
      'tf_coverage':tfvalid/max(1,len(native)),'gt_coverage':gtvalid/max(1,len(native)),
      'joint_coverage':pairvalid/max(1,len(native)),'task_joint_coverage':taskvalid/max(1,len(task)),
      'required_coverage':.90,'gt_tolerance_s':.15,'tf_max_interpolation_span_s':.15,
      'latest_tf_fallback':False,'scientific_eligible':False,'nonempty_online_pose_error_sequence':bool(evaluated)}
    report['qualified_scan_sequence_missing_count']=sum(max(0,b['seq']-a['seq']-1) for a,b in zip(native,native[1:]))
    report['qualified_scan_max_stamp_gap_s']=max((b['stamp']-a['stamp'] for a,b in zip(native,native[1:])),default=None)
    atomic(OUT/'results/tf_coverage_report.json',report)
    if evaluated:
        with (OUT/'results/technical_pose_error.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(evaluated[0]));writer.writeheader();writer.writerows(evaluated)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['alignment','final']);args=parser.parse_args()
    if args.command=='alignment':freeze_alignment()
    else:final_reports()
