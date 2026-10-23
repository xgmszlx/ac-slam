#!/usr/bin/env python3
"""Unit tests for the flock-based resource lock. Every test is a real multi-process test."""
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, 'lock.py')
PY = sys.executable
FAILS = []


def check(name, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + ((' | ' + detail) if detail else ''))
    if not cond:
        FAILS.append(name)


def status(res):
    out = subprocess.run([PY, LOCK, 'status', res], capture_output=True, text=True).stdout.strip()
    return json.loads(out) if out else {'state': 'FREE'}


def cleanup(*resources):
    for r in resources:
        for d in ('locks', 'locks/holders'):
            for ext in ('.lock', '.json'):
                p = os.path.join(HERE, d, r + ext)
                if os.path.exists(p):
                    os.remove(p)


def t_concurrent():
    print('[T1] two concurrent tasks on the same lock -> second must be DENIED')
    r = 'T_CONCURRENT'
    cleanup(r)
    h = subprocess.Popen([PY, LOCK, 'hold', r, '--seconds', '6'], stdout=subprocess.PIPE, text=True)
    h.stdout.readline()
    time.sleep(0.4)
    rc = subprocess.run([PY, LOCK, 'run', r, '--', PY, '-c', 'print(1)'],
                        capture_output=True, text=True)
    check('second acquisition denied', rc.returncode == 2, 'rc=%d err=%s' % (rc.returncode, rc.stderr.strip()[:60]))
    check('status reports HELD', status(r)['state'] == 'HELD')
    h.terminate(); h.wait(timeout=5)
    time.sleep(0.3)
    check('after holder exits the lock is FREE', status(r)['state'] == 'FREE')
    cleanup(r)


def t_normal():
    print('[T2] normal run acquires, executes, releases')
    r = 'T_NORMAL'
    cleanup(r)
    rc = subprocess.run([PY, LOCK, 'run', r, '--', PY, '-c', 'print("ran")'],
                        capture_output=True, text=True)
    check('run returns child rc 0', rc.returncode == 0, repr(rc.stdout.strip()))
    check('lock released after run', status(r)['state'] == 'FREE')
    cleanup(r)


def t_kill9():
    print('[T3] holder killed with SIGKILL -> kernel releases the flock')
    r = 'T_KILL9'
    cleanup(r)
    h = subprocess.Popen([PY, LOCK, 'hold', r, '--seconds', '60'], stdout=subprocess.PIPE, text=True)
    h.stdout.readline(); time.sleep(0.4)
    check('held before kill', status(r)['state'] == 'HELD')
    os.kill(h.pid, signal.SIGKILL); h.wait(timeout=5); time.sleep(0.3)
    check('lock auto-released after SIGKILL', status(r)['state'] == 'FREE')
    rc = subprocess.run([PY, LOCK, 'run', r, '--', PY, '-c', 'print(1)'], capture_output=True, text=True)
    check('reacquire succeeds after SIGKILL', rc.returncode == 0)
    cleanup(r)


def t_grandchild_timeout():
    print('[T4] timeout kills the whole process group (grandchild included)')
    r = 'T_GRAND'
    cleanup(r)
    marker = '/tmp/locktest_grandchild_%d' % os.getpid()
    token = 'GRANDCHILD_SENTINEL_%d' % os.getpid()   # unique: never matches other runs
    if os.path.exists(marker):
        os.remove(marker)
    code = ('import subprocess,sys,time;'
            'subprocess.Popen([sys.executable,"-c",'
            '"import time;time.sleep(120)  # %s"]);'
            'open(%r,"w").write("up");time.sleep(120)' % (token, marker))
    t0 = time.time()
    rc = subprocess.run([PY, LOCK, 'run', r, '--timeout', '1.5', '--', PY, '-c', code],
                        capture_output=True, text=True)
    el = time.time() - t0
    check('timeout path returns 124', rc.returncode == 124, 'rc=%d' % rc.returncode)
    check('timed out promptly', el < 15, '%.1fs' % el)
    check('grandchild started (so the test is not vacuous)', os.path.exists(marker))
    time.sleep(0.6)
    leftover = subprocess.run(['pgrep', '-f', token], capture_output=True, text=True).stdout
    check('no surviving grandchild process', leftover.strip() == '', 'leftover=%r' % leftover.strip()[:60])
    if os.path.exists(marker):
        os.remove(marker)
    check('lock released after timeout', status(r)['state'] == 'FREE')
    cleanup(r)


