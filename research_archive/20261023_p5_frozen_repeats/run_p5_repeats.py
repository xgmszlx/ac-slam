#!/usr/bin/env python3
"""P5 frozen repeats: desk B0 x2 more and desk B1 x2 more (each condition reaches 3).

Reuses the FROZEN environment byte-for-byte (verified before by 16/16 hash matches),
writes into NEW directories, keeps its own ledger so the original
protocol/attempts.jsonl is never touched, and never overwrites a result.

Order is the one fixed in the archive's NEXT_MINIMAL_ACTION: B1_02 -> B0_02 -> B0_03 -> B1_03.
"""
import json, os, hashlib, time, subprocess, csv, collections, sys
from pathlib import Path

P = Path('/home/wcqw/passive_rgbd_depth_screen_20261019')
S = Path('/home/wcqw/passive_visual_slam_qualification_20261015/sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4')
HERE = Path('/home/wcqw/slam_multi_direction_research/p5_repeats')
LEDGER = HERE / 'ledger.jsonl'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

ORDER = [('desk', 'B1', 2), ('desk', 'B0', 2), ('desk', 'B0', 3), ('desk', 'B1', 3)]

def frozen_identity():
    return {
        'binary_sha256': sha(P/'build/rgbd_screen'),
        'core_sha256': sha(P/'build/libORB_SLAM3.so'),
        'yaml_sha256': sha(P/'config'/'desk.yaml'),
        'association_sha256': sha(P/'data'/'rgbd_dataset_freiburg1_desk'/'associations.txt'),
    }

def main():
    ident = frozen_identity()
    # verify against a historical record before running anything
    hist = json.load(open(P/'results'/'desk'/'B0'/'run.json'))
    mism = [k for k, v in ident.items() if hist.get(k) != v]
    if mism:
        print('IDENTITY MISMATCH', mism, file=sys.stderr); return 2
    print('identity verified against historical run.json:', list(ident), flush=True)

    for seq, cond, rep in ORDER:
        out = P/'results'/seq/f'{cond}_r{rep}'
        if out.exists():
            print(f'SKIP {out} (already exists; results are never overwritten)', flush=True)
            continue
        if __import__('shutil').disk_usage(P).free < 5*1024**3:
            print('DISK GUARD', file=sys.stderr); return 3
        d = P/'data'/'rgbd_dataset_freiburg1_desk'
        out.mkdir(parents=True, exist_ok=False)
        cmd = [str(P/'build'/'rgbd_screen'), str(S/'Vocabulary'/'ORBvoc.txt'),
               str(P/'config'/f'{seq}.yaml'), str(d), str(d/'associations.txt'),
               cond, str(out)]
        env = dict(os.environ,
                   LD_LIBRARY_PATH=str(P/'build') + ':/home/wcqw/passive_visual_slam_qualification_20261015/local/lib:' +
                   os.environ.get('LD_LIBRARY_PATH', ''))
        rec = {'sequence': seq, 'condition': cond, 'repeat': rep, 'command': cmd,
               **ident, 'GT_online': False,
               'frames_expected': len((d/'associations.txt').read_text().splitlines()),
               'start_unix': time.time(), 'protocol': 'NEXT_MINIMAL_ACTION B1_02/B0_02/B0_03/B1_03'}
        (out/'run.json').write_text(json.dumps(rec, indent=2))
        with LEDGER.open('a') as f:
            f.write(json.dumps({'event': 'START', 'seq': seq, 'cond': cond, 'rep': rep, 'unix': time.time()}) + '\n')
        t0 = time.monotonic()
        with (out/'stdout.log').open('w') as log:
            try:
                r = subprocess.run(['/usr/bin/time', '-v', '-o', str(out/'resources.txt')] + cmd,
                                   env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=900)
                rec['exit'] = r.returncode
            except subprocess.TimeoutExpired:
                rec['exit'] = 'TIMEOUT'
        rec['elapsed_wall_s'] = time.monotonic() - t0
        if (out/'frame_states.csv').exists():
            z = list(csv.DictReader((out/'frame_states.csv').open()))
            rec['processed_frames'] = len(z)
            rec['states'] = dict(collections.Counter(x['state'] for x in z))
            rec['map_ids'] = sorted({int(float(x['map_id'])) for x in z})
        rec['artifacts'] = sorted(os.path.basename(f) for f in out.iterdir())
        (out/'run.json').write_text(json.dumps(rec, indent=2))
        with LEDGER.open('a') as f:
            f.write(json.dumps({'event': 'END', 'seq': seq, 'cond': cond, 'rep': rep,
                                'exit': rec['exit'], 'elapsed_s': rec['elapsed_wall_s']}) + '\n')
        print(json.dumps({k: rec.get(k) for k in ('condition','repeat','exit','processed_frames','map_ids','elapsed_wall_s')}), flush=True)
        if rec['exit'] != 0:
            print('TECHNICAL FAILURE RETAINED. Stopping; no rerun.', file=sys.stderr)
            return 4
    return 0

if __name__ == '__main__':
    sys.exit(main())
