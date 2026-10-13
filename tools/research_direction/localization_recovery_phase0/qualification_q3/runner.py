#!/usr/bin/python3
"""Single Q3 technical attempt. No scientific suite, retries or old-file writes."""
import argparse
import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from common import ROOT,ASSETS,OLD,OUT,HERE,EPISODE,PORT,WORLD,sha,read,create,atomic,environment,launch_text,protect_manifest,check_protection,reserve,port_free,OwnedProcesses
from timestamps import wall_wait
from analysis import final_reports,jsonl


def static_audit():
    text=launch_text();tree=ET.fromstring(text)
    stage=next(n for n in tree.findall('node') if n.attrib['name']=='Stage')
    if stage.attrib['args']!=str(WORLD) or '-g ' in text or '-u ' in text:raise RuntimeError('Wrong Stage CLI')
    for name in ('map3.world','p3at.inc','hokuyo.inc','floorplan.inc','map3.png'):
        if not (WORLD.parent/name).is_file():raise RuntimeError('Missing Stage resource '+name)
    for node in tree.findall('node'):
        if node.attrib.get('ns') or node.attrib['name']=='path_planner':raise RuntimeError('Unexpected namespace/planner')
    for param in tree.findall('.//rosparam'):
        if not Path(param.attrib['file']).is_file():raise RuntimeError('Missing launch parameter file')
    env=environment()
    display=subprocess.run(['xdpyinfo'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)
    if display.returncode:raise RuntimeError('Graphical display unavailable; no headless fallback authorized')
    return {'stage_world':str(WORLD),'world_sha256':sha(WORLD),'stage_flags':[],
            'gui_display_available':True,'stage_nested_resources_exist':True,'robot_namespace_absent':True,
            'mapper_rebuilt':False,'stage_started':False,'ros_master_started':False}


def freeze():
    if (OUT/'protocol/Q3_qualification_preregistration.json').exists():raise RuntimeError('Already frozen')
    check=static_audit()
    tests=read(OUT/'audit/offline_tests_postreview.json')
    if tests['new_q3_tests']['returncode'] or tests['old_doc81_tests']['returncode']:raise RuntimeError('Offline tests failed: no physical authorization')
    create(OUT/'protocol/protected_pre.json',protect_manifest())
    create(OUT/'audit/static_preflight.json',check)
    (OUT/'protocol/native_Q3.launch').write_text(launch_text())
    sources={str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.glob('*.py'))}
    create(OUT/'protocol/Q3_qualification_preregistration.json',{
      'task_id':'DOC81_Q3_RUNTIME_AND_TIMESTAMP_QUALIFICATION','type':'TECHNICAL_QUALIFICATION_ONLY',
      'reference_commit':'c0f5d0d475ce015283522b191e81a268c38438c0','episode_id':EPISODE,
      'maximum_new_physical_attempts':1,'no_auto_retry':True,'no_scientific_collection':True,
      'stage_world':str(WORLD),'stage_mode':'original GUI; no -g/-u; exact existing map3.world',
      'physical_start':[-28.,-28.,0.],'sensor_odometry_karto_nav_parameters':'original files, no changes',
      'task_goal':'2m forward relative to post-initialization estimated map-base heading',
      'goal_position_tolerance_m':.25,'goal_heading_tolerance_rad':.1,
      'gt_usage':'read-only serialization; closed static-window offline subprocess alignment and offline task evaluation; never navigation input',
      'tf_chain':['map','offset','odom','base_footprint','base_link'],'tf_max_interpolation_span_s':.15,
      'tf_cache_sim_s':20.,'tf_per_edge_max_samples':4096,'pending_queue_capacity':200,'pending_queue_wall_timeout_s':2.,
      'gt_max_interpolation_gap_s':.15,'required_tf_gt_coverage':.90,'task_minimum_joint_pairs':20,
      'alignment_after_start_mapping':True,'alignment_fixed_window_sim_s':2.,'alignment_minimum_samples':15,
      'alignment_max_residual_m':.03,'alignment_frozen_before_goal':True,'no_post_task_refit':True,
      'gui_pacing_allowed_sim_wall_ratio':[.25,2.5],'clock_validation_min_wall_s':2.,
      'action_connection_wall_timeout_s':30.,'mapping_wall_timeout_s':120.,'navigation_wall_timeout_s':120.,
      'episode_hard_wall_timeout_s':300.,'gt_offline_min_task_displacement_m':1.,
      'all_twelve_gate_conditions_required':True,'old_scientific_hypotheses':'UNRESOLVED',
      'old_three_attempt_ledger_sha256':sha(OLD/'protocol/budget_ledger.json'),
      'budget_policy':'immutable old 3-attempt ledger plus exclusive Q3 reservation; cumulative4/15 and baseline4/9 if started',
      'scientific_matrix_after_start':'ORIGINAL_SCIENTIFIC_MATRIX_NOT_EXECUTABLE_UNDER_REMAINING_BASELINE_BUDGET',
      'source_sha256':sources,'protected_pre_sha256':sha(OUT/'protocol/protected_pre.json')})
    paths=[OUT/'protocol/Q3_qualification_preregistration.json',OUT/'protocol/protected_pre.json',
           OUT/'protocol/native_Q3.launch',OUT/'audit/offline_tests_postreview.json',OUT/'audit/static_preflight.json']
    create(OUT/'protocol/Q3_qualification_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in paths})
    create(OUT/'results/qualification_status.json',{'verdict':'QUALIFICATION_NOT_EXECUTED','old_scientific_hypotheses':'OLD_SCIENTIFIC_HYPOTHESES_UNRESOLVED','new_physical_attempts':0})


def check_frozen():
    for name,digest in read(OUT/'protocol/Q3_qualification_hashes.json').items():
        if sha(OUT/name)!=digest:raise RuntimeError('Frozen Q3 artifact changed: '+name)
    for name,digest in read(OUT/'protocol/Q3_qualification_preregistration.json')['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Frozen Q3 source changed: '+name)
    check_protection()


def diagnostics(env,owned):
    reports={}
    for key,args in [('nodes',['rosnode','list']),('topics',['rostopic','list']),
                     ('navigator',['rosnode','info','/Navigator']),('services',['rosservice','list']),
                     ('mapper_params',['rosparam','get','/Mapper'])]:
        try:
            p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=5)
            reports[key]={'returncode':p.returncode,'output':p.stdout}
        except subprocess.TimeoutExpired:reports[key]={'timeout_wall_s':5}
    atomic(OUT/'results/ros_diagnostics.json',reports)
    processes=[];loaded={}
    for process in owned.live():
        try:
            row={'pid':process.pid,'name':process.name(),'cmdline':process.cmdline(),'status':process.status()}
            processes.append(row)
            if 'nav2d_karto/mapper' in ' '.join(row['cmdline']):
                loaded[str(process.pid)]={'executable':process.exe(),'executable_sha256':sha(process.exe()),
                                         'maps':Path('/proc/%d/maps'%process.pid).read_text()}
        except Exception as exc:
            processes.append({'pid':process.pid,'observation_error':str(exc)})
    atomic(OUT/'results/process_states_before_cleanup.json',{'processes':processes})
    atomic(OUT/'raw/loaded_mapper_libraries.json',loaded)


