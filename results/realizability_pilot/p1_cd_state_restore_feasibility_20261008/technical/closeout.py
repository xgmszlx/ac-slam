#!/usr/bin/python3
"""Failure closeout and hash-only evidence. Never launches ROS or replays data."""
import inspect
import os
import time
import rospy.topics
from b0_tools import OUT, ROOT, read, sha, write

protocol = read(OUT / 'protocol/frozen_technical_experiment.json')
assert sha(OUT / 'protocol/frozen_technical_experiment.json') == read(OUT / 'protocol/frozen_hash.json')['sha256']
for relative, expected in protocol['software_config_sha256'].items():
    assert sha(OUT / relative) == expected
source = inspect.getsource(rospy.topics._PublisherImpl.publish)
module_text = open(inspect.getsourcefile(rospy.topics)).read()
license_header = module_text.split('"""', 1)[0]
(OUT / 'audit/rospy_publisher_source.txt').write_text(license_header + source)
write(OUT / 'audit/publisher_failure.json', {
    'classification': 'ADAPTER_HEADER_SEQUENCE_OFF_BY_ONE',
    'evidence_type': ['real worker traceback', 'installed ROS source audit', 'offline installed-implementation serialization test'],
    'installed_rospy_module': inspect.getsourcefile(rospy.topics),
    'installed_rospy_module_sha256': sha(inspect.getsourcefile(rospy.topics)),
    'sequence_order': 'self.seq += 1 BEFORE serialize_message(self.seq, message)',
    'frozen_adapter_initial_seq': 0, 'frozen_first_input_index': 0,
    'emitted_seq_by_installed_implementation': 1,
    'runtime_wire_capture_preserved': False,
    'runtime_limit': 'worker asserted after first publish; no graph or checkpoint saved',
    'no_runtime_retry': True, 'frozen_code_modified_after_launch': False,
})
for name in ('checkpoint_barrier', 'checkpoint_manifest'):
    write(OUT / ('technical/' + name + '.json'), {
        'status': 'NOT_EXECUTED', 'reason': 'frozen stop rule after continuous adapter assertion',
        'archive_created': False, 'barrier_validated': False})
write(OUT / 'technical/remaining_runs.json', {
    'status': 'NOT_AUTHORIZED_TO_AUTO_RETRY_WITHIN_FROZEN_PROTOCOL',
    'not_executed': ['checkpoint', 'restore_1', 'restore_2', 'restore_3'],
    'no_additional_input_published': True})
for name in ('restore_to_restore', 'restore_to_continuous'):
    write(OUT / ('analysis/' + name + '.json'), {'status': 'NOT_EVALUABLE',
        'exact': None, 'pairs_evaluated': 0, 'reason': 'no saved checkpoint / restored graphs'})
write(OUT / 'technical/ros_environment.json', {
    'keys': {k: os.environ.get(k) for k in ('ROS_DISTRO', 'ROS_VERSION', 'CMAKE_PREFIX_PATH',
                                          'LD_LIBRARY_PATH', 'PYTHONPATH', 'ROS_PACKAGE_PATH', 'PATH')},
    'system_install': False, 'isolated_workspace': '/home/wcqw/ac-slam_cd_b0_ws'})
write(OUT / 'analysis/final_gate.json', {
    'task_id': protocol['task_id'], 'gate': 'TECHNICALLY_INCOMPLETE',
    'reason': 'adapter publication header sequence assertion before full continuous input',
    'backend_independent_startup': 'OBSERVED', 'isolated_source_build': 'COMPLETE',
    'input_adapter_static_audit': 'FEASIBLE_FOR_TECHNICAL_REPLAY',
    'input_adapter_runtime_contract': 'FAILED',
    'checkpoint_cut_validated': False, 'checkpoint_created': False,
    'restore_runs_completed': 0, 'restore_to_restore_exact': None,
    'restore_to_continuous_exact': None,
    'historical_measurement_gate': 'HISTORICAL_MEASUREMENT_NOT_YET_VALIDATED',
    'backend_restore_infeasible': None, 'plan_a_ready': False,
    'scientific_collection_authorized': False,
    'next_action': 'Separate outcome-blind adapter technical amendment; correct rospy initial sequence and test actual serialization before new freeze; retain same input/cut/parameters/run order and do not retry this frozen run.',
    'analysis_boolean_note': 'technical_verdict.json false means completion gate unmet, not a measured failed restore comparison',
    'closed_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
files = sorted(p for p in OUT.rglob('*') if p.is_file() and '__pycache__' not in p.parts
               and p.name != 'raw_artifact_manifest.json')
write(OUT / 'analysis/raw_artifact_manifest.json', {'files': {
    str(p.relative_to(OUT)): {'sha256': sha(p), 'bytes': p.stat().st_size,
                            'local_only': 'ros_home' in p.parts} for p in files},
    'all_logs_retained': True, 'checkpoint_archives': 'not created',
    'isolated_build_libraries': 'preserved locally; exact hashes in build/runtime manifests'})
print('CD-B0 sealed: TECHNICALLY_INCOMPLETE; no backend replay performed by closeout')
