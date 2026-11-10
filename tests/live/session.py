#!/usr/bin/env python3
"""Explicit opt-in live replay; never imported by the automated test target."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

from suite import run_suite


class Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]


class Session:
    def __init__(self, output):
        self.root = Path(__file__).resolve().parents[2]
        self.client = '/opt/homebrew/bin/yabai'
        self.binary = self.root / 'bin/yabai'
        self.plist = Path.home() / 'Library/LaunchAgents/com.asmvik.yabai.plist'
        self.service = f'gui/{os.getuid()}/com.asmvik.yabai'
        self.output = output
        self.records = []
        self.daemon = None
        self.test_app = output / 'test-windows'
        self.cg = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.cg.CGEventCreate.argtypes = [ctypes.c_void_p]
        self.cg.CGEventCreate.restype = ctypes.c_void_p
        self.cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
        self.cg.CGEventGetLocation.restype = Point
        self.cg.CGWarpMouseCursorPosition.argtypes = [Point]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]

    @staticmethod
    def run(args, timeout=10):
        p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
        return {'argv': list(map(str, args)), 'rc': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}

    def query(self, kind):
        result = self.run([self.client, '-m', 'query', '--' + kind])
        if result['rc']:
            raise RuntimeError(f'query {kind} failed: {result["stderr"]}')
        return json.loads(result['stdout'])

    def save(self, name, value):
        (self.output / name).write_text(json.dumps(value, indent=2) + '\n')

    def snapshot(self, name):
        event = self.cg.CGEventCreate(None)
        if not event:
            raise RuntimeError('could not read cursor position')
        point = self.cg.CGEventGetLocation(event)
        self.cf.CFRelease(event)
        value = {'cursor': {'x': point.x, 'y': point.y},
                 'displays': self.query('displays'), 'spaces': self.query('spaces'),
                 'windows': self.query('windows'),
                 'service': self.run(['launchctl', 'print', self.service]),
                 'sip': self.run(['csrutil', 'status']),
                 'binary_sha256': hashlib.sha256(Path(self.client).read_bytes()).hexdigest(),
                 'plist_sha256': hashlib.sha256(self.plist.read_bytes()).hexdigest(),
                 'local_binary_sha256': hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                 'source_commit': self.run(['git', '-C', self.root, 'rev-parse', 'HEAD']),
                 'source_status': self.run(['git', '-C', self.root, 'status', '--porcelain'])}
        self.save(name + '.json', value)
        return value

    def preflight(self):
        self.baseline = self.snapshot('before')
        if self.baseline['sip']['stdout'].strip() != 'System Integrity Protection status: enabled.':
            raise RuntimeError('SIP must be enabled for this fixture')
        if self.baseline['source_status']['stdout'].strip():
            raise RuntimeError('commit source changes before replay so HEAD identifies the test build')
        displays = self.baseline['displays']
        spaces = self.baseline['spaces']
        if len(displays) != 2 or sorted(len(d['spaces']) for d in displays) != [10, 12]:
            raise RuntimeError('fixture requires two displays with 12 and 10 Spaces')
        primary = next(d for d in displays if d['index'] == 1)
        secondary = next(d for d in displays if d['index'] == 2)
        if len(primary['spaces']) != 12 or secondary['frame']['x'] >= primary['frame']['x']:
            raise RuntimeError('fixture expects display 2 west of display 1, which has 12 Spaces')
        for index in [4, 12, 13, 14, 20, 22]:
            space = next(s for s in spaces if s['index'] == index)
            if space['windows'] or space['is-native-fullscreen']:
                raise RuntimeError(f'Space {index} must be empty and not fullscreen')
        focused = next(s for s in spaces if s['has-focus'])
        following = next((s for s in spaces if s['index'] == focused['index'] + 1), None)
        if not following or following['display'] != focused['display']:
            raise RuntimeError('start on a Space with a next neighbor on the same display')
        identity = self.baseline['service']['stdout']
        if self.client not in identity or 'state = running' not in identity:
            raise RuntimeError('expected Homebrew launchd service is not running')
        self.original_pid = int(re.search(r'\bpid = (\d+)', identity).group(1))
        if self.run(['pgrep', '-x', 'yabai'])['stdout'].split() != [str(self.original_pid)]:
            raise RuntimeError('expected exactly one yabai process before handoff')

    def execute(self):
        self.preflight()
        build = self.run(['xcrun', 'clang', Path(__file__).with_name('windows.m'),
                          '-framework', 'Cocoa', '-o', self.test_app], timeout=60)
        if build['rc']:
            raise RuntimeError(build['stderr'])
        config = self.output / 'yabairc'
        config.write_text('#!/bin/sh\n' + '\n'.join(
            f'{self.client} -m config {key} {value}' for key, value in [
                ('layout', 'float'), ('top_padding', 3), ('bottom_padding', 3),
                ('left_padding', 3), ('right_padding', 3), ('window_gap', 3)]) + '\n')
        config.chmod(0o700)
        stopped = False
        try:
            stopped = True  # bootout may complete even if its client times out
            result = self.run(['launchctl', 'bootout', self.service])
            self.records.append({'stop_homebrew': result})
            if result['rc']:
                raise RuntimeError('could not boot out Homebrew service')
            for _ in range(50):
                if self.run(['ps', '-p', str(self.original_pid), '-o', 'pid='])['rc']:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('original daemon still exists; refusing to start replacement')
            with (self.output / 'daemon.log').open('w') as log:
                self.daemon = subprocess.Popen([str(self.binary), '--verbose', '--config', str(config)],
                                               stdout=log, stderr=subprocess.STDOUT)
                for _ in range(50):
                    if self.daemon.poll() is not None:
                        raise RuntimeError('local daemon exited; inspect daemon.log (possibly Accessibility)')
                    if self.run([self.client, '-m', 'query', '--displays'])['rc'] == 0:
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('local daemon did not become ready')
                if self.run(['pgrep', '-x', 'yabai'])['stdout'].split() != [str(self.daemon.pid)]:
                    raise RuntimeError('replacement is not the only yabai process')
                self.records.append({'local_pid': self.daemon.pid,
                                     'identity': self.run(['ps', '-p', str(self.daemon.pid), '-o', 'args='])})
                time.sleep(1)
                run_suite(self)
        finally:
            # Do not let a second interrupt prevent rollback once it has started.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            if self.daemon is not None and self.daemon.poll() is None:
                self.daemon.terminate()
                try:
                    self.daemon.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.daemon.kill()  # Only the owned child, never an unrelated PID.
                    self.daemon.wait(timeout=5)
            if stopped:
                restored = self.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', self.plist])
                self.records.append({'restore_homebrew': restored})
                for _ in range(80):
                    if self.run([self.client, '-m', 'query', '--displays'])['rc'] == 0:
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('ROLLBACK FAILED: bootstrap the original plist manually')
                time.sleep(2)
                self.cg.CGWarpMouseCursorPosition(Point(**self.baseline['cursor']))
                after = self.snapshot('after')
                old = {w['id']: w for w in self.baseline['windows']}
                new = {w['id']: w for w in after['windows']}
                keys = ['frame', 'space', 'display', 'is-floating', 'is-minimized']
                match = re.search(r'\bpid = (\d+)', after['service']['stdout'])
                checks = {'original_service_running': bool(match) and self.client in after['service']['stdout'],
                          'one_original_daemon': bool(match) and self.run(['pgrep', '-x', 'yabai'])['stdout'].split() == [match.group(1)],
                          'sip_enabled': after['sip']['stdout'].strip() == 'System Integrity Protection status: enabled.',
                          'cursor_restored': all(abs(after['cursor'][k] - self.baseline['cursor'][k]) < 1 for k in ['x', 'y']),
                          'binary_unchanged': after['binary_sha256'] == self.baseline['binary_sha256'],
                          'plist_unchanged': after['plist_sha256'] == self.baseline['plist_sha256'],
                          'window_ids_restored': old.keys() == new.keys(),
                          'window_state_restored': all(all(w[k] == new[wid][k] for k in keys)
                                                       for wid, w in old.items() if wid in new),
                          'visible_spaces_restored': [s['id'] for s in after['spaces'] if s['is-visible']] ==
                              [s['id'] for s in self.baseline['spaces'] if s['is-visible']],
                          'focus_restored': [s['id'] for s in after['spaces'] if s['has-focus']] ==
                              [s['id'] for s in self.baseline['spaces'] if s['has-focus']]}
                self.records.append({'restoration_checks': checks})
                print('Homebrew restored; restoration checks:', checks, flush=True)
                self.save('session-results.json', self.records)
                if not all(checks.values()):
                    raise RuntimeError('restoration difference: inspect before/after snapshots')
            self.save('session-results.json', self.records)


def interrupted(signum, frame):
    raise RuntimeError(f'interrupted by signal {signum}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='perform the authorized disruptive live replay')
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        print('No service changes performed. Read tests/live/README.md before opting in.')
        return 0
    output = Path(tempfile.mkdtemp(prefix='yabai-live-'))
    print('Private local evidence:', output, flush=True)
    session = Session(output)
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        session.execute()
    except Exception as exc:
        session.records.append({'error': str(exc)})
        session.save('session-results.json', session.records)
        print(str(exc), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
