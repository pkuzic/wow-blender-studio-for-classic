# Model Browser texture picker: short ranked list (DBC-paired, then same name family), prev/next arrows,
# "Search all" popup over the whole folder, thumbnails.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('tex_picker')


class FakeLayout:
    def __init__(self, log):
        object.__setattr__(self, 'log', log)

    def __getattr__(self, name):
        def fn(*a, **k):
            if name == 'operator' and a:
                self.log.append('op:' + a[0])
            elif name == 'prop' and len(a) > 1:
                self.log.append('prop:' + a[1])
            elif name == 'label':
                self.log.append('label:' + str(k.get('text', '')))
            return FakeLayout(self.log)
        return fn

    def __setattr__(self, k, v):
        pass


def body(T):
    common.setup_project()
    MB = common.module('ui.model_browser')
    st = bpy.context.window_manager.wbs_browser
    MB.build_index(); MB.refilter()

    fp = MB._family_prefix
    T.check(fp('Item\\ObjectComponents\\Head\\Helm_Plate_A_01Crimson_HuM.m2') == 'helm_plate_a_01', 'family of a helm')
    T.check(fp('Item\\ObjectComponents\\Weapon\\Sword_2H_Claymore_C_01.m2') == 'sword_2h_claymore_c_01', 'family of a sword')
    T.check(fp('X\\Rat.m2') == '', 'too vague a name has no family')

    # a head-folder helm: hundreds of BLPs in the folder, a handful paired by ItemDisplayInfo
    st.source = 'ALL'; st.kind = 'M2'
    st.search = 'objectcomponents head helm_plate'
    T.check(len(st.results) > 0, 'helm models found (%d)' % len(st.results))
    slot_pos = found = None
    for i in range(min(40, len(st.results))):
        st.active = i
        for pos, it in enumerate(st.slots):
            if it.ttype == 2 and MB.PRIMARY.get((st.current, it.index)):
                slot_pos, found = pos, st.current
                break
        if found:
            break
    T.check(found is not None, 'a helm with ItemDisplayInfo textures: %s' % found)
    if not found:
        return
    it = st.slots[slot_pos]
    key = (st.current, it.index)
    full, short = MB.CANDIDATES[key], MB.short_candidates(*key)
    T.info('%s: %d in folder list, %d in short list (%d used by game, %d similar)' % (
        os.path.basename(found), len(full) - 1, len(short) - 1, MB.PRIMARY[key], MB.FAMILY[key]))
    T.check(len(full) > 100 and len(short) < len(full) / 3, 'the dropdown is a short list, not the whole folder')
    T.check(short[0][0] == 'NONE' and all(x[2].startswith('ItemDisplayInfo') for x in short[1:1 + MB.PRIMARY[key]]),
            'game-paired textures come first')
    T.check(all(x[1].endswith('(similar)') for x in short[1 + MB.PRIMARY[key]:]), '...then the same name family')
    enum = MB._slot_items(it, bpy.context)
    T.check(len(enum) == len(short) and all(len(x) == 5 for x in enum), 'dropdown enum = short list, numbered items')
    T.check(sum(1 for x in enum if isinstance(x[3], int) and x[3]) >= min(len(enum) - 1, 3), 'dropdown items have thumbnails')

    # arrows
    real = [x[0] for x in short if x[0] != 'NONE']
    first = it.choice
    ms0 = st.render_ms
    nxt = MB.step_texture(slot_pos, 1)
    T.check(len(real) < 2 or (nxt != first and it.choice == nxt), 'next arrow moves to another texture (%s)' % nxt)
    T.check(MB.step_texture(slot_pos, -1) == first, 'previous arrow comes back')
    it.choice = real[-1]
    T.check(MB.step_texture(slot_pos, 1) == real[0], 'next wraps around at the end of the short list')
    bpy.ops.wbs.browser_tex_step(slot=slot_pos, step=1)
    T.check(it.choice == real[1 % len(real)], 'arrow operator works')

    # search all
    op_items = MB._search_items(type('O', (), {'slot': slot_pos})(), bpy.context)
    T.check(len(op_items) == len(full), 'search popup offers every texture of the folder (%d)' % len(op_items))
    other = next(x[0] for x in full[1 + MB.PRIMARY[key] + MB.FAMILY[key]:])
    T.check(MB.pick_texture(slot_pos, other) and it.choice == other, 'picking from search uses it: %s' % os.path.basename(other))
    T.check(other in [x[0] for x in MB.short_candidates(*key)], '...and it stays in the dropdown')
    T.check(not MB.pick_texture(slot_pos, 'Nope\\missing.blp'), 'unknown path refused')
    bpy.ops.wbs.browser_tex_search('EXEC_DEFAULT', slot=slot_pos, texture=full[1][0])
    T.check(it.choice == full[1][0], 'search operator applies its choice')

    # panel draws arrows + search
    log = []
    MB.WBS_PT_model_browser.draw(type('P', (), {'layout': FakeLayout(log),
                                               '_draw_progress': MB.WBS_PT_model_browser._draw_progress,
                                               '_draw_geosets': MB.WBS_PT_model_browser._draw_geosets,
                                               '_draw_anim': MB.WBS_PT_model_browser._draw_anim})(), bpy.context)
    T.check('op:wbs.browser_tex_step' in log and 'op:wbs.browser_tex_search' in log, 'panel shows arrows and search')
    T.check(any(' in game' in x for x in log), 'panel says how many textures the game uses: %s' %
            next((x for x in log if ' in game' in x), ''))


common.run(T, body)
