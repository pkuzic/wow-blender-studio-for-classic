# Everwood mode (add-on preferences) gates the Everwood-only tools: .emorph load/save, HD (Data\Upscale) preview
# textures, the Everwood client note in Send to test client. Off by default; general 1.12 tools stay available.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('everwood_mode')


class FakeLayout:
    """Records what a panel draws (operator ids, props, labels) without a real UI."""
    def __init__(self, log):
        self.log = log

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
        if k == 'log':
            object.__setattr__(self, k, v)


def drawn(panel_cls):
    """Run panel_cls.draw on a stand-in object that has the panel's own helper methods and a recording layout."""
    log = []
    members = {k: v for k, v in vars(panel_cls).items() if callable(v) or isinstance(v, (staticmethod, classmethod))}
    members['layout'] = FakeLayout(log)
    panel = type('P', (), members)()
    panel_cls.draw(panel, bpy.context)
    return log


def body(T):
    common.setup_project()
    prefs = bpy.context.preferences.addons[common.ADDON].preferences
    misc = common.module('utils.misc')
    T.check(hasattr(prefs, 'everwood_mode') and prefs.everwood_mode is False, 'Everwood mode exists and is OFF by default')
    T.check(misc.everwood_mode() is False, 'everwood_mode() reports off')

    # ---- OFF: Everwood-only tools hidden / refused, general tools present
    T.check(not bpy.ops.wbs.emorph_load.poll() and not bpy.ops.wbs.emorph_save.poll(),
            '.emorph load/save refuse outside Everwood mode')
    CT = common.module('ui.character_tools')
    log = drawn(CT.WBS_PT_character_tools)
    T.check('op:wbs.m2_safe_export' in log, 'Character panel still offers Safe Export (general 1.12 tool)')
    T.check(not any('emorph' in x for x in log), 'Character panel hides the .emorph buttons')
    DP = common.module('ui.deploy_panel')
    log = drawn(DP.WBS_PT_send_to_test_client)
    T.check(not any('benilla_deploy' in x for x in log), 'Send to test client shows no Everwood client path')
    T.check('benilla_deploy' in DP.protected_list(bpy.context.window_manager),
            '...but the Everwood LIVE client stays protected underneath')
    MB = common.module('ui.model_browser')
    st = bpy.context.window_manager.wbs_browser
    MB.build_index(); MB.refilter()
    st.search = 'ogre female'
    for i, it in enumerate(st.results):
        if it.path.lower().endswith('ogremage.m2'):
            st.active = i
    log = drawn(MB.WBS_PT_model_browser)
    T.check(not any('use_hd' in x or 'Upscale' in x for x in log), 'browser hides the HD (Upscale) toggle')
    gd = misc.load_game_data()
    skin = next(it for it in st.slots if it.ttype == 1).choice
    st.use_hd = True                                    # even if the stored toggle is on...
    MB.TEXTURES.clear()
    t_off = MB._load_texture(gd, skin)
    T.check(t_off is not None and t_off.shape[0] <= 512, '...HD textures are not used outside Everwood mode (%s)'
            % str(None if t_off is None else t_off.shape[:2]))

    # ---- ON: everything appears
    common.set_everwood_mode(True)
    T.check(misc.everwood_mode() is True, 'everwood_mode() reports on after ticking the preference')
    T.check(bpy.ops.wbs.emorph_load.poll() and bpy.ops.wbs.emorph_save.poll(), '.emorph load/save available')
    log = drawn(CT.WBS_PT_character_tools)
    T.check('op:wbs.emorph_load' in log and 'op:wbs.emorph_save' in log, 'Character panel shows the .emorph buttons')
    log = drawn(DP.WBS_PT_send_to_test_client)
    T.check(any('benilla_deploy' in x for x in log), 'Send to test client shows the always-protected Everwood client')
    log = drawn(MB.WBS_PT_model_browser)
    T.check(any('use_hd' in x for x in log), 'browser shows the HD (Upscale) toggle')
    MB.TEXTURES.clear()
    t_on = MB._load_texture(gd, skin)
    T.check(t_on is not None and t_off is not None and t_on.shape[0] > t_off.shape[0],
            'HD textures used in Everwood mode (%s vs %s)' % (str(None if t_on is None else t_on.shape[:2]),
                                                              str(None if t_off is None else t_off.shape[:2])))

    # ---- preference drawing has the Everwood section
    log = []
    P = common.module('ui.preferences')
    P.WBS_AP_Preferences.draw(type('X', (), {'layout': FakeLayout(log), 'projects': prefs.projects,
                                             'active_project_index': 0, 'everwood_mode': True,
                                             'update_auto_check': True, 'update_interval_days': 1,
                                             'update_custom_url': ''})(), bpy.context)
    T.check('prop:everwood_mode' in log, 'add-on preferences show the Everwood mode checkbox')


common.run(T, body)
