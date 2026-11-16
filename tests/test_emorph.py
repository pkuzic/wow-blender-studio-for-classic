# .emorph: load as shape keys on the ogress, save back unedited (semantically + byte identical), edit one key.
import os, sys, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
import common

T = common.Test('emorph')
GAME_PATH = r"Character\Ogre\Female\OgreMage.m2"
SRC = r"G:\mangos\ogre_female_extract\model\OgreMage.emorph"
SRC_M2 = r"G:\mangos\ogre_female_extract\model\OgreMage.m2"
CHECKER = r"G:\mangos\tortoise-wow\custom\model-pipeline\morphs\check_emorph.py"


def same(a, b, tol=1e-5):
    """semantic equality of two parsed files -> list of differences"""
    d = []
    if a['n_model_v'] != b['n_model_v']:
        d.append('n_model_v')
    if len(a['morphs']) != len(b['morphs']):
        d.append('entry count %d vs %d' % (len(a['morphs']), len(b['morphs'])))
        return d
    for x, y in zip(a['morphs'], b['morphs']):
        for f in ('key', 'pid', 'cat', 'en', 'ru'):
            if x[f] != y[f]:
                d.append('%s.%s' % (x['key'], f))
        if not np.array_equal(x['idx'], y['idx']):
            d.append('%s.idx' % x['key'])
        elif len(x['idx']) and np.abs(x['delta'] - y['delta']).max() > tol:
            d.append('%s.delta' % x['key'])
        if (x['neg_idx'] is None) != (y['neg_idx'] is None):
            d.append('%s.neg presence' % x['key'])
        elif x['neg_idx'] is not None:
            if not np.array_equal(x['neg_idx'], y['neg_idx']) or np.abs(x['neg_delta'] - y['neg_delta']).max() > tol:
                d.append('%s.neg' % x['key'])
    return d


def body(T):
    common.setup_project()
    common.new_scene('M2')
    common.import_game_model(GAME_PATH)
    E = common.module('m2.emorph_io')
    SE = common.module('m2.safe_export')
    meshes = SE.find_meshes(bpy.context)
    T.check(len(meshes) > 10, '%d meshes' % len(meshes))

    src = os.path.join(common.TMP, 'OgreMage.emorph')
    shutil.copyfile(SRC, src)
    raw = open(src, 'rb').read()
    em = E.parse(raw)
    geo = [m for m in em['morphs'] if len(m['idx'])]
    negs = [m for m in em['morphs'] if m['neg_idx'] is not None]
    T.info('file: %d entries, %d with geometry, %d with negative shape, %d geometry-less' % (
        len(em['morphs']), len(geo), len(negs), len(em['morphs']) - len(geo)))

    r = E.load_emorph(meshes, src)
    T.check(r['ok'], 'load ok: errors=%s warnings=%s' % (r['errors'], r['warnings'][:3]))
    names = set()
    for o in meshes:
        sk = o.data.shape_keys
        if sk:
            names.update(k.name for k in sk.key_blocks[1:])
    T.check(len(names) == len(geo) + len(negs), 'shape-key names %d == geometry entries %d + negative shapes %d'
            % (len(names), len(geo), len(negs)))
    T.check(all(m['key'] in names for m in geo), 'every geometry entry has its shape key')
    T.check(all((m['key'] + '.neg') in names for m in negs), 'every negative shape has a .neg key')
    meta = E.read_meta()
    T.check(meta and len(meta['entries']) == len(em['morphs']), 'metadata text holds every entry (incl. geometry-less)')

    # unedited save
    out = os.path.join(common.TMP, 'saved.emorph')
    r = E.save_emorph(meshes, out)
    T.check(r['ok'], 'save ok: errors=%s warnings=%s' % (r['errors'], r['warnings'][:3]))
    saved = open(out, 'rb').read()
    diffs = same(em, E.parse(saved))
    T.check(not diffs, 'unedited save is semantically identical to the input %s' % diffs[:5])
    T.check(saved == raw, 'unedited save is BYTE-identical (%d vs %d bytes)' % (len(saved), len(raw)))

    # independent validator (needs scipy: system Python)
    if os.path.isfile(CHECKER) and os.path.isfile(SRC_M2):
        try:
            p = subprocess.run(['py', '-3', CHECKER, SRC_M2, out], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=600)
            tail = (p.stdout or '').strip().splitlines()[-3:]
            T.check(p.returncode == 0, 'check_emorph.py passes on the saved file (exit %d) %s' % (p.returncode, tail))
        except Exception as e:
            T.info('check_emorph.py could not run: %r' % e)

    # edit ONE key
    victim = geo[len(geo) // 2]
    key = victim['key']
    edited = None
    for o in meshes:
        sk = o.data.shape_keys
        if sk and key in sk.key_blocks:
            vid = np.empty(len(o.data.vertices), np.int32)
            o.data.attributes['wbs_m2_vid'].data.foreach_get('value', vid)
            kb = sk.key_blocks[key]
            i = int(np.nonzero(vid == int(victim['idx'][0]))[0][0])
            kb.data[i].co.x += 0.5
            edited = (o.name, i, int(vid[i]))
            break
    T.check(edited is not None, 'edited key %s at %s' % (key, edited))
    out2 = os.path.join(common.TMP, 'edited.emorph')
    r = E.save_emorph(meshes, out2)
    T.check(r['ok'], 'save after edit ok: %s' % (r['errors'],))
    em2 = E.parse(open(out2, 'rb').read())
    changed = [x['key'] for x, y in zip(em['morphs'], em2['morphs'])
               if same(dict(em, morphs=[x]), dict(em2, morphs=[y]))]
    T.check(changed == [key], 'only entry %s changed (%s)' % (key, changed))
    y = next(m for m in em2['morphs'] if m['key'] == key)
    pos = int(np.nonzero(y['idx'] == victim['idx'][0])[0][0])
    T.check(abs(float(y['delta'][pos, 0]) - float(victim['delta'][0, 0]) - 0.5) < 1e-4, 'edited delta +0.5 on x')

    # a new key gets the next free id
    o = next(o for o in meshes if o.data.shape_keys)
    nk = o.shape_key_add(name='My New Shape', from_mix=False)
    nk.data[0].co.z += 0.2
    p3 = os.path.join(common.TMP, 'newkey.emorph')
    r = E.save_emorph(meshes, p3)
    T.check(r['ok'], 'save with new key ok: %s' % (r['errors'],))
    em3 = E.parse(open(p3, 'rb').read())
    nm = [m for m in em3['morphs'] if m['key'] == 'my_new_shape']
    used = {m['pid'] for m in em['morphs']}
    T.check(len(nm) == 1 and nm[0]['en'] == 'My New Shape' and 100 <= nm[0]['pid'] <= 126 and nm[0]['pid'] not in used,
            'new key -> entry %s' % [(m['key'], m['pid'], m['en'], m['ru']) for m in nm])


common.run(T, body)
