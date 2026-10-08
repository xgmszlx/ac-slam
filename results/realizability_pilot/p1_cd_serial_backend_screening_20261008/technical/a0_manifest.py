#!/usr/bin/python3
"""Generate read-only CD-A0 build/runtime inventories from isolated artifacts."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

SCREEN = Path(__file__).resolve().parents[1]
ROOT = SCREEN.parents[2]
AUDIT = SCREEN / 'audit'
SOURCE = ROOT / 'dependencies/navigation_2d/nav2d_karto'
PURE = SCREEN / 'isolated_catkin'
OBSERVED = SCREEN / 'isolated_catkin_observed'
PRODUCTION = ROOT / 'catkin_ws/devel/lib'
BEFORE = {
    'mapper': '7ab54496b4572e831d7f10d615ad3d700bec3a0b89c5abdb9c562616a67d92f6',
    'libMultiMapper.so': 'a5338a332209d4bda3aa40e53de4f438fbdc6a02dcdd3d9c2331159e93bc19f4',
    'libOpenKarto.so': '4a01ec77c3402845d16e5dd3a0ae1c18e3f3263d578091878b745bb064a6372d',
}
FILES = ['src/MultiMapper.cpp', 'src/SpaSolver.cpp',
         'OpenKarto/source/OpenMapper.cpp',
         'OpenKarto/source/OpenKarto/OpenMapper.h', 'CMakeLists.txt']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(*args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, check=True)
    return result.stdout.strip()


def save(name, payload):
    path = AUDIT / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def binary_set(ws):
    return {name: {'path': str(path), 'sha256': sha(path)} for name, path in {
        'mapper': ws / 'devel/lib/nav2d_karto/mapper',
        'libMultiMapper.so': ws / 'devel/lib/libMultiMapper.so',
        'libOpenKarto.so': ws / 'devel/lib/libOpenKarto.so',
        'libSelfLocalizer.so': ws / 'devel/lib/libSelfLocalizer.so',
    }.items()}


def source_set(ws):
    root = ws / 'src/navigation_2d/nav2d_karto'
    return {name: sha(root / name) for name in FILES}


def main():
    pure, observed = binary_set(PURE), binary_set(OBSERVED)
    smoke = json.loads((SCREEN / 'technical/smoke_observed_final/unified_replay_result.json').read_text())
    runtime = smoke['mapper_runtime']
    mapped = []
    for path_string in runtime['mapped_paths']:
        path = Path(path_string)
        mapped.append({'path': path_string,
                       'sha256': sha(path) if path.is_file() else None})
    env_raw = command('bash', '-lc',
                      'source /opt/ros/noetic/setup.bash && source "{}" && env'.format(
                          OBSERVED / 'devel/setup.bash'))
    env = dict(line.split('=', 1) for line in env_raw.splitlines() if '=' in line)
    binary = observed['mapper']['path']
    save('isolated_build_manifest.json', {
        'task_id': 'CD_A0_A1_SERIAL_KARTO_SCREENING',
        'source_commit': command('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
        'source_sha256': {name: sha(SOURCE / name) for name in FILES},
        'pure_source_sha256': source_set(PURE),
        'observed_source_sha256': source_set(OBSERVED),
        'pure_binaries': pure, 'observed_binaries': observed,
        'pure_change': 'OpenMapper(true) -> OpenMapper(false) only',
        'observed_extra_changes': ['ROS_INFO of IsMultiThreaded',
                                   'graph JSON max_digits10 only',
                                   'ROS_INFO_ONCE after doSPA(40)'],
        'build_command': ('source /opt/ros/noetic/setup.bash && catkin_make -C <isolated_ws> '
                          '--only-pkg-with-deps nav2d_karto -j4 --cmake-args '
                          '-DPYTHON_EXECUTABLE=/usr/bin/python3 -DCMAKE_BUILD_TYPE=Release '
                          '-DCMAKE_CXX_FLAGS=-I/home/wcqw/ac-slam/catkin_ws/devel/include'),
        'build_header_dependency_limitation': 'cpp_solver/PoseGraph.h from production devel/include; header only',
        'compiler': command('/usr/bin/c++', '--version').splitlines()[0],
        'cmake': command('cmake', '--version').splitlines()[0],
        'ros_distro': env.get('ROS_DISTRO'),
        'ros_version': command('rosversion', 'ros'),
        'python_executable': '/usr/bin/python3',
        'PYTHONPATH': env.get('PYTHONPATH'),
        'python_version': command('/usr/bin/python3', '--version'),
        'build_type': 'Release', 'release_flags': '-O3 -DNDEBUG',
        'cxx_flags': '-I/home/wcqw/ac-slam/catkin_ws/devel/include',
        'USE_TBB': True, 'TBB_LIBRARIES': ['tbb', 'atomic'],
        'CMAKE_PREFIX_PATH': env.get('CMAKE_PREFIX_PATH'),
        'ROS_PACKAGE_PATH': env.get('ROS_PACKAGE_PATH'),
    })
    save('runtime_library_provenance.json', {
        'candidate': 'observed', 'mapper_pid_at_smoke': runtime['pid'],
        'mapper_executable': runtime['executable'],
        'mapper_executable_sha256': runtime['executable_sha256'],
        'proc_maps_mapped_files': mapped,
        'LD_LIBRARY_PATH': env.get('LD_LIBRARY_PATH'),
        'readelf_dynamic': command('readelf', '-d', binary),
        'ldd': command('ldd', binary),
        'nm_multimapper_constructor': [line for line in command(
            'nm', '-DC', observed['libMultiMapper.so']['path']).splitlines()
            if 'OpenMapper::OpenMapper(bool)' in line],
        'observed_binding_log': str(SCREEN / 'technical/ld_bindings.103012'),
        'observed_binding_log_sha256': sha(SCREEN / 'technical/ld_bindings.103012'),
    })
    after = {name: sha(PRODUCTION / ('nav2d_karto/' + name if name == 'mapper' else name))
             for name in BEFORE}
    if after != BEFORE:
        raise RuntimeError('PRODUCTION HASH CHANGED; STOP')
    save('production_integrity_before_after.json', {
        'baseline_commit': command('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
        'before_sha256': BEFORE, 'after_sha256': after,
        'all_equal': True,
        'scope_note': 'Three production binary/library files only; not a hash of all ignored raw files',
    })


if __name__ == '__main__':
    main()