def reconcile():
    started=(OUT/'protocol/physical_attempt.json').exists();total=3+int(started)
    report={'old_ledger_sha256':sha(OLD/'protocol/budget_ledger.json'),'old_attempts_immutable':3,
            'new_q3_physical_attempts':int(started),'q3_counts_as_scientific_control':False,
            'cumulative_total_attempts':total,'cumulative_baseline_attempts':total,'intervention_attempts':0,
            'remaining_total':15-total,'remaining_baseline':9-total,'remaining_intervention':6,
            'original_healthy_plus_corridor_required':6,
            'original_scientific_matrix':'ORIGINAL_SCIENTIFIC_MATRIX_NOT_EXECUTABLE_UNDER_REMAINING_BASELINE_BUDGET' if started else 'SEALED_REQUIRES_NEW_PROTOCOL',
            'new_scientific_protocol_authorized':False}
    atomic(OUT/'results/budget_reconciliation.json',report)


def conclude(reason=None):
    nav=read(OUT/'results/navigation_report.json') if (OUT/'results/navigation_report.json').exists() else {}
    ready=read(OUT/'results/readiness_report.json') if (OUT/'results/readiness_report.json').exists() else {}
    coverage=read(OUT/'results/tf_coverage_report.json') if (OUT/'results/tf_coverage_report.json').exists() else {}
    align=read(OUT/'results/gt_alignment_report.json') if (OUT/'results/gt_alignment_report.json').exists() else {}
    cleanup=read(OUT/'results/process_cleanup_report.json') if (OUT/'results/process_cleanup_report.json').exists() else {}
    close=read(OUT/'results/raw_close_report.json') if (OUT/'results/raw_close_report.json').exists() else {}
    clock=read(OUT/'results/clock_pacing_report.json') if (OUT/'results/clock_pacing_report.json').exists() else {}
    events=ready.get('events',[]);stages={e['stage'] for e in events}
    frozen_event=next((e for e in events if e['stage']=='ALIGNMENT_FROZEN_BEFORE_TASK'),None)
    conditions={
       'A_stage_resource_load':'NATIVE_CLOCK_SCAN_GT_ODOM_READY' in stages,
       'B_clock_monotonic_paced':'clock_pacing' in ready and clock.get('strictly_monotonic',False) and .25<=clock.get('sim_wall_ratio',0)<=2.5,
       'C_native_scan_gt_odom':'NATIVE_CLOCK_SCAN_GT_ODOM_READY' in stages,
       'D_actual_map_base_chain':'REAL_MAP_BASE_CHAIN_READY' in stages,
       'E_exact_time_tf_coverage':coverage.get('tf_coverage',0)>=.9 and coverage.get('task_joint_coverage',0)>=.9,
       'F_strict_gt_pairing':coverage.get('gt_coverage',0)>=.9 and coverage.get('joint_coverage',0)>=.9,
       'G_post_mapping_static_alignment':align.get('alignment_samples',0)>=15,
       'H_alignment_frozen_before_task':bool(frozen_event and frozen_event['wall_monotonic_s']<nav.get('task_goal_wall_monotonic_s',0)
                  and align.get('alignment_window_end',float('inf'))<nav.get('task_start_ros_s',0)),
       'I_move_to_connected':ready.get('move_to_connected',False),
       'J_frozen_navigation_completed':nav.get('completed',False) and nav.get('action_state')==3,
       'K_valid_nonempty_error_sequence':coverage.get('nonempty_online_pose_error_sequence',False) and coverage.get('task_joint_pairs',0)>=20,
       'L_complete_process_and_data_cleanup':cleanup.get('all_closed',False) and close.get('all_files_closed',False) and close.get('worker_joined',False)}
    if (OUT/'raw/gt_stream.jsonl').exists() and 'task_start_ros_s' in nav and 'task_end_ros_s' in nav:
        gt=[r for r in jsonl(OUT/'raw/gt_stream.jsonl') if nav['task_start_ros_s']<=r['stamp']<=nav['task_end_ros_s']]
        if gt:
            import math
            distance=math.hypot(gt[-1]['x']-gt[0]['x'],gt[-1]['y']-gt[0]['y'])
            nav['offline_gt_task_net_displacement_m']=distance;atomic(OUT/'results/navigation_report.json',nav)
            conditions['J_frozen_navigation_completed'] &= distance>=1.
    started=(OUT/'protocol/physical_attempt.json').exists()
    verdict='QUALIFICATION_PASS' if started and all(conditions.values()) and reason is None else ('QUALIFICATION_FAIL' if started else 'QUALIFICATION_NOT_EXECUTED')
    atomic(OUT/'results/qualification_status.json',{'verdict':verdict,'conditions':conditions,'failure_reason':reason,
            'old_scientific_hypotheses':'OLD_SCIENTIFIC_HYPOTHESES_UNRESOLVED','new_physical_attempts':int(started),
            'scientific_episode_count':0,'no_automatic_next_stage':True})
    reconcile()
    return verdict