def t_different_resources():
    print('[T5] different resources may be held simultaneously')
    ra, rb = 'T_RES_A', 'T_RES_B'
    cleanup(ra, rb)
    ha = subprocess.Popen([PY, LOCK, 'hold', ra, '--seconds', '4'], stdout=subprocess.PIPE, text=True)
    ha.stdout.readline(); time.sleep(0.3)
    rc = subprocess.run([PY, LOCK, 'run', rb, '--', PY, '-c', 'print(1)'], capture_output=True, text=True)
    check('other resource not blocked', rc.returncode == 0)
    check('A still held', status(ra)['state'] == 'HELD')
    ha.terminate(); ha.wait(timeout=5); time.sleep(0.3)
    cleanup(ra, rb)


def t_owner_protected():
    print('[T6] a non-owner must not be able to clear the lock')
    r = 'T_OWNER'
    cleanup(r)
    h = subprocess.Popen([PY, LOCK, 'hold', r, '--seconds', '5'], stdout=subprocess.PIPE, text=True)
    h.stdout.readline(); time.sleep(0.3)
    # v2 has no 'release' verb at all: releasing is only possible by exiting, so a
    # third party cannot free a lock it does not hold. Verify the lock file is not
    # removable through the CLI surface.
    rc = subprocess.run([PY, LOCK, 'release', r], capture_output=True, text=True)
    check('no release verb that a bystander could use', rc.returncode != 0)
    check('lock still held', status(r)['state'] == 'HELD')
    h.terminate(); h.wait(timeout=5); time.sleep(0.3)
    cleanup(r)


# ---------------------------------------------------------------------------
# v3 additions: the two runtime holes the review named.
# ---------------------------------------------------------------------------
def t_sigterm_aborts_group():
    print('[T7] SIGTERM to the wrapper aborts the child GROUP, not just the wrapper')
    r = 'T_SIGTERM'
    cleanup(r)
    marker = '/tmp/locktest_t7_%d' % os.getpid()
    code = ('import sys,time;open(%r,"w").write("up");time.sleep(120)' % marker)
    w = subprocess.Popen([PY, LOCK, 'run', r, '--', PY, '-c', code],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(50):
        if os.path.exists(marker):
            break
        time.sleep(0.1)
    check('child started', os.path.exists(marker))
    w.send_signal(signal.SIGTERM)
    out, err = w.communicate(timeout=20)
    check('wrapper reports 128+SIGTERM', w.returncode == 128 + signal.SIGTERM,
       'rc=%d err=%s' % (w.returncode, (err or '').strip()[:60]))
    time.sleep(0.6)
    # unique per-run pattern: a generic one would match leftovers from earlier runs
    leftover = subprocess.run(['pgrep', '-f', marker], capture_output=True, text=True).stdout
    check('no surviving child after SIGTERM', leftover.strip() == '', repr(leftover.strip()[:40]))
    check('lock released', status(r)['state'] == 'FREE')
    if os.path.exists(marker):
        os.remove(marker)
    cleanup(r)


def t_parent_sigkill_keeps_lock():
    print('[T8] parent SIGKILL: lock must STAY held while the child still computes')
    r = 'T_PARENT_KILL'
    cleanup(r)
    marker = '/tmp/locktest_t8_%d' % os.getpid()
    code = ('import os,time;open(%r,"w").write("up");time.sleep(6)' % marker)
    w = subprocess.Popen([PY, LOCK, 'run', r, '--', PY, '-c', code],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(60):
        if os.path.exists(marker):
            break
        time.sleep(0.1)
    check('child started', os.path.exists(marker))
    check('lock held before parent kill', status(r)['state'] == 'HELD')
    os.kill(w.pid, signal.SIGKILL)          # wrapper dies without any cleanup
    w.wait(timeout=5)
    time.sleep(0.5)
    st = status(r)
    check('lock STILL HELD after parent SIGKILL (child inherits the fd)',
       st['state'] == 'HELD', json.dumps(st)[:80])
    rc = subprocess.run([PY, LOCK, 'run', r, '--', PY, '-c', 'print(1)'],
                        capture_output=True, text=True)
    check('a new task is still DENIED while the child runs', rc.returncode == 2)
    time.sleep(7)                            # let the orphan child finish on its own
    check('lock released once the child exits', status(r)['state'] == 'FREE')
    if os.path.exists(marker):
        os.remove(marker)
    cleanup(r)


if __name__ == '__main__':
    for t in (t_concurrent, t_normal, t_kill9, t_grandchild_timeout,
              t_different_resources, t_owner_protected,
              t_sigterm_aborts_group, t_parent_sigkill_keeps_lock):
        t()
    print()
    if FAILS:
        print('FAILED:', FAILS); sys.exit(1)
    print('ALL LOCK TESTS PASSED')
