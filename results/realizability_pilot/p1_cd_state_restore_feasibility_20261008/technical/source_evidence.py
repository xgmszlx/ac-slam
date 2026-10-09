#!/usr/bin/python3
"""Compare ROS release tar source against isolated source and official raw files."""
import difflib
import hashlib
import tarfile
from b0_tools import WS, OUT, sha, write

archive = WS / 'packages/ros-noetic-slam-toolbox_1.5.7.orig.tar.gz'
changes = []
files = {}
with tarfile.open(archive) as tar:
    for entry in tar.getmembers():
        if not entry.isfile(): continue
        relative = '/'.join(entry.name.split('/')[1:])
        original = tar.extractfile(entry).read()
        current = (WS / 'src/slam_toolbox' / relative).read_bytes()
        files[relative] = {'upstream_sha256': hashlib.sha256(original).hexdigest(),
                           'isolated_sha256': hashlib.sha256(current).hexdigest()}
        if original != current:
            changes.extend(difflib.unified_diff(original.decode().splitlines(True),
                                               current.decode().splitlines(True),
                                               fromfile='upstream/' + relative,
                                               tofile='candidate/' + relative))
path = OUT / 'audit/observation.patch'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(''.join(changes))
raw_matches = {}
for local in sorted(WS.glob('*.cpp')) + sorted(WS.glob('*.hpp')) + [WS / 'Mapper.h', WS / 'Karto.h']:
    matches = [p for p in files if p.split('/')[-1] == local.name]
    if len(matches) == 1:
        raw_matches[local.name] = {'official_tag_raw_sha256': sha(local),
                                   'release_source_sha256': files[matches[0]]['upstream_sha256'],
                                   'exact': sha(local) == files[matches[0]]['upstream_sha256']}
write(OUT / 'audit/upstream_source_provenance.json', {
    'tag': '1.5.7', 'commit': '1b18cacfa6971bd9c3f8fdd965d7baeecffbedf0',
    'archive_sha256': sha(archive), 'files': files, 'official_raw_comparison': raw_matches,
    'all_raw_exact': all(x['exact'] for x in raw_matches.values()),
    'patch_sha256': sha(path)})
assert all(x['exact'] for x in raw_matches.values())
print('Source evidence saved; changed files:', [p for p, x in files.items() if x['upstream_sha256'] != x['isolated_sha256']])