def run():
    check_frozen();static_audit()
    if not port_free():raise RuntimeError('Task master port occupied; no takeover')
    # All checks precede reservation; reservation precedes every ROS/Stage start.
    reserve()
    env=environment();owned=OwnedProcesses();begin=time.monotonic();reason=None;launch=None;driver=None
    (OUT/'raw').mkdir(exist_ok=True);(OUT/'runtime').mkdir(exist_ok=True)
    try:
        master=owned.start(['roscore','-p',str(PORT)],env,OUT/'raw/roscore.log')
        def master_ready():
            try:return subprocess.run(['rosparam','list'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1).returncode==0
            except subprocess.TimeoutExpired:return False
        wall_wait(master_ready,30.,alive=lambda:master.poll() is None)
        launch=owned.start(['roslaunch',str(OUT/'protocol/native_Q3.launch')],env,OUT/'raw/roslaunch.log')
        def service_ready():
            try:return subprocess.run(['rosservice','type','/StartMapping'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1).returncode==0
            except subprocess.TimeoutExpired:return False
        wall_wait(service_ready,30.,alive=lambda:launch.poll() is None)
        def core_nodes_ready():
            try:
                p=subprocess.run(['rosnode','list'],env=env,capture_output=True,text=True,timeout=1)
                return p.returncode==0 and {'/Mapper','/Operator','/Navigator','/Stage'}.issubset(set(p.stdout.splitlines()))
            except subprocess.TimeoutExpired:return False
        wall_wait(core_nodes_ready,30.,alive=lambda:launch.poll() is None)
        create(OUT/'results/initial_core_nodes_ready.json',{'required_nodes_exist':True,'wall_monotonic_s':time.monotonic()})
        driver=owned.start(['/usr/bin/python3',str(HERE/'driver.py')],env,OUT/'raw/driver.log')
        with (OUT/'raw/process_monitor.csv').open('x') as monitor:
            monitor.write('wall_elapsed_s,launch_alive,driver_alive\n')
            while driver.poll() is None:
                elapsed=time.monotonic()-begin
                monitor.write('%.6f,%s,%s\n'%(elapsed,launch.poll() is None,driver.poll() is None));monitor.flush()
                if launch.poll() is not None:raise RuntimeError('Core roslaunch exited')
                if elapsed>300.:raise TimeoutError('Frozen 300s episode wall limit')
                time.sleep(.1)
        if driver.returncode:raise RuntimeError('Qualification driver exited '+str(driver.returncode))
    except BaseException as exc:reason=str(exc)
    finally:
        try:diagnostics(env,owned)
        except Exception as exc:atomic(OUT/'results/diagnostic_error.json',{'error':str(exc)})
        cleanup=owned.close();cleanup['whole_attempt_wall_s']=time.monotonic()-begin
        atomic(OUT/'results/process_cleanup_report.json',cleanup)
        protection=check_protection();atomic(OUT/'audit/protected_post.json',protection)
        try:final_reports()
        except Exception as exc:
            reason=reason or 'Offline coverage/evaluation failed: '+str(exc)
            atomic(OUT/'results/evaluation_failure.json',{'error':str(exc)})
        verdict=conclude(reason)
        atomic(OUT/'protocol/physical_attempt.json',{**read(OUT/'protocol/physical_attempt.json'),'status':verdict,'reason':reason})
        files=[p for p in (OUT/'raw').rglob('*') if p.is_file()]
        create(OUT/'audit/local_only_capture_manifest.json',{'files':[{'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]})
        print(verdict,flush=True)
    return verdict


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['freeze','run','report']);args=parser.parse_args()
    if args.command=='freeze':freeze()
    elif args.command=='run':run()
    else:final_reports();print(conclude())
