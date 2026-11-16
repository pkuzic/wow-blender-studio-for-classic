"""UI for 'Send to test client' (see utils/client_deploy.py for the safety rules and the writing code)."""

import os

import bpy
from bpy.props import StringProperty, PointerProperty

from ..utils import client_deploy as cd
from ..utils.misc import everwood_mode


def release_game_data():
    """Close every MPQ handle this process holds (a writer cannot open an archive the game data has open) and drop
    the cached game data; it is re-created lazily by load_game_data()."""
    if hasattr(bpy, 'wow_game_data'):
        try:
            for storage, is_archive in bpy.wow_game_data.files:
                if is_archive:
                    storage.close()
        except Exception:
            pass
        delattr(bpy, 'wow_game_data')


class WBS_PG_deploy(bpy.types.PropertyGroup):
    protected_paths: StringProperty(
        name='Never deploy to paths containing',
        description="Semicolon separated fragments. Archives whose full path contains one are never written",
        default='')
    backup_dir: StringProperty(
        name='MPQ backup folder', subtype='DIR_PATH',
        description="Archives are copied here before their first write in a Blender session. Must be outside the "
                    "client. Empty = <project cache folder>\\wbs_mpq_backups")
    last_export: StringProperty(name='Last exported model', subtype='FILE_PATH')


def remember_export(filepath):
    """Called after an export so the dialog can offer that file first."""
    try:
        bpy.context.window_manager.wbs_deploy.last_export = filepath
    except Exception:
        pass


def _project():
    from .preferences import get_project_preferences
    return get_project_preferences()


def protected_list(wm):
    # the Everwood LIVE launcher client (cd.DEFAULT_PROTECTED) is ALWAYS refused, whatever the field says and even
    # outside Everwood mode - a safety guard that costs nothing elsewhere (no other client is called that)
    user = tuple(p.strip() for p in wm.wbs_deploy.protected_paths.split(';') if p.strip())
    return user + tuple(p for p in cd.DEFAULT_PROTECTED if p not in user)


def backup_folder(wm):
    b = wm.wbs_deploy.backup_dir
    if b:
        return bpy.path.abspath(b)
    pp = _project()
    return os.path.join(pp.cache_dir_path or os.path.expanduser('~'), 'wbs_mpq_backups')


def _default_model(context):
    """(file path, internal path) guess for the current scene."""
    wm = context.window_manager
    scene = context.scene
    last = wm.wbs_deploy.last_export
    stype = scene.wow_scene.type
    internal = ''
    path = ''
    if stype == 'M2':
        internal = scene.wow_scene.game_path.replace('/', '\\')
        pp = _project()
        if last and last.lower().endswith('.m2'):
            path = last
        elif internal and pp.export_dir_path:
            path = os.path.join(pp.export_dir_path, internal)
    else:
        try:
            from ..utils.collections import get_current_wow_model_collection
            col = get_current_wow_model_collection(scene, 'wow_wmo')
            if col is not None:
                stem = os.path.splitext(col.name)[0]
                internal = (col.wow_wmo.dir_path.replace('/', '\\').strip('\\') + '\\' + stem + '.wmo').lstrip('\\')
                pp = _project()
                path = os.path.join(pp.export_dir_path, col.wow_wmo.dir_path, stem + '.wmo')
        except Exception:
            pass
        if last and last.lower().endswith('.wmo'):
            path = last
    if last and not path:
        path = last
    return path, internal


_PLAN_CACHE = {}


