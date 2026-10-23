#!/usr/bin/env python3
"""Real resource locks via flock(2).  [v2, replaces the PID-file version]

Why v1 was wrong: it wrote the PID of a short-lived CLI process into a file. Once
that process exited the lock file stayed behind with a dead PID, so the lock was
prose, not mutex.

v2 semantics:
  * mutual exclusion is the OS file lock (fcntl.flock, LOCK_EX|LOCK_NB) -- atomic,
    and released by the kernel if the holder dies for any reason;
  * the lock is held by whichever process keeps the fd open. `run` holds it for the
    whole lifetime of the child command; `hold` holds it until its own exit;
  * the child is started in its own process group (start_new_session), and timeouts
    signal the whole group, so grandchildren are covered;
  * we never delete someone else's lock file and never kill processes outside the
    process group we created; a "stale" lock is impossible by construction -- if
    nobody holds the flock, acquisition succeeds immediately.

Usage:
  lock.py run   <resource> [--timeout S] [--holder NAME] -- <cmd...>
  lock.py hold  <resource> [--holder NAME] [--seconds S]
  lock.py status [resource]
"""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time

LOCKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locks')
PIDDIR = os.path.join(LOCKDIR, 'holders')
os.makedirs(PIDDIR, exist_ok=True)


def paths(res):
    return (os.path.join(LOCKDIR, res + '.lock'),
            os.path.join(PIDDIR, res + '.json'))


def open_lock(res):
    lp, _ = paths(res)
    fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
    return fd


def try_acquire(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def write_holder(res, holder, extra):
    _, hp = paths(res)
    tmp = hp + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'resource': res, 'pid': os.getpid(), 'pgid': os.getpgid(0),
                   'holder': holder, 'started': time.strftime('%Y-%m-%dT%H:%M:%S'),
                   'workspace': os.getcwd(), **extra}, f, indent=2)
    os.replace(tmp, hp)


def read_holder(res):
    _, hp = paths(res)
    try:
        return json.load(open(hp))
    except Exception:
        return None


def clear_holder(res):
    _, hp = paths(res)
    try:
        os.remove(hp)
    except OSError:
        pass


def cmd_run(a):
    fd = open_lock(a.resource)
    if not try_acquire(fd):
        h = read_holder(a.resource)
        print('DENIED: %s is held%s' % (a.resource, (' by ' + json.dumps(h)) if h else ''),
              file=sys.stderr)
        return 2
    write_holder(a.resource, a.holder, {'mode': 'run', 'cmd': a.cmd})

    # --- parent-death safety -------------------------------------------------
    # The flock lives on the open file description, and an OFD is shared by every
    # process that inherits the fd. By passing the lock fd to the child, the lock
    # stays HELD even if this parent is SIGKILLed: it is only released once the
    # child (and anything else holding the fd) exits. That closes the "lock free
    # but compute still running" hole that a plain parent-held lock leaves open.
    def child_setup():
        os.setpgid(0, 0)

    proc = subprocess.Popen(a.cmd, start_new_session=True, pass_fds=(fd,))

    # --- signal forwarding ---------------------------------------------------
    # SIGTERM/SIGINT to the wrapper must abort the child GROUP, not orphan it.
    state = {'sig': None}

    def _fwd(signum, frame):
        state['sig'] = signum
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass

    old = {s: signal.signal(s, _fwd) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        proc.wait(timeout=a.timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        # signal the WHOLE group so grandchildren die too
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        rc = 124
        print('TIMEOUT: killed process group of %s after %ss' % (a.resource, a.timeout),
              file=sys.stderr)
    finally:
        # escalate if the group ignored SIGTERM
        if state['sig'] is not None:
            try:
                os.killpg(os.getpgid(proc.pid), 0)      # still alive?
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass
            time.sleep(0.2)
        for sig_, h in old.items():
            signal.signal(sig_, h)
        clear_holder(a.resource)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        if state['sig'] is not None:
            print('ABORTED by signal %d; child group terminated' % state['sig'], file=sys.stderr)
            return 128 + state['sig']
    return rc


def cmd_hold(a):
    fd = open_lock(a.resource)
    if not try_acquire(fd):
        print('DENIED: %s is held' % a.resource, file=sys.stderr)
        return 2
    write_holder(a.resource, a.holder, {'mode': 'hold', 'seconds': a.seconds})
    print('HELD %s pid %d' % (a.resource, os.getpid()), flush=True)
    try:
        if a.seconds:
            time.sleep(a.seconds)
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        clear_holder(a.resource)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return 0


def cmd_status(a):
    res = a.resource
    names = [res] if res else sorted(f[:-5] for f in os.listdir(LOCKDIR)
                                     if f.endswith('.lock'))
    out = []
    for n in names:
        lp, _ = paths(n)
        if not os.path.exists(lp):
            out.append({'resource': n, 'state': 'FREE'}); continue
        fd = os.open(lp, os.O_RDWR)
        free = try_acquire(fd)
        if free:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        out.append({'resource': n, 'state': 'FREE' if free else 'HELD',
                    'holder': read_holder(n)})
    for o in out:
        print(json.dumps(o))
    return 0


def main():
    # `run` needs an unambiguous split: everything after the first bare `--` is the
    # child command, so options may appear in any order before it. argparse's
    # REMAINDER would otherwise swallow --timeout into the command.
    argv = sys.argv[1:]
    if argv and argv[0] == 'run' and '--' in argv:
        cut = argv.index('--')
        head, child = argv[:cut], argv[cut + 1:]
        ap2 = argparse.ArgumentParser(prog='lock.py run')
        ap2.add_argument('action'); ap2.add_argument('resource')
        ap2.add_argument('--timeout', type=float); ap2.add_argument('--holder', default='')
        ns = ap2.parse_args(head)
        ns.cmd = child
        if not child:
            ap2.error('run needs a command after --')
        return cmd_run(ns)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='action', required=True)
    r = sub.add_parser('run'); r.add_argument('resource'); r.add_argument('--timeout', type=float)
    r.add_argument('--holder', default=''); r.add_argument('cmd', nargs=argparse.REMAINDER)
    h = sub.add_parser('hold'); h.add_argument('resource'); h.add_argument('--holder', default='')
    h.add_argument('--seconds', type=float)
    s = sub.add_parser('status'); s.add_argument('resource', nargs='?')
    a = ap.parse_args()
    if a.action == 'run':
        if a.cmd and a.cmd[0] == '--':
            a.cmd = a.cmd[1:]
        if not a.cmd:
            ap.error('run needs a command after --')
        return cmd_run(a)
    if a.action == 'hold':
        return cmd_hold(a)
    return cmd_status(a)


if __name__ == '__main__':
    sys.exit(main())
