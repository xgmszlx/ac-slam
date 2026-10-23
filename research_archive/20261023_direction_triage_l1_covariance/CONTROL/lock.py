#!/usr/bin/env python3
"""Real resource locks: file + PID + holder + created time. Stale locks are reported, never auto-removed."""
import argparse, json, os, sys, time
LOCKDIR = os.path.dirname(os.path.abspath(__file__)) + '/locks'
def path(n): return os.path.join(LOCKDIR, n + '.lock')
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
def status(n):
    p = path(n)
    if not os.path.exists(p): return {'resource': n, 'state': 'FREE'}
    try: d = json.load(open(p))
    except Exception: return {'resource': n, 'state': 'UNREADABLE'}
    d['state'] = 'HELD_ALIVE' if alive(d.get('pid', -1)) else 'STALE_PID_DEAD'
    return d
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('resource', nargs='?')
    ap.add_argument('--holder', default=''); ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--force-stale', action='store_true')
    a = ap.parse_args()
    if a.action == 'status':
        names = [a.resource] if a.resource else [f[:-5] for f in os.listdir(LOCKDIR) if f.endswith('.lock')]
        for n in names: print(json.dumps(status(n)))
        return 0
    if a.action == 'acquire':
        s = status(a.resource)
        if s['state'] == 'HELD_ALIVE':
            print('DENIED: held by', s, file=sys.stderr); return 2
        if s['state'] == 'STALE_PID_DEAD' and not a.force_stale:
            print('DENIED: stale lock (pid dead) present; verify then re-run with --force-stale', file=sys.stderr); return 3
        json.dump({'resource': a.resource, 'pid': os.getpid(), 'holder': a.holder,
                   'workspace': a.workspace, 'created': time.strftime('%Y-%m-%dT%H:%M:%S')},
                  open(path(a.resource), 'w'), indent=2)
        print('ACQUIRED', a.resource, 'pid', os.getpid()); return 0
    if a.action == 'release':
        s = status(a.resource)
        if s.get('pid') == os.getpid() or a.force_stale:
            os.path.exists(path(a.resource)) and os.remove(path(a.resource))
            print('RELEASED', a.resource); return 0
        print('DENIED: not owner', s, file=sys.stderr); return 2
