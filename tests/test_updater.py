# Updater: GitHub / custom-URL check, staged download, apply (changed files only, dropped files removed, unlisted
# listfile.csv kept), git-checkout refusal, unsafe / non-zip downloads, draw functions, unregister.
# The release zip is built with tools/make_release.py into WBS_TEST_TMP. Needs `git` on PATH (make_release uses it).
import os
import sys
import json
import runpy
import shutil
import zipfile
import pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('updater')


def build_release_zip(out_dir):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    argv = sys.argv
    sys.argv = ['make_release.py', out_dir]
    try:
        runpy.run_path(os.path.join(here, 'tools', 'make_release.py'), run_name='__main__')
    finally:
        sys.argv = argv
    zips = [f for f in os.listdir(out_dir) if f.endswith('.zip')]
    return os.path.join(out_dir, zips[0]) if zips else None


class _Prefs:
    update_auto_check = True
    update_interval_days = 1
    update_custom_url = ''


class _Layout:
    def __getattr__(self, n):
        return lambda *a, **k: _Layout()

    def __setattr__(self, n, v):
        pass


def body(T):
    common.enable_addon()
    U = common.module('ui.updater')
    AP = common.module('updater_apply')
    ADDON = common.ADDON
    TMP = common.TMP

    T.check(hasattr(bpy.ops.wbs, 'update_check') and hasattr(bpy.ops.wbs, 'update_install'), 'update operators registered')
    real_prefs = U._prefs
    U._prefs = lambda: _Prefs
    real_stage = AP.staging_root
    work = os.path.join(TMP, 'updater')
    shutil.rmtree(work, ignore_errors=True)
    STAGE = os.path.join(work, 'stage')
    os.makedirs(STAGE)
    AP.staging_root = lambda: STAGE
    try:
        CUR = U.current_version()
        NEWV = '%d.%d.%d' % (CUR[0], CUR[1], CUR[2] + 1)
        T.check(len(CUR) == 3 and CUR >= (1, 1, 1), 'current_version from __init__.py on disk = %s' % (CUR,))
        T.check(U.parse_version('v1.10.2') > (1, 9, 9) and U.parse_version('1.1.0') == (1, 1, 0), 'version compare')

        ZIP = build_release_zip(os.path.join(work, 'release'))
        T.check(ZIP and os.path.isfile(ZIP), 'tools/make_release.py built %s' % (os.path.basename(ZIP) if ZIP else None))
        if not ZIP:
            return

        # GitHub (network): tolerant - offline is information, not a failure
        U._check_worker('')
        T.info('github check: %s %s latest=%s' % (U.STATE['status'], U.STATE['error'], U.STATE['latest']))
        T.check(U.STATE['status'] in ('error', 'uptodate', 'available'), 'GitHub check completes (%s)' % U.STATE['status'])

        # custom JSON URL -> a newer version
        js = os.path.join(work, 'latest.json')
        with open(js, 'w') as f:
            json.dump({'version': NEWV, 'url': pathlib.Path(ZIP).as_uri(), 'notes': 'test notes\nline 2'}, f)
        U._check_worker(pathlib.Path(js).as_uri())
        T.check(U.STATE['status'] == 'available' and U.STATE['latest'] == NEWV,
                'custom URL check -> available (%s %s)' % (U.STATE['status'], U.STATE['error']))

        # download + stage
        U._download_worker(U.STATE['url'], U.STATE['latest'])
        T.check(U.STATE['status'] == 'restart' and os.path.isfile(os.path.join(STAGE, 'READY'))
                and os.path.isfile(os.path.join(STAGE, 'staged', ADDON, 'wbs_manifest.txt')),
                'download staged (%s %s)' % (U.STATE['status'], U.STATE['error']))
        U._save_state()
        T.check(os.path.isfile(os.path.join(STAGE, 'state.json')), 'state saved')

        # apply onto a fake install: changed files written, dropped file removed, unlisted file kept
        INST = os.path.join(work, 'inst')
        zipfile.ZipFile(ZIP).extractall(INST)
        INST = os.path.join(INST, ADDON)
        with open(os.path.join(INST, 'wbs_manifest.txt'), 'a') as f:
            f.write('deadbeef  old_removed.py\n')
        with open(os.path.join(INST, 'old_removed.py'), 'w') as f:
            f.write('x')
        with open(os.path.join(INST, 'ui', 'updater.py'), 'a') as f:
            f.write('\n# local change\n')
        os.remove(os.path.join(INST, 'auto_load.py'))
        os.makedirs(os.path.join(INST, 'pywowlib', 'archives'), exist_ok=True)
        with open(os.path.join(INST, 'pywowlib', 'archives', 'listfile.csv'), 'w') as f:
            f.write('keep me')
        r = AP.apply_pending(INST)
        T.info('apply: %s' % r)
        T.check(r and '2 files written, 1 removed' in r, 'apply wrote 2 / removed 1')
        with open(os.path.join(INST, 'pywowlib', 'archives', 'listfile.csv')) as f:
            T.check(f.read() == 'keep me', 'unlisted listfile.csv kept')
        T.check(not os.path.exists(os.path.join(INST, 'old_removed.py'))
                and os.path.isfile(os.path.join(INST, 'auto_load.py')), 'dropped file deleted, missing file restored')
        T.check(not os.path.exists(os.path.join(STAGE, 'READY')) and not os.path.exists(os.path.join(STAGE, 'staged')),
                'staging cleared')
        T.check(AP.apply_pending(INST) is None, 'second start: nothing pending')

        # git checkout is never overwritten
        U._download_worker(pathlib.Path(ZIP).as_uri(), '1.1.1')
        G = os.path.join(work, 'git')
        os.makedirs(os.path.join(G, '.git'))
        r = AP.apply_pending(G)
        T.check(r and 'git checkout' in r and os.path.isfile(os.path.join(STAGE, 'READY')), 'git checkout not overwritten')
        shutil.rmtree(os.path.join(STAGE, 'staged'))
        os.remove(os.path.join(STAGE, 'READY'))

        # unsafe zip
        EV = os.path.join(work, 'evil.zip')
        with zipfile.ZipFile(EV, 'w') as z:
            z.writestr('../evil.txt', 'x')
            z.writestr(ADDON + '/__init__.py', '')
        U._download_worker(pathlib.Path(EV).as_uri(), '9.9.9')
        T.check(U.STATE['status'] == 'error' and 'unsafe' in U.STATE['error']
                and not os.path.exists(os.path.join(work, 'evil.txt')) and not os.path.exists(os.path.join(STAGE, 'READY')),
                'unsafe zip rejected')

        # not a zip
        U._download_worker(pathlib.Path(js).as_uri(), '9.9.9')
        T.check(U.STATE['status'] == 'error', 'non-zip rejected (%s)' % U.STATE['error'][:60])

        # draw helpers survive every state
        for st in ('idle', 'checking', 'uptodate', 'available', 'downloading', 'restart', 'error'):
            U.STATE['status'] = st
            U.draw_prefs(_Prefs, _Layout())
            U.draw_notice(_Layout())
        T.check(True, 'draw_prefs/draw_notice survive every state')
    finally:
        U._prefs = real_prefs
        AP.staging_root = real_stage
        U.STATE['status'] = 'idle'

    # unregister cleanly (the add-on's own unregister path), then register again
    import addon_utils
    addon_utils.disable(ADDON, default_set=True)
    T.check(not hasattr(bpy.types, 'WBS_OT_update_check'), 'unregister clean (update operators gone)')
    addon_utils.enable(ADDON, default_set=True, persistent=False)
    T.check(hasattr(bpy.types, 'WBS_OT_update_check'), 're-enable registers the update operators again')


common.run(T, body)
