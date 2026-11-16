# Shared helpers for WBS GUI tests (Everwood Classic fork).
#
# CONTRACT (every tests/test_*.py follows it):
#   * It is a Blender script run by tools/run_tests.py in a GUI Blender (OpenGL is needed by the add-on) with a
#     FRESH, throw-away BLENDER_USER_CONFIG, and BLENDER_USER_SCRIPTS pointing at the folder that contains
#     addons/<this add-on>.
#   * Environment: WBS_CLIENT  = WoW client folder (default G:\tw_experiment\benilla_local)
#                  WBS_TEST_OUT = path of the JSON result file to write
#                  WBS_TEST_TMP = scratch folder for this test (cache dir etc.)
#   * Structure:   import common;  T = common.Test('name')
#                  def body(T): ... T.check(cond, 'message') ...
#                  common.run(T, body)          # schedules body on a timer, writes JSON, quits Blender
#   * Never touch the user's real client archives in place: copy what you need into WBS_TEST_TMP.
#
# The JSON result: {"name", "passed", "failed", "checks": [{"ok", "msg"}], "error": traceback-or-null}

import os
import sys
import json
import time
import traceback

import bpy

ADDON = None
for _name in ('io_scene_wmo', 'wow-blender-studio-for-classic-main'):
    if os.path.isdir(os.path.join(bpy.utils.user_resource('SCRIPTS', path='addons'), _name)):
        ADDON = _name
        break
ADDON = os.environ.get('WBS_ADDON', ADDON or 'io_scene_wmo')

CLIENT = os.environ.get('WBS_CLIENT', r"G:\tw_experiment\benilla_local")
OUT = os.environ.get('WBS_TEST_OUT', os.path.join(os.environ.get('TEMP', '.'), 'wbs_test.json'))
TMP = os.environ.get('WBS_TEST_TMP', os.path.join(os.environ.get('TEMP', '.'), 'wbs_test_tmp'))
os.makedirs(TMP, exist_ok=True)


class Test:
    def __init__(self, name):
        self.name = name
        self.checks = []
        self.error = None
        self.t0 = time.time()

    def check(self, cond, msg):
        ok = bool(cond)
        self.checks.append({'ok': ok, 'msg': str(msg)})
        print(('[PASS] ' if ok else '[FAIL] ') + str(msg))
        self.save()
        return ok

    def info(self, msg):
        self.checks.append({'ok': None, 'msg': str(msg)})
        print('       ' + str(msg))
        self.save()

    def save(self):
        res = {'name': self.name,
               'passed': sum(1 for c in self.checks if c['ok'] is True),
               'failed': sum(1 for c in self.checks if c['ok'] is False) + (1 if self.error else 0),
               'seconds': round(time.time() - self.t0, 1),
               'checks': self.checks, 'error': self.error}
        try:
            with open(OUT, 'w', encoding='utf-8') as f:
                json.dump(res, f, indent=1)
        except OSError:
            pass


def module(sub):
    """sys.modules entry of an add-on submodule, e.g. module('ui.model_browser')."""
    return sys.modules[ADDON + '.' + sub]


def enable_addon():
    import addon_utils
    addon_utils.enable(ADDON, default_set=True, persistent=False)
    return bpy.context.preferences.addons[ADDON].preferences


def setup_project(client=None, version='0'):
    """Enable the add-on, create one project pointing at the client, cache in TMP. Returns project prefs."""
    prefs = enable_addon()
    if not len(prefs.projects):
        bpy.ops.wbs.project_list_action('INVOKE_DEFAULT', action='ADD')
    P = module('ui.preferences')
    pp = P.get_project_preferences()
    pp.wow_path = client or CLIENT
    pp.cache_dir_path = os.path.join(TMP, 'cache')
    os.makedirs(pp.cache_dir_path, exist_ok=True)
    bpy.context.scene.wow_scene.version = version
    return pp


def new_scene(kind='M2', version='0'):
    bpy.ops.scene.new(type='NEW')
    bpy.context.scene.wow_scene.version = version
    bpy.context.scene.wow_scene.type = kind
    return bpy.context.scene


def import_game_model(path, version=0):
    """Import a model from the client archives with the regular WBS game-data importers."""
    if path.lower().endswith('.m2'):
        from importlib import import_module
        import_module(ADDON + '.m2.import_m2').import_m2_gamedata(version, path, False)
    else:
        from importlib import import_module
        import_module(ADDON + '.wmo.import_wmo').import_wmo_to_blender_scene_gamedata(path, version)


def run(T, body, delay=2.0, quit_after=1.0):
    def step():
        try:
            body(T)
        except Exception:
            T.error = traceback.format_exc()
            print(T.error)
        T.save()
        bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=quit_after)
        return None
    bpy.app.timers.register(step, first_interval=delay)
