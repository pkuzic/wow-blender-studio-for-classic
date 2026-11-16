# Everwood Classic fork: "WBS Character" panel (3D View > Sidebar) - safe export + .emorph shape keys.
# Logic lives in m2/safe_export.py and m2/emorph_io.py; the operators are registered by auto_load from there.
import bpy

from ..m2.safe_export import find_meshes, VID_ATTR
from ..m2.emorph_io import read_meta, NEG_SUFFIX
from ..utils.misc import everwood_mode


class WBS_PT_character_tools(bpy.types.Panel):
    bl_label = 'Character'
    bl_idname = 'WBS_PT_character_tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'WBS Character'

    def draw(self, context):
        layout = self.layout
        meshes = find_meshes(context)
        keys = set()
        for o in meshes:
            sk = o.data.shape_keys
            if sk:
                keys.update(kb.name for kb in sk.key_blocks[1:])
        meta = read_meta()

        box = layout.box()
        box.label(text='%d M2 meshes' % len(meshes), icon='MESH_DATA')
        ew = everwood_mode()
        if ew:
            n_morph = len([k for k in keys if not k.endswith(NEG_SUFFIX)])
            box.label(text='%d morphs' % n_morph + ((' (%d in file)' % len(meta['entries'])) if meta else ''),
                      icon='SHAPEKEY_DATA')

        col = layout.column(align=True)
        col.label(text='Safe export (positions only)')
        col.operator('wbs.m2_safe_export', icon='EXPORT')
        if ew:                                       # .emorph = Everwood client slider format
            col.separator()
            col.label(text='Morphs (.emorph)')
            col.operator('wbs.emorph_load', icon='IMPORT')
            col.operator('wbs.emorph_save', icon='FILE_TICK')

        status = context.scene.get('wbs_char_status')
        if status:
            sb = layout.box()
            for line in str(status).split('\n')[:14]:
                for i in range(0, min(len(line), 180), 36):       # wrap: the sidebar is narrow
                    sb.label(text=line[i:i + 36])
