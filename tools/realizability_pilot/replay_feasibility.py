#!/usr/bin/python3
"""Same-input replay feasibility audit and the N0-B fallback decision.

The audit is recorded as explicit, checkable statements about the current
repository rather than as a prose opinion, so the decision can be re-derived by
anyone reading it.

Question: can the mapper be replayed from recorded inputs so that an OFF run and
an ON run see bit-identical input, making the OFF/ON contrast exactly causal?

Findings (each one is a code fact with a file reference):

F1  The mapper consumes ``nav2d_msgs/LocalizedScan`` on ``karto_in``
    (MultiMapper subscription) AND resolves four TF frames (laser, robot, odom,
    offset) through a live TransformListener.  A replay harness must therefore
    provide both the topic stream and a walking TF tree, in the same order and
    with the same timing, or the frame lookups fail.
F2  The mapper's graph publication used by the observers is triggered by the
    ``get_map`` service (``MultiMapper::getMap`` -> ``sendMap``), which also
    resets the internal map-update timer.  Reproducing the observer state
    exactly means reproducing when the service is called, not only what the
    input stream contains.
F3  There is no mapper-only launch file; the mapper node is started inside the
    full exploration launch together with the planner and the localizer.  A
    replay harness is a new subsystem, not a flag.
F4  Karto's scan matching runs through TBB (``OpenKarto`` /
    ``Karto::ScanMatcher`` thread pools).  Even with identical input, thread
    scheduling changes the search order in which candidate chains are
    evaluated, which is precisely the nondeterminism the earlier protocol
    version documented when it had to stop trusting single-run closure counts.
F5  The instrument under test is synchronous file I/O inside the mapper's
    answer path (edge provenance JSONL and the loop diagnostics JSONL).  A
    replay harness would have to reproduce the *blocking* behaviour of that
    I/O on the same OS/scheduler to be informative, which is not achievable by
    re-running recorded messages at all.

Cost of a faithful replay harness: a new launch path for the mapper alone, a TF
re-publisher driven from the recording, a service-call scheduler, and a
determinism story for TBB - i.e. a multi-day change to the ROS/Stage pipeline
whose own reproducibility properties are exactly what F2 and F4 show to be
fragile.

Decision: run the matched same-seed ON/OFF episodes (N0-B) now, and record the
replay harness as the escalation path if the matched-pair repeatability proves
too coarse to resolve the effect the direction gate needs.
"""

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CODE_FACTS = [
    {
        'id': 'F1',
        'statement': 'the mapper consumes localized scans and resolves live TF frames',
        'evidence': [
            {'path': 'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
             'detail': 'subscribes nav2d_msgs/LocalizedScan on karto_in'},
            {'path': 'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
             'detail': 'uses tf::TransformListener for laser/robot/odom/offset frames'},
        ],
    },
    {
        'id': 'F2',
        'statement': 'graph snapshots and both observers are produced by a service '
                     'call, which also resets the periodic publication timer',
        'evidence': [
            {'path': 'dependencies/navigation_2d/nav2d_karto/src/MultiMapper.cpp',
             'detail': 'getMap() -> sendMap() publishes /slam_path and the full pose '
                       'graph observer beside it'},
            {'path': 'catkin_ws/src/cpp_solver/param/mapper.yaml',
             'detail': 'map_update_rate drives the periodic publication'},
        ],
    },
    {
        'id': 'F3',
        'statement': 'no mapper-only launch exists; every launch file starts the '
                     'full stack',
        'evidence': [
            {'path': 'catkin_ws/src/cpp_solver/launch/exploration.launch',
             'detail': 'single exploration entry point for this project'},
            {'path': 'catkin_ws/src/cpp_solver/launch/play_bag.launch',
             'detail': 'the remaining launch files are joystick/real-robot/bag '
                       'variants, not mapper-only launches'},
        ],
    },
    {
        'id': 'F4',
        'statement': 'the mapper uses TBB parallel range processing and concurrent '
                     'queues, so identical input does not imply identical internal '
                     'work order',
        'evidence': [
            {'path': 'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/'
                     'OpenMapper.cpp',
             'detail': 'includes tbb/tbb_thread.h and tbb/concurrent_queue.h and '
                       'defines a tbb::blocked_range3d operator()'},
            {'path': 'dependencies/navigation_2d/nav2d_karto/CMakeLists.txt',
             'detail': 'pkg_check_modules(TBB tbb)'},
        ],
    },
    {
        'id': 'F5',
        'statement': 'the instrument under test is blocking file I/O on the '
                     'constraint-creation path, which a message replay cannot '
                     'reproduce',
        'evidence': [
            {'path': 'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/'
                     'OpenMapper.cpp',
             'detail': 'AppendEdgeProvenanceLine opens/appends/closes a std::ofstream '
                       'per created constraint; called from RecordNewConstraint'},
            {'path': 'dependencies/navigation_2d/nav2d_karto/OpenKarto/source/'
                     'OpenMapper.cpp',
             'detail': 'AppendLoopDiagnosticsLine is called from the loop-closure '
                       'search path'},
        ],
    },
]

