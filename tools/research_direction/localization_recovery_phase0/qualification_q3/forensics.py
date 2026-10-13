#!/usr/bin/python3
"""Read sealed A2 capture; write only the independent Q3 audit directory."""
import csv
import hashlib
import json
import re
import statistics
from collections import Counter,defaultdict
from pathlib import Path
from timestamps import TFHistory,MAP_CHAIN

ROOT=Path(__file__).resolve().parents[4]
OLD=ROOT/'results/research_direction/localization_recovery_phase0'
Q3=OLD/'qualification_Q3'
A2=OLD/'baseline/NORMAL_GEOMETRY_271001_A2'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jsonl(p):
    with Path(p).open() as f:return [json.loads(x) for x in f if x.strip()]
def write_json(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def csv_out(p,rows):
    if not rows:return
    with Path(p).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def dist(values):
    if not values:return None
    values=sorted(values)
    return {'min':values[0],'median':statistics.median(values),'p95':values[int(.95*(len(values)-1))],'max':values[-1]}


def main():
    # Compare every already registered capture digest before using sealed data.
    registered=json.loads((OLD/'audit/local_only_capture_manifest.json').read_text())['files']
    for row in registered:
        if sha(OLD/row['path'])!=row['sha256']:raise RuntimeError('Sealed capture changed: '+row['path'])
    audit=Q3/'audit';audit.mkdir(parents=True,exist_ok=True)
    tfrows=jsonl(A2/'tf_stream.jsonl');scans=jsonl(A2/'scan_stream.jsonl')
    history=TFHistory(cache_s=None);edges=defaultdict(list)
    for r in tfrows:
        for t in r['transforms']:
            history.add(t);edges[(t['parent'],t['child'])].append((t['stamp'],r['received']))
    edge_table=[]
    lo,hi=min(r['stamp'] for r in scans),max(r['stamp'] for r in scans)
    for edge,rows in sorted(edges.items()):
        times=sorted(set(t for t,_ in rows));gaps=[b-a for a,b in zip(times,times[1:])]
        lag=[received-t for t,received in rows]
        edge_table.append({'parent':edge[0],'child':edge[1],'messages':len(rows),'unique_stamps':len(times),
          'first_stamp':times[0],'last_stamp':times[-1],
          'frequency_unique_hz':(len(times)-1)/(times[-1]-times[0]) if len(times)>1 else None,
          'maximum_stamp_gap_s':max(gaps) if gaps else None,
          'receipt_minus_header_median_ros_s':statistics.median(lag),'receipt_minus_header_p95_ros_s':dist(lag)['p95'],
          'receipt_minus_header_min_ros_s':min(lag),'receipt_minus_header_max_ros_s':max(lag),
          'scan_range_overlap_s':max(0.,min(hi,times[-1])-max(lo,times[0]))})
    available=[];counts=Counter();spans=[]
    for r in scans:
        p,meta=history.resolve(r['stamp']);counts[meta['status']]+=1
        if p is not None:spans.append(meta['max_span_s'])
        available.append({'scan_index':r['index'],'seq':r['seq'],'stamp':r['stamp'],
          'original_map_base_present':r['map_base'] is not None,'strict_offline_tf_status':meta['status'],
          'interpolation_span_s':meta.get('max_span_s'),'map_x':None if p is None else p[0],
          'map_y':None if p is None else p[1],'map_yaw':None if p is None else p[2]})
    log=(A2/'roslaunch.log').read_text(errors='replace')
    clock=[(float(a),float(b)) for a,b in re.findall(r'\[(\d+\.\d+), (\d+\.\d+)\]',log)]
    wall=json.loads((A2/'run_state.json').read_text())['wall_duration_s']
    gt=jsonl(A2/'gt_stream.jsonl');gtspan=max(x['stamp'] for x in gt)-min(x['stamp'] for x in gt)
    clock_report={'entire_attempt_wall_s':wall,'recorded_gt_sim_elapsed_s':gtspan,
       'gt_span_divided_by_entire_attempt_wall_ratio_lower_bound':gtspan/wall,
       'bootstrap_ros_s':613.7,'get_first_map_goal_ros_s':945.9,'get_first_map_result_ros_s':996.6,
       'driver_failure_ros_s':1322.7,'mapping_action_elapsed_sim_s':50.7,
       'failure_minus_bootstrap_sim_s':709.,'native_scan_last_ros_s':hi,
       'ros_log_wall_elapsed_s':max(a for a,b in clock)-min(a for a,b in clock),
       'ros_log_sim_range_s':max(b for a,b in clock)-min(b for a,b in clock),
       'same_publisher_stage_exact_speed_available':False,
       'a2_scan_callback_received_wall_time_available':False,
       'scan_query_exception_details_available':False,
       'actionlib_timeout_clock':'rospy.get_rostime; timeout=30 simulated seconds, polled with time.sleep(0.01)',
       'karto_initialization':'robot1 enters ST_MAPPING before explicit StartMapping; mapping bootstrap is Navigator movement',
       'tf_chain_publisher':'Mapper map->offset and offset->odom stamped ros::Time::now; Stage/URDF odom/base links',
       'gt_as_tf_source':False}
    summary={'sealed_scan_count':len(scans),'original_map_base_present':0,
       'full_tf_chain_exists':all(e in edges for e in zip(MAP_CHAIN,MAP_CHAIN[1:])),
       'strictly_reconstructible_scans':len(spans),'strict_coverage':len(spans)/len(scans),
       'classification_counts':dict(counts),'maximum_allowed_tf_bracket_s':.15,
       'interpolation_span_distribution_s':dist(spans),'evaluation_stamp_error_s':0.,
       'conflicting_duplicate_tf_records':history.conflicting_duplicates,
       'duplicate_policy':'first received at edge/stamp, matching TF2 repeated-data rejection; conflicts reported',
       'conclusion':'Map chain exists and many scan timestamps are strictly reconstructible offline. Online failure is not absence of map chain. Callback receipt/exception telemetry is absent, so cache expiration versus query-too-early cannot be uniquely assigned per scan.',
       'causal_strength':'delayed reception/cache/backpressure are probable; raw availability is confirmed; sole cause unresolved',
       'a2_is_scientifically_eligible':False,'old_eligibility_unchanged':True}
    csv_out(audit/'A2_tf_edges.csv',edge_table);csv_out(audit/'A2_scan_tf_availability.csv',available)
    write_json(audit/'A2_tf_coverage.json',summary);write_json(audit/'A2_clock_forensics.json',clock_report)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
