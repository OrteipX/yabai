"""Historical two-display integration fixture. Called only by session.py --run."""
import subprocess
import time


def run_suite(context):
    HB = context.client
    OUT = context.output
    records = context.records
    baseline = context.baseline
    daemon = context.daemon
    run = context.run
    query = context.query
    save = context.save

    def command(*args):
        result = run([HB, '-m', *map(str, args)])
        records.append({'command': result})
        return result

    def state():
        return {'spaces': query('spaces'), 'displays': query('displays'), 'windows': query('windows')}

    def switch(label, target, selector=None):
        before = state()
        destination = next(s for s in before['spaces'] if s['index'] == target)
        result = command('space', '--focus', selector or target)
        time.sleep(.15)
        after = state()
        focused = [s['index'] for s in after['spaces'] if s['has-focus']]
        displays = [d['index'] for d in after['displays'] if d['has-focus']]
        untouched = all(s['is-visible'] == next(t['is-visible'] for t in after['spaces'] if t['id']==s['id']) for s in before['spaces'] if s['display'] != destination['display'])
        passed = result['rc']==0 and focused==[target] and displays==[destination['display']] and untouched
        records.append({'test': label, 'pass': passed, 'target': target, 'focused': focused, 'focused_displays': displays, 'other_display_unchanged': untouched, 'result': result})
        print(f'{label}: {"PASS" if passed else "FAIL"} rc={result["rc"]} actual={focused} display={displays}', flush=True)
        if not passed: raise RuntimeError(f'switch failed: {label}')

    def own_windows():
        return [w for w in query('windows') if w['pid']==testapp.pid]

    def frame(w):
        return tuple(w['frame'][k] for k in ('x','y','w','h'))

    def check(label, passed, details=None):
        records.append({'test': label, 'pass': bool(passed), 'details': details})
        print(f'{label}: {"PASS" if passed else "FAIL"}', flush=True)
        if not passed: raise RuntimeError(label)

    original_visible = [s for s in baseline['spaces'] if s['is-visible']]
    original_focus = next(s for s in baseline['spaces'] if s['has-focus'])
    testapp = None
    try:
        initial = state()
        focused = next(s for s in initial['spaces'] if s['has-focus'])
        nextspace = next(s for s in initial['spaces'] if s['index']==focused['index']+1)
        switch('next Space from initial display', nextspace['index'], 'next')
        switch('previous Space from initial display', focused['index'], 'prev')
        switch('numeric empty Space (display 1)', 4)
        switch('multi-hop backward (display 1)', 1)
        switch('multi-hop forward to empty Space (display 1)', 12)
        other_visible = next(s for s in initial['spaces'] if s['is-visible'] and s['display']==2)
        switch('already visible Space on other display', other_visible['index'])
        switch('numeric empty Space (display 2)', 13)
        switch('next Space (display 2)', 14, 'next')
        switch('previous Space (display 2)', 13, 'prev')
        switch('multi-hop forward to empty Space (display 2)', 22)
        switch('multi-hop backward (display 2)', 20)
        switch('cross-display return to empty Space', 4)

        check('enable BSP on disposable Space', command('space', 4, '--layout', 'bsp')['rc']==0)
        app_log = open(OUT / 'test-windows.log', 'w')
        testapp = subprocess.Popen([str(context.test_app)], stdout=app_log, stderr=subprocess.STDOUT)
        for _ in range(50):
            windows = own_windows()
            if len(windows)==3: break
            time.sleep(.1)
        check('three disposable windows tracked and tiled', len(windows)==3 and all(w['space']==4 and not w['is-floating'] for w in windows), windows)
        time.sleep(.8)
        windows = own_windows()
        check('BSP frames fill test Space', sum(w['frame']['w'] * w['frame']['h'] for w in windows) > 2000000)
        ids = [w['id'] for w in windows]
        a,b,c = ids
        # Check native client focus and directional focus exactly as used by skhd.
        check('window focus by id', command('window','--focus',a)['rc']==0)
        time.sleep(.1)
        check('focused window confirmed', next(w for w in own_windows() if w['id']==a)['has-focus'])
        windows = own_windows()
        left = min(windows, key=lambda w:w['frame']['x'])
        command('window','--focus',left['id'])
        r = command('window','--focus','east')
        time.sleep(.1)
        check('skhd directional focus east',r['rc']==0 and next(w for w in own_windows() if w['has-focus'])['id']!=left['id'])
        r = command('window','--focus','west')
        check('skhd directional focus west',r['rc']==0)

        before={w['id']:frame(w) for w in own_windows()}
        r=command('window', a, '--swap', b)
        time.sleep(.1)
        after={w['id']:frame(w) for w in own_windows()}
        check('window swap changes placement', r['rc']==0 and after[a]==before[b] and after[b]==before[a])
        before=after
        r=command('window', a, '--warp', c)
        time.sleep(.1)
        after={w['id']:frame(w) for w in own_windows()}
        check('window warp changes BSP',r['rc']==0 and before!=after)
        for flag, value in [('--rotate','270'),('--mirror','y-axis'),('--mirror','x-axis')]:
            before={w['id']:frame(w) for w in own_windows()}
            r=command('space',4,flag,value)
            time.sleep(.1)
            after={w['id']:frame(w) for w in own_windows()}
            if flag == '--mirror':
                coordinate = 0 if value == 'y-axis' else 1
                size = coordinate + 2
                low = min(f[coordinate] for f in before.values())
                high = max(f[coordinate]+f[size] for f in before.values())
                expected = {}
                for wid, f in before.items():
                    target = list(f)
                    target[coordinate] = low+high-f[coordinate]-f[size]
                    expected[wid] = tuple(target)
                geometry_ok = all(all(abs(x-y)<=2 for x,y in zip(after[wid],expected[wid])) for wid in ids)
                check('BSP '+flag+' '+value,r['rc']==0 and geometry_ok, {'before': before, 'after': after, 'expected': expected})
            else:
                check('BSP '+flag+' '+value,r['rc']==0 and before!=after)
        for operation in ['--swap','--warp']:
            succeeded = False
            for direction in ['south','north','east','west']:
                for wid in ids:
                    command('window','--focus',wid)
                    before={w['id']:frame(w) for w in own_windows()}
                    r=command('window',operation,direction)
                    time.sleep(.08)
                    if r['rc']==0 and before!={w['id']:frame(w) for w in own_windows()}:
                        succeeded = True
                        break
                if succeeded: break
            check('skhd directional '+operation,succeeded)
        r=command('space',4,'--balance')
        check('BSP balance',r['rc']==0)
        # Try a resize on an existing BSP boundary; direction depends on current tree.
        resized=False
        for wid in ids:
            for edge in ['right:20:0','left:-20:0','bottom:0:20','top:0:-20']:
                before={w['id']:frame(w) for w in own_windows()}
                r=command('window',wid,'--resize',edge)
                time.sleep(.05)
                if r['rc']==0 and before!={w['id']:frame(w) for w in own_windows()}:
                    resized=True; break
            if resized: break
        check('skhd BSP resize changes frames',resized)
        before_balance={w['id']:frame(w) for w in own_windows()}
        r=command('space',4,'--balance')
        time.sleep(.1)
        check('balance restores altered split ratios',r['rc']==0 and before_balance!={w['id']:frame(w) for w in own_windows()})
        r=command('window',a,'--space',12)
        time.sleep(.15)
        check('window moved to other Space',r['rc']==0 and next(w for w in own_windows() if w['id']==a)['space']==12)
        r=command('window',a,'--space',4)
        time.sleep(.15)
        check('window returned and tiled',r['rc']==0 and next(w for w in own_windows() if w['id']==a)['space']==4 and not next(w for w in own_windows() if w['id']==a)['is-floating'])
        # Switch the other display to an empty destination before cross-display moves.
        switch('prepare empty cross-display destination',20)
        check('enable BSP on second disposable Space',command('space',20,'--layout','bsp')['rc']==0)
        switch('return to source for window display move',4)
        r=command('window',a,'--display','west')
        time.sleep(.15)
        moved=next(w for w in own_windows() if w['id']==a)
        check('skhd move window to display west',r['rc']==0 and moved['display']==2 and moved['space']==20 and not moved['is-floating'])
        r=command('display','--focus','west')
        time.sleep(.15)
        check('skhd follow moved window to display west',r['rc']==0 and [d['index'] for d in query('displays') if d['has-focus']]==[2])
        r=command('window',a,'--display','east')
        time.sleep(.15)
        moved=next(w for w in own_windows() if w['id']==a)
        check('skhd move window to display east',r['rc']==0 and moved['display']==1 and moved['space']==4 and not moved['is-floating'])
        r=command('display','--focus','east')
        time.sleep(.15)
        check('skhd follow moved window to display east',r['rc']==0 and [d['index'] for d in query('displays') if d['has-focus']]==[1])
        command('window','--focus',a)
        r=command('window','--space','next')
        time.sleep(.15)
        check('skhd window --space next',r['rc']==0 and next(w for w in own_windows() if w['id']==a)['space']==5)
        r=command('window','--focus',a)
        time.sleep(.4)
        check('native window focus switches to its Space',r['rc']==0 and [sp['index'] for sp in query('spaces') if sp['has-focus']]==[5])
        r=command('window',a,'--space','prev')
        time.sleep(.15)
        check('skhd window --space prev',r['rc']==0 and next(w for w in own_windows() if w['id']==a)['space']==4)
        switch('return after prev/next window moves',4)
        for label,args in [('invalid Space',['space','--focus','99999']),('invalid window',['window','4294967294','--space','4']),('invalid selector',['space','--focus','bogus-macos27']),('same Space focus',['space','--focus','4'])]:
            r=command(*args)
            check(label+' rejected',r['rc']!=0,r)
        save('suite-final.json',state())
    finally:
        if testapp is not None and testapp.poll() is None:
            testapp.terminate()
            try:
                testapp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                testapp.kill()
                testapp.wait(timeout=5)
        if daemon.poll() is None:
            for original in original_visible:
                now = query('spaces')
                matching=next(s for s in now if s['id']==original['id'])
                if not matching['has-focus']:
                    r=command('space','--focus',original['index'])
                    if r['rc']:
                        candidates=[w for w in baseline['windows'] if w['space']==original['index'] and not w['is-minimized'] and not w['is-sticky']]
                        if candidates: command('window','--focus',candidates[0]['id'])
            orig_window=next((w for w in baseline['windows'] if w['has-focus']),None)
            if orig_window: command('window','--focus',orig_window['id'])
            else: command('space','--focus',original_focus['index'])
            time.sleep(.5)
            save('before-local-stop.json',state())