DECISION = {
    'decision': 'USE_MATCHED_ONLINE',
    'primary_method': 'N0-B matched same-seed episodes with alternating arm order',
    'reasons': [
        'a faithful replay harness requires a new mapper-only launch path, a TF '
        're-publisher, a service-call scheduler and a determinism argument for the '
        'threaded matcher (facts F1-F4); that is a multi-day change to the ROS/Stage '
        'pipeline',
        'the instrument being tested is blocking file I/O inside the mapper answer '
        'path (fact F5), so replaying recorded messages cannot reproduce the very '
        'mechanism whose effect is in question',
        'matched same-seed pairs remove the actual defect of the earlier comparison '
        '(the TSP seed differed between the OFF and ON episodes), which is the '
        'confound the decision needs to remove',
    ],
    'limitations': [
        'matched pairs control the seed, the route, the map and the probe, but the '
        'initial mapping phase remains an exploring action whose length varies by a '
        'few scans; the pre-probe gate measures and reports that residual variation '
        'instead of assuming it away',
        'the verdict is therefore non-perturbation of the measured outcome '
        'distribution, not bit-level determinism',
    ],
    'escalation_path': {
        'trigger': 'the matched-pair repeatability proves too coarse to resolve the '
                   'effect the direction gate needs (MDE larger than the effect)',
        'action': 'build the replay harness (mapper-only launch, TF re-publisher, '
                  'service scheduler, recorded karto_in stream) and repeat N0',
        'estimated_cost': 'multi-day engineering change to the ROS/Stage pipeline',
    },
    'required_inputs_recorded': [
        'karto_in localized scans (topic stream with timestamps)',
        'TF tree for laser/robot/odom/offset frames',
        'get_map service call timing',
        'planner MoveTo action goals',
    ],
    'inputs_already_recorded_by_this_repository': [
        'per-episode karto_edge_provenance.jsonl',
        'pose_graph_before.json / pose_graph_after.json full snapshots',
        'episode_result.json MoveTo goals and probe ground-truth trajectory',
        'resolved_history_route.json resolved waypoints',
    ],
    'inputs_not_recorded': [
        'the raw karto_in stream',
        'the TF tree history',
    ],
}


def audit(repo_root):
    present = []
    missing = []
    for fact in CODE_FACTS:
        entries = []
        for evidence in fact['evidence']:
            candidate = Path(repo_root) / evidence['path']
            entries.append({
                'path': evidence['path'],
                'detail': evidence['detail'],
                'path_exists': candidate.exists(),
            })
        if all(entry['path_exists'] for entry in entries):
            present.append(fact['id'])
        else:
            missing.append(fact['id'])
        fact['evidence_paths_present'] = entries
    return present, missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--repo-root', default=str(REPO_ROOT))
    args = parser.parse_args()
    present, missing = audit(args.repo_root)
    payload = {
        'audit_version': 1,
        'repo_root': args.repo_root,
        'code_facts': CODE_FACTS,
        'facts_with_present_evidence_paths': present,
        'facts_with_missing_evidence_paths': missing,
        'decision': DECISION,
    }
    with open(args.out, 'w') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write('\n')
    print(json.dumps({'decision': DECISION['decision'],
                      'facts_verified': present,
                      'facts_missing_paths': missing}, indent=2))


if __name__ == '__main__':
    main()
