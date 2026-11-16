# Send to test client: safety rules + write/readback/listfile/compaction on a FAKE client built from copies of
# small real archives. Never touches a real client.
import os, sys, shutil, ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('deploy')

SRC_DATA = os.path.join(common.CLIENT, 'Data')


def make_client(root, names):
    data = os.path.join(root, 'Data')
    os.makedirs(data, exist_ok=True)
    for n in names:
        shutil.copy2(os.path.join(SRC_DATA, n), os.path.join(data, n))
    return root


def lock_exclusive(path):
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                              ctypes.c_uint32, ctypes.c_void_p]
    h = k.CreateFileW(path, 0x80000000, 0, None, 3, 0, None)       # GENERIC_READ, share = 0
    return k, h


def body(T):
    from importlib import import_module as _im
    cd = _im(common.ADDON + '.utils.client_deploy')
    panel = _im(common.ADDON + '.ui.deploy_panel')
    cd.reset_session_backups()

    root = make_client(os.path.join(common.TMP, 'fakeclient'),
                       ['dbc.MPQ', 'patch-X.mpq', 'patch-H.mpq', 'patch-W.mpq'])
    data = os.path.join(root, 'Data')
    bak = os.path.join(common.TMP, 'wbs_mpq_backups')
    # the add-on game data always loads AnimationData.dbc; stock 1.12 keeps it only in the 108 MB patch-Y, so put
    # that one file into the (copied) patch-H - this also exercises the writer
    from importlib import import_module
    MPQ = import_module(common.ADDON + '.pywowlib.archives.mpq').MPQFile
    ry = MPQ(os.path.join(SRC_DATA, 'patch-Y.mpq'), 0x100)
    adb = os.path.join(common.TMP, 'AnimationData.dbc')
    with open(adb, 'wb') as f:
        f.write(ry.read('DBFilesClient\\AnimationData.dbc'))
    ry.close()
    with cd.Archive(os.path.join(data, 'patch-H.mpq'), write=True) as a:
        a.add(adb, 'DBFilesClient/AnimationData.dbc')
    common.setup_project(client=root)
    from importlib import import_module
    misc = import_module(common.ADDON + '.utils.misc')
    X = os.path.join(data, 'patch-X.mpq')
    W = os.path.join(data, 'patch-W.mpq')
    H = os.path.join(data, 'patch-H.mpq')
    size0 = {p: os.path.getsize(p) for p in (X, W, H)}
    T.check(os.path.isfile(cd.find_dll()), 'StormLib.dll bundled in the add-on: ' + cd.find_dll())
    T.check([os.path.basename(p).lower() for p in cd.mount_order(root)][-3:] == ['patch-h.mpq', 'patch-w.mpq', 'patch-x.mpq'],
            'mount order ascending: ' + ', '.join(os.path.basename(p) for p in cd.mount_order(root)))

    def read_back(name):
        gd = misc.load_game_data()
        data_, _ = gd.read_file(name, no_exc=True) or (None, None)
        return data_

    def mk(name, payload):
        p = os.path.join(common.TMP, name)
        with open(p, 'wb') as f:
            f.write(payload)
        return p

    # ---- 1. new path -> default target = highest-priority writable patch archive (patch-X)
    payload = os.urandom(6000)
    src = mk('new.bin', payload)
    rep = cd.deploy(root, [(src, 'Everwood/WBSTest/new.bin')], protected=(), backup_dir=bak,
                    release_game_data=panel.release_game_data)
    T.check(rep.ok and os.path.basename(rep.target).lower() == 'patch-x.mpq',
            'new path goes to the highest-priority patch archive: ' + os.path.basename(rep.target))
    got = read_back('Everwood\\WBSTest\\new.bin')
    T.check(got == payload, 'read back through the add-on game data is byte-identical (%s bytes)' % (len(got) if got else None))
    with cd.Archive(X) as a:
        lf = (a.read('(listfile)') or b'').decode('latin-1').lower()
    T.check('everwood\\wbstest\\new.bin' in lf, '(listfile) of patch-X contains the new path')
    nb = [f for f in os.listdir(bak) if f.startswith('patch-X')] if os.path.isdir(bak) else []
    T.check(len(nb) == 1 and os.path.getsize(os.path.join(bak, nb[0])) == size0[X], 'backup of patch-X made, original size')
    T.check(not os.path.normcase(bak).startswith(os.path.normcase(root)), 'backup folder is outside the client')

    # ---- 2. existing path -> the archive that currently wins (patch-W), not the default
    from importlib import import_module as im
    MPQFile = im(common.ADDON + '.pywowlib.archives.mpq').MPQFile
    mw = MPQFile(W, 0x100)
    order = cd.mount_order(root)
    victim = None
    for n in mw.namelist():
        if n.startswith('(') or n.lower().endswith('.dbc'):
            continue
        if cd.winner_of(order, n.replace('/', '\\')) == W:
            victim = n.replace('/', '\\')
            break
    mw.close()
    T.check(victim is not None, 'found a file that patch-W wins: %s' % victim)
    p2 = os.urandom(777)
    rep = cd.deploy(root, [(mk('victim.bin', p2), victim)], protected=(), backup_dir=bak,
                    release_game_data=panel.release_game_data)
    T.check(os.path.normcase(rep.target) == os.path.normcase(W), 'existing path updates the winning archive (patch-W)')
    T.check(read_back(victim) == p2, 'overwritten file reads back with the new bytes')
    T.check(len([f for f in os.listdir(bak) if f.startswith('patch-W')]) == 1, 'patch-W backed up once')

    # ---- 3. redeploy x5: no growth, one backup per archive per session
    sizes = []
    for i in range(5):
        cd.deploy(root, [(src, 'Everwood/WBSTest/new.bin')], protected=(), backup_dir=bak,
                  release_game_data=panel.release_game_data)
        sizes.append(os.path.getsize(X))
    T.check(max(sizes) <= sizes[0] and len(set(sizes)) == 1,
            'redeploy x5 leaves patch-X size constant (compaction): %s' % sizes)
    T.check(sizes[0] <= size0[X] + 6000 + 4096, 'patch-X is about one copy larger than the original: %d vs %d' % (sizes[0], size0[X]))
    T.check(len([f for f in os.listdir(bak) if f.startswith('patch-X')]) == 1, 'still ONE backup of patch-X after 6 deploys')

    # ---- 4. size guard
    before = os.path.getsize(X)
    old = cd.MAX_ARCHIVE_BYTES
    cd.MAX_ARCHIVE_BYTES = 1000
    try:
        cd.deploy(root, [(src, 'Everwood/WBSTest/new.bin')], protected=(), backup_dir=bak,
                  release_game_data=panel.release_game_data)
        T.check(False, 'size guard refuses')
    except cd.DeployError as e:
        T.check('GB' in str(e) and 'refused' in str(e), 'size guard refuses: ' + str(e)[:110])
    finally:
        cd.MAX_ARCHIVE_BYTES = old
    T.check(os.path.getsize(X) == before, 'refused deploy left the archive untouched')
    T.check(cd.check_archive(os.path.join(SRC_DATA, 'patch-3.mpq'), protected=(), probe_write=False) is not None,
            'the real 1.96 GB patch-3.mpq would be refused by the default threshold')

    # ---- 5. protected path
    try:
        cd.deploy(root, [(src, 'Everwood/WBSTest/new.bin')], protected=('fakeclient',), backup_dir=bak,
                  release_game_data=panel.release_game_data)
        T.check(False, 'protected path refuses')
    except cd.DeployError as e:
        T.check('protected' in str(e) and 'fakeclient' in str(e), 'protected-path guard refuses: ' + str(e)[:110])
    live = make_client(os.path.join(common.TMP, 'benilla_deploy_copy'), ['patch-X.mpq'])
    try:
        cd.deploy(live, [(src, 'Everwood/WBSTest/new.bin')], backup_dir=bak, release_game_data=panel.release_game_data)
        T.check(False, 'default protection refuses benilla_deploy')
    except cd.DeployError as e:
        T.check('protected' in str(e), 'default protected fragment benilla_deploy refuses: ' + str(e)[:90])

    # ---- 6. locked archive
    k, h = lock_exclusive(X)
    try:
        T.check(h not in (None, 0, ctypes.c_void_p(-1).value), 'test holds patch-X exclusively')
        try:
            cd.deploy(root, [(src, 'Everwood/WBSTest/new.bin')], target_archive='patch-X.mpq', protected=(),
                      backup_dir=bak, release_game_data=panel.release_game_data)
            T.check(False, 'locked archive refused')
        except cd.DeployError as e:
            T.check('locked' in str(e) and 'patch-X' in str(e), 'locked archive refused: ' + str(e)[:110])
        # new path with the top archive locked: default target skips it
        rep = cd.deploy(root, [(mk('other.bin', b'x' * 100), 'Everwood/WBSTest/other.bin')], protected=(),
                        backup_dir=bak, release_game_data=panel.release_game_data)
        T.check(os.path.basename(rep.target).lower() == 'patch-w.mpq',
                'default target skips the locked archive: ' + os.path.basename(rep.target))
    finally:
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CloseHandle(h)
    T.check(os.path.getsize(X) == before, 'locked archive was not modified')

    # ---- 7. sibling discovery (M2 skin/anim, WMO groups)
    d = os.path.join(common.TMP, 'sib')
    os.makedirs(d, exist_ok=True)
    for n in ('Foo.m2', 'Foo00.skin', 'Foo01.skin', 'Foo0000-00.anim', 'Foobar.m2', 'Foo.txt',
              'Hut.wmo', 'Hut_000.wmo', 'Hut_001.wmo', 'Hut2_000.wmo'):
        with open(os.path.join(d, n), 'wb') as f:
            f.write(b'x')
    m2 = sorted(i for _l, i in cd.sibling_files(os.path.join(d, 'Foo.m2'), 'World/Generic/Foo.m2'))
    T.check(m2 == sorted(['World\\Generic\\Foo.m2', 'World\\Generic\\Foo00.skin', 'World\\Generic\\Foo01.skin',
                          'World\\Generic\\Foo0000-00.anim']), 'M2 siblings: %s' % m2)
    wm = sorted(i for _l, i in cd.sibling_files(os.path.join(d, 'Hut.wmo'), 'World\\wmo\\Hut.wmo'))
    T.check(wm == ['World\\wmo\\Hut.wmo', 'World\\wmo\\Hut_000.wmo', 'World\\wmo\\Hut_001.wmo'], 'WMO siblings: %s' % wm)

    # ---- 8. operator + panel registered
    T.check(hasattr(bpy.ops.wbs, 'send_to_test_client'), 'wbs.send_to_test_client operator registered')
    wm = bpy.context.window_manager
    T.check(wm.wbs_deploy.protected_paths == '', 'protected-paths field starts empty (no Everwood path shown to others)')
    DP = common.module('ui.deploy_panel')
    T.check('benilla_deploy' in DP.protected_list(wm), 'benilla_deploy is still always refused (hidden safety guard)')
    wm.wbs_deploy.protected_paths = 'my_live_client'
    T.check(set(DP.protected_list(wm)) == {'my_live_client', 'benilla_deploy'}, 'user fragments add to the guard')


common.run(T, body)