class WBS_OT_send_to_test_client(bpy.types.Operator):
    bl_idname = 'wbs.send_to_test_client'
    bl_label = 'Send to test client'
    bl_description = ("Write the exported model (+ its .skin/.anim/_NNN.wmo siblings and extra files) into the "
                      "project's client MPQ archives, with backup, listfile update and compaction")
    bl_options = {'REGISTER'}

    filepath: StringProperty(name='Exported file', subtype='FILE_PATH',
                             description='The exported .m2 / .wmo (siblings with the same name are included)')
    internal_path: StringProperty(name='Game path', description='Path inside the MPQ, e.g. World\\Generic\\Foo.m2')
    extra_files: StringProperty(name='Extra files',
                                description="Additional files, separated by ';'. Put 'local path=Internal\\Path' to "
                                            "choose the internal path, otherwise the folder of the game path is used")
    target_archive: StringProperty(name='Target archive',
                                   description="Empty = the archive that currently wins for this path (or the best "
                                               "patch archive for a new path). Or a file name like patch-Y.mpq")

    # ------------------------------------------------------------------ helpers
    def _files(self):
        files = cd.sibling_files(bpy.path.abspath(self.filepath), self.internal_path)
        idir = os.path.dirname(self.internal_path.replace('/', '\\'))
        for item in [x.strip() for x in self.extra_files.split(';') if x.strip()]:
            if '=' in item:
                local, internal = item.split('=', 1)
            else:
                local, internal = item, (idir + '\\' if idir else '') + os.path.basename(item)
            files.append((bpy.path.abspath(local.strip()), internal.strip()))
        return files

    def _plan(self, context):
        wm = context.window_manager
        client = _project().wow_path
        files = self._files()
        key = (client, tuple(files), self.target_archive, wm.wbs_deploy.protected_paths)
        if key not in _PLAN_CACHE:
            try:
                target, _o, notes, problem = cd.plan(client, files, self.target_archive or None,
                                                     protected_list(wm), probe_write=False)
            except Exception as e:
                target, notes, problem = None, [], str(e)
            _PLAN_CACHE.clear()
            _PLAN_CACHE[key] = (files, target, notes, problem)
        return _PLAN_CACHE[key]

    # ------------------------------------------------------------------ operator
    def invoke(self, context, event):
        path, internal = _default_model(context)
        if not self.filepath:
            self.filepath = path
        if not self.internal_path:
            self.internal_path = internal
        return context.window_manager.invoke_props_dialog(self, width=640)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'filepath')
        layout.prop(self, 'internal_path')
        layout.prop(self, 'extra_files')
        layout.prop(self, 'target_archive')
        if not self.filepath or not os.path.isfile(bpy.path.abspath(self.filepath)):
            layout.label(text='Exported file not found - export first.', icon='ERROR')
            return
        if not self.internal_path:
            layout.label(text='Enter the game path (inside the MPQ).', icon='ERROR')
            return
        files, target, notes, problem = self._plan(context)
        box = layout.box()
        box.label(text='Client: ' + _project().wow_path)
        box.label(text='Target archive: ' + (os.path.basename(target) if target else '-'), icon='PACKAGE')
        for n in notes:
            box.label(text=n[:120], icon='ERROR' if n.startswith('WARNING') else 'INFO')
        if problem:
            for i in range(0, len(problem), 110):
                box.label(text=problem[i:i + 110], icon='CANCEL')
        box.label(text='Files (%d):' % len(files))
        for local, internal in files[:12]:
            box.label(text='  %s  (%s)' % (internal, '%d KB' % (os.path.getsize(local) // 1024)
                                          if os.path.isfile(local) else 'MISSING'))
        if len(files) > 12:
            box.label(text='  ... %d more' % (len(files) - 12))
        box.label(text='A backup of the archive is made on its first write this session; it is then compacted.')

    def execute(self, context):
        wm = context.window_manager
        try:
            files = self._files()
            rep = cd.deploy(_project().wow_path, files, self.target_archive or None, protected_list(wm),
                            backup_folder(wm), release_game_data)
        except cd.DeployError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, "Send to test client failed: %s" % e)
            return {'CANCELLED'}
        _PLAN_CACHE.clear()
        for line in rep.lines:
            self.report({'INFO'}, line)
        self.report({'INFO'}, "Sent %d file(s) to %s. Restart the test client to see it (archives are read at start)."
                    % (len(rep.written), os.path.basename(rep.target)))
        return {'FINISHED'}


class WBS_PT_send_to_test_client(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_label = "Send to test client"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        d = context.window_manager.wbs_deploy
        col.prop(d, 'protected_paths')
        if everwood_mode():
            col.label(text='Always protected: %s (Everwood LIVE client)' % ', '.join(cd.DEFAULT_PROTECTED),
                      icon='LOCKED')
        col.prop(d, 'backup_dir')
        col.operator(WBS_OT_send_to_test_client.bl_idname, icon='EXPORT')

    @classmethod
    def poll(cls, context):
        return context.scene is not None


def register():
    bpy.types.WindowManager.wbs_deploy = PointerProperty(type=WBS_PG_deploy)


def unregister():
    try:
        del bpy.types.WindowManager.wbs_deploy
    except Exception:
        pass
