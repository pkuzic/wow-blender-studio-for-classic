# Model Browser test: background index with progress, search / preview / textures (ports of the old ad-hoc
# test), geoset picker, animation playback, ItemDisplayInfo textures, archive list, favourites, HD textures.
# The body is a generator: every `yield seconds` hands control back to Blender's event loop (timers must keep
# running - that is part of what is tested).
import os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
import common

T = common.Test('browser')
FRAMES = os.path.join(common.TMP, 'frames')
os.makedirs(FRAMES, exist_ok=True)


def pick(st, needle):
    for i, it in enumerate(st.results):
        if needle.lower() in it.path.lower():
            st.active = i
            return it.path
    return None


def save_frame(MB, name, rgba):
    MB._write_png(os.path.join(FRAMES, name + '.png'), rgba)


def body(T):
    pp = common.setup_project()
    MB = common.module('ui.model_browser')
    MP = common.module('utils.model_preview')
    st = bpy.context.window_manager.wbs_browser
    gd = None

    # ---------------------------------------------------------------- 1. background index with progress
    ticks = [0]

    stamps = []

    def tick():
        ticks[0] += 1
        stamps.append(time.time())
        return 0.05
    bpy.app.timers.register(tick, first_interval=0.05)

    t0 = time.time()
    MB.load_game_data()                      # first-use archive mounting (not part of the index listing)
    T.info('game data mounted in %.2fs' % (time.time() - t0))
    t0 = time.time()
    r = bpy.ops.wbs.browser_index(force=True)
    t_call = time.time() - t0
    T.check(r == {'FINISHED'} and MB.JOB['active'], 'index operator returned at once (%.2fs) with the job running in the '
            'background' % t_call)
    T.check(t_call < 1.5, 'starting the index did not block (%.2fs)' % t_call)
    total = MB.JOB['total']
    ticks0, seen_done = ticks[0], set()
    t_job = time.time()
    prog = []
    while MB.JOB['active'] and time.time() - t_job < 120:
        seen_done.add(MB.JOB['done'])
        prog.append((round(time.time() - t_job, 2), MB.JOB['done']))
        yield 0.05
    T.info('progress samples (s, done): %s' % prog[:40])
    T.info('tick times since start: %s' % [round(x - t_job, 2) for x in stamps if x >= t_job][:40])
    dur = time.time() - t_job
    T.check(not MB.JOB['active'] and not MB.JOB['error'], 'index job finished in %.1fs (error=%s, mode=%s)' % (dur, MB.JOB['error'], MB.JOB['mode']))
    T.check(MB.JOB['mode'] == 'process', 'the listing ran in the worker process (not the in-process fallback)')
    T.check(total > 5 and MB.JOB['done'] == total, 'progress reached %d / %d archives; %d distinct values seen while '
            'running' % (MB.JOB['done'], total, len(seen_done)))
    T.check(ticks[0] - ticks0 >= max(2, int(dur / 0.05 * 0.25)),
            'UI timers kept running during indexing: %d ticks in %.1fs' % (ticks[0] - ticks0, dur))
    T.check(len(MB.INDEX['models']) > 100, 'index: %d models, %d archives, %d patch archives' % (
        len(MB.INDEX['models']), len(MB.INDEX['archives']), len(MB.INDEX['patch_archives'])))
    n_models = len(MB.INDEX['models'])
    MB.INDEX['key'] = None
    t0 = time.time()
    r = bpy.ops.wbs.browser_index()
    t_cached = time.time() - t0
    T.check(not MB.JOB['active'] and len(MB.INDEX['models']) == n_models,
            'index served from the disk cache (%.2fs), %d models' % (t_cached, len(MB.INDEX['models'])))
    gd = MB.load_game_data()

    # ---------------------------------------------------------------- ogress: search, skins, hair
    st.view = 'ALL'
    st.source = 'PATCH'
    st.kind = 'M2'
    st.search = 'ogre female'
    ogre = 'Character\\Ogre\\Female\\OgreMage.m2'
    hit = [(it.path, it.archive) for it in st.results if it.path.lower() == ogre.lower()]
    T.check(hit and hit[0][1] == 'patch-Z.mpq', 'search "ogre female" finds the ogress in patch-Z: %s' % hit)
    p = pick(st, ogre)
    T.check(p is not None and st.preview_icon > 0, 'ogress selected, preview icon set (render %d ms)' % st.render_ms)
    skin = next((it for it in st.slots if it.ttype == 1), None)
    skins = [x for x in (MB.CANDIDATES.get((st.current, skin.index)) or []) if x[1].startswith('Skin')] if skin else []
    T.check(len(skins) >= 6, 'ogress offers %d CharSections skins' % len(skins))
    hair = next((it for it in st.slots if it.ttype == 6), None)
    hairs = [x for x in (MB.CANDIDATES.get((st.current, hair.index)) or []) if x[1].startswith('Hair')] if hair else []
    T.check(len(hairs) >= 1, 'ogress offers %d CharSections hair textures' % len(hairs))
    save_frame(MB, 'ogress_default', MP.render(MB.build_view(st, MB.MESHES[st.current])[0], {}, 256, 35, 12))
    blue = next((x[0] for x in skins if 'blue' in x[0].lower()), None)
    if blue:
        skin.choice = blue
        T.check('blue' in skin.choice.lower(), 'skin switched to %s and re-rendered (%d ms)' % (os.path.basename(blue), st.render_ms))

    # ---------------------------------------------------------------- 5. archives holding the file
    T.check(MB.HOLDERS and MB.HOLDERS[0] == 'patch-Z.mpq', 'archive list for the ogress: %s (winner first)' % MB.HOLDERS)
    T.check(len(set(MB.HOLDERS)) == len(MB.HOLDERS), 'archive list has no duplicates')

    # ---------------------------------------------------------------- 2. geoset picker
    mesh = MB.MESHES[st.current]
    n_geo = len(st.geosets)
    default_tris = st.tri_count
    T.check(n_geo > 10 and sum(1 for g in st.geosets if g.on) == len(mesh.default_geo),
            'geoset picker: %d ids, %d checked by default, %d triangles' % (n_geo, len(mesh.default_geo), default_tris))
    bpy.ops.wbs.browser_geosets(mode='ALL')
    all_tris = st.tri_count
    bpy.ops.wbs.browser_geosets(mode='NONE')
    none_tris = st.tri_count
    bpy.ops.wbs.browser_geosets(mode='DEFAULT')
    T.check(all_tris > default_tris and none_tris == 0 and st.tri_count == default_tris,
            'geoset presets change the triangle count: all %d > default %d > none %d' % (all_tris, default_tris, none_tris))
    extra = next((g for g in st.geosets if not g.on), None)
    if extra:
        extra.on = True
        T.check(st.tri_count > default_tris, 'ticking one more geoset (%d) adds triangles: %d -> %d' % (
            extra.gid, default_tris, st.tri_count))
        extra.on = False
    T.check(st.tri_count == default_tris, 'unticking restores the default (%d triangles)' % st.tri_count)

    # ---------------------------------------------------------------- 3. animation (ogress)
    names = [i[1] for i in MB.ANIM_ITEMS]
    T.check(len(MB.ANIM_ITEMS) > 20 and any(n.startswith('Stand') for n in names) and any(n.startswith('Walk') for n in names),
            'sequence dropdown: %d entries, e.g. %s' % (len(MB.ANIM_ITEMS), names[1:5]))
    walk = next(i for i in MB.ANIM_ITEMS if i[1].startswith('Walk'))
    st.anim_seq = walk[0]
    seq = MB.current_sequence(st, mesh)
    T.check(seq is not None and st.anim_pos == 0.0, 'Walk selected (sequence %s)' % seq)
    rest = mesh.verts
    lo0, hi0 = rest.min(axis=0), rest.max(axis=0)
    ext = float(np.linalg.norm(hi0 - lo0))
    v0, _n = mesh.anim.pose(mesh, seq, 0)
    dur_ms = mesh.anim.sequences[seq]['duration']
    frames = []
    for k, f in enumerate((0.0, 0.25, 0.5, 0.75)):
        st.anim_pos = f
        view, fit = MB.build_view(st, mesh)
        frames.append(view.verts.copy())
        img = MP.render(view, {}, 256, 90, 8, fit=fit)
        save_frame(MB, 'ogress_walk_%d' % k, img)
    diff = float(np.abs(frames[2] - frames[0]).max())
    T.check(diff > 0.05, 'walk frame at 50%% differs from frame 0 (max vertex move %.3f)' % diff)
    ok_box = True
    for fv in frames:
        lo, hi = fv.min(axis=0), fv.max(axis=0)
        ok_box &= bool(np.isfinite(fv).all() and (hi - lo).max() < 2.0 * ext and (hi - lo).max() > 0.3 * ext
                       and (lo > lo0 - ext).all() and (hi < hi0 + ext).all())
    T.check(ok_box, 'posed ogress stays inside a sane bounding box (model extent %.2f)' % ext)
    n_before = MB._preview_counter[0]
    pos0 = st.anim_pos
    st.anim_playing = True
    t_play = time.time()
    while time.time() - t_play < 2.0:
        yield 0.1
    st.anim_playing = False
    n_frames = MB._preview_counter[0] - n_before
    T.check(n_frames >= 3 and st.anim_pos != pos0, 'playback re-rendered %d frames in 2 s, time moved %.2f -> %.2f' % (
        n_frames, pos0, st.anim_pos))
    t_stop = MB._preview_counter[0]
    yield 0.5
    T.check(MB._preview_counter[0] == t_stop, 'pause stops the re-rendering')
    st.anim_seq = 'NONE'
    T.check(st.tri_count == default_tris, 'bind pose restored')

    # ---------------------------------------------------------------- WMO preview
    st.kind = 'WMO'
    st.search = 'fp_outland_draeni_hut_1'
    st.source = 'ALL'
    pick(st, 'fp_outland_draeni_hut_1.wmo')
    T.check(st.preview_icon > 0 and 'WMO' in st.info, 'WMO preview: %s | %s' % (st.current, st.info))
    save_frame(MB, 'wmo', MP.render(MB.MESHES[st.current], {}, 256, 35, 12))

    # ---------------------------------------------------------------- wolf: CreatureDisplayInfo + animation
    st.kind = 'M2'
    st.search = 'creature wolf'
    p = pick(st, 'creature\\wolf\\wolf.m2')
    cskin = [it for it in st.slots if it.ttype in (11, 12, 13)]
    disp = [x for it in cskin for x in (MB.CANDIDATES.get((st.current, it.index)) or []) if x[1].startswith('Display')]
    T.check(p is not None and len(disp) >= 1, 'wolf %s: %d CreatureDisplayInfo skins' % (p, len(disp)))
    wmesh = MB.MESHES[st.current]
    stand = next((i for i in MB.ANIM_ITEMS if i[1].startswith('Stand')), None)
    T.check(stand is not None, 'wolf has a Stand sequence in the dropdown')
    if stand:
        st.anim_seq = stand[0]
        wl, wh = wmesh.verts.min(axis=0), wmesh.verts.max(axis=0)
        wext = float(np.linalg.norm(wh - wl))
        fr = []
        for f in (0.0, 0.5):
            st.anim_pos = f
            view, fit = MB.build_view(st, wmesh)
            fr.append(view.verts.copy())
            save_frame(MB, 'wolf_stand_%d' % int(f * 10), MP.render(view, {}, 256, 90, 8, fit=fit))
        T.check(np.isfinite(fr[1]).all() and float(np.abs(fr[1] - fr[0]).max()) > 0.0 and
                float((fr[1].max(axis=0) - fr[1].min(axis=0)).max()) < 2.0 * wext,
                'wolf Stand frame 50% differs from frame 0 and is sane')
        st.anim_seq = 'NONE'

    # ---------------------------------------------------------------- 4. item textures via ItemDisplayInfo
    st.source = 'ALL'
    st.search = 'item objectcomponents weapon'
    found = None
    for i, it in enumerate(list(st.results)[:60]):
        st.active = i
        for slot in st.slots:
            if slot.ttype == 2:
                cands = [x for x in (MB.CANDIDATES.get((st.current, slot.index)) or []) if x[1].startswith('Item ')]
                if cands:
                    found = (st.current, slot, cands)
                    break
        if found:
            break
    T.check(found is not None, 'an Item\\ObjectComponents model gets ItemDisplayInfo textures: %s' % (
        '%s -> %d (%s)' % (found[0], len(found[2]), found[2][0][1]) if found else 'none found in the first 60'))
    if found:
        T.check(found[2][0][0].lower().startswith(os.path.dirname(found[0]).lower()) and found[2][0][0].lower().endswith('.blp'),
                'item texture path lives in the model folder: %s' % found[2][0][0])
        T.check(found[1].choice == found[2][0][0], 'the first ItemDisplayInfo texture is the default choice')
        T.check(MB._load_texture(gd, found[2][0][0], hd=False) is not None, 'item texture decodes')

    # ---------------------------------------------------------------- 6. favourites + recent
    st.search = 'ogre female'
    st.kind = 'M2'
    st.source = 'PATCH'
    pick(st, ogre)
    MB.USER['fav'] = []
    bpy.ops.wbs.browser_favourite()
    T.check(MB.is_fav(ogre), 'star toggled on')
    MB.USER['fav'], MB.USER['recent'] = ['junk'], ['junk']          # forget the in-memory copy ...
    MB.load_user()                                                   # ... and read the JSON back
    T.check(MB.is_fav(ogre) and MB.USER['recent'] and MB.USER['recent'][0].lower() == ogre.lower(),
            'favourite + recent survive a re-read of %s' % MB._user_file())
    st.search = ''
    st.view = 'FAV'
    T.check(st.matches >= 1 and any(it.path.lower() == ogre.lower() for it in st.results),
            'Favourites filter lists the ogress (%d)' % st.matches)
    st.view = 'RECENT'
    T.check(st.matches >= 1 and st.results[0].path.lower() == ogre.lower(),
            'Recent filter has %d model(s)' % st.matches)
    for i in range(25):                                              # cap at 20
        MB.touch_recent('Fake\\Model%d.m2' % i)
    T.check(len(MB.USER['recent']) == MB.RECENT_MAX, 'recent list is capped at %d' % MB.RECENT_MAX)
    st.view = 'ALL'
    bpy.ops.wbs.browser_favourite()
    T.check(not MB.is_fav(ogre), 'star toggled off')

    # ---------------------------------------------------------------- 7. HD textures
    st.kind = 'M2'
    st.source = 'PATCH'
    st.search = 'ogre female'
    pick(st, ogre)
    skin = next(it for it in st.slots if it.ttype == 1)
    sp = skin.choice
    T.check(MB.hd_available(gd), 'Data\\Upscale archives found: %s' % [n for n, _m in MB.HD['archives']][:4])
    n0 = MB._load_texture(gd, sp, hd=False)
    n1 = MB._load_texture(gd, sp, hd=True)
    T.check(n0 is not None and n1 is not None and n1.shape[0] > n0.shape[0],
            'HD ogress skin %s is larger: %s vs %s' % (sp, None if n1 is None else n1.shape[:2], None if n0 is None else n0.shape[:2]))
    st.use_hd = True
    T.check(st.preview_icon > 0, 'preview re-rendered with HD on (%d ms)' % st.render_ms)
    st.use_hd = False

    # ---------------------------------------------------------------- import through the browser
    if blue:
        skin.choice = blue
    r = bpy.ops.wbs.browser_import()
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    T.check(r == {'FINISHED'} and len(meshes) > 10, 'browser import: %d meshes' % len(meshes))
    skin_imgs = [img for img in bpy.data.images if img.wow_m2_texture.enabled and img.wow_m2_texture.texture_type == '1']
    if blue:
        T.check(skin_imgs and all('blue' in img.filepath.lower() for img in skin_imgs),
                'body-skin image now points at %s' % [os.path.basename(i.filepath) for i in skin_imgs])
        T.check(all(i.size[0] > 0 for i in skin_imgs), 'skin image loaded (%s)' % [tuple(i.size) for i in skin_imgs])
    ogress_scene = bpy.context.window.scene
    bpy.ops.scene.new(type='NEW')
    bpy.context.scene.wow_scene.version = '0'
    st.kind = 'WMO'
    st.search = 'fp_outland_draeni_hut_1'
    st.source = 'ALL'
    pick(st, 'fp_outland_draeni_hut_1.wmo')
    r = bpy.ops.wbs.browser_import()
    wobj = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    T.check(r == {'FINISHED'} and len(wobj) >= 1, 'WMO browser import: %d mesh objects' % len(wobj))
    bpy.context.window.scene = ogress_scene
    T.info('frames saved in %s' % FRAMES)

    # ---------------------------------------------------------------- panel draws without errors (screenshot)
    st.kind = 'M2'
    st.source = 'PATCH'
    st.search = 'ogre female'
    pick(st, ogre)
    st.show_geosets = True
    st.anim_seq = next(i for i in MB.ANIM_ITEMS if i[1].startswith('Walk'))[0]
    try:
        cls = bpy.types.WBS_PT_model_browser            # 3.4 cannot switch sidebar tabs from Python: show it in 'Item'
        bpy.utils.unregister_class(cls)
        cls.bl_category = 'Item'
        cls.bl_order = -100
        for name in ('VIEW3D_PT_transform', 'VIEW3D_PT_context_properties'):
            try:
                bpy.utils.unregister_class(getattr(bpy.types, name))
            except Exception:
                pass
        bpy.utils.register_class(cls)
        for area in bpy.context.window.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces[0].show_region_ui = True
                area.tag_redraw()
    except Exception:
        T.info('sidebar setup failed: ' + traceback.format_exc())
    yield 2.0
    shot = os.path.join(common.TMP, 'panel.png')
    try:
        bpy.ops.screen.screenshot(filepath=shot)
    except Exception as e:
        T.info('screenshot failed: %s' % e)
    T.check(os.path.isfile(shot), 'panel screenshot written (%s)' % shot)
    yield 0.5


def drive(T, gen_fn):
    gen = gen_fn(T)

    def step():
        try:
            return next(gen)
        except StopIteration:
            pass
        except Exception:
            T.error = traceback.format_exc()
            print(T.error)
        T.save()
        bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=1.0)
        return None
    bpy.app.timers.register(step, first_interval=2.0)


drive(T, body)
