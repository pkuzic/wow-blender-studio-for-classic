from ...utils.custom_object import CustomObject
from ...utils.bl_id_types_utils import match_id_name
from ..bl_render import BlenderWMOObjectRenderFlags
from .enums import SpecialColorLayers

from functools import partial

import bpy

_OBJECT_MODE_DESTRUCTIVE_OPS = {
    'OBJECT_OT_transform_apply',
    'OBJECT_OT_transforms_to_deltas',
    'OBJECT_OT_origin_set',
    'TRANSFORM_OT_mirror',
    'OBJECT_OT_visual_transform_apply'
}


class WoWWMOGroup(CustomObject):
    __wbs_bl_object_type__ = 'MESH'
    __wbs_prop_group_id__ = 'wow_wmo_group'

    _bl_render_renderflag_map = {
        SpecialColorLayers.Lightmap.name: BlenderWMOObjectRenderFlags.HasLightmap,
        SpecialColorLayers.BatchmapInt.name: BlenderWMOObjectRenderFlags.HasBatchB,
        SpecialColorLayers.BatchmapTrans.name: BlenderWMOObjectRenderFlags.HasBatchA,
        SpecialColorLayers.Blendmap.name: BlenderWMOObjectRenderFlags.HasBlendmap
    }

    @classmethod
    def match(cls, obj: bpy.types.Object) -> bool:
        return super().match(obj) \
           and any(match_id_name(col.name, 'Indoor')
                   or match_id_name(col.name, 'Outdoor') for col in obj.users_collection)
                   
    @classmethod
    def is_indoor(cls, obj: bpy.types.Object) -> bool:
        if WoWWMOGroup.match(obj):
            for col in obj.users_collection:
                if match_id_name(col.name, 'Indoor'):
                    return True
            return False
        else:
            return False

    @classmethod
    def is_outdoor(cls, obj: bpy.types.Object) -> bool:
        if WoWWMOGroup.match(obj):
            for col in obj.users_collection:
                if match_id_name(col.name, 'Outdoor'):
                    return True
            return False
        else:
            return False

    @classmethod
    def handle_object_if_matched(cls
                                 , update: bpy.types.DepsgraphUpdate) -> bool:
        obj: bpy.types.Object = update.id.original

        if not cls.match(obj):
            return False

        cls.on_each_update(update)

        return True

    @classmethod
    def on_each_update(cls, update: bpy.types.DepsgraphUpdate) -> bool:
        obj: bpy.types.Object = update.id.original
        mesh: bpy.types.Mesh = obj.data

        # change shader behavior depending on the presence of specially named color layers
        for col_name, flag in cls._bl_render_renderflag_map.items():
            col = mesh.color_attributes.get(col_name)

            if col:
                obj.pass_index |= flag
            else:
                obj.pass_index &= ~flag
        
        # update shader based on current place type
        if cls.is_outdoor(obj):
            obj.pass_index |= BlenderWMOObjectRenderFlags.IsOutdoor
            obj.pass_index &= ~BlenderWMOObjectRenderFlags.IsIndoor
        else:
            obj.pass_index &= ~BlenderWMOObjectRenderFlags.IsOutdoor
            obj.pass_index |= BlenderWMOObjectRenderFlags.IsIndoor

        return True


class WoWWMOFog(CustomObject):
    __wbs_bl_object_type__ = 'MESH'
    __wbs_prop_group_id__ = 'wow_wmo_fog'
    __wbs_allowed_modes__ = set()
    __wbs_allow_scale__ = True
    __wbs_allow_non_uniform_scale__ = False
    __wbs_allow_rotation__ = False
    __wbs_allow_modifiers__ = False
    __wbs_allow_constraints__ = False
    __wbs_allow_material_properties__ = False
    __wbs_allow_mesh_properties__ = False
    __wbs_allow_particles__ = False
    __wbs_allow_physics__ = False
    __wbs_banned_ops__ = _OBJECT_MODE_DESTRUCTIVE_OPS


class WoWWMODoodad(CustomObject):
    __wbs_bl_object_type__ = 'MESH'
    __wbs_prop_group_id__ = 'wow_wmo_doodad'
    __wbs_allowed_modes__ = set()
    __wbs_allow_scale__ = True
    __wbs_allow_non_uniform_scale__ = False
    __wbs_allow_rotation__ = True
    __wbs_allow_modifiers__ = False
    __wbs_allow_constraints__ = False
    __wbs_allow_material_properties__ = False
    __wbs_allow_mesh_properties__ = False
    __wbs_allow_particles__ = False
    __wbs_allow_physics__ = False
    __wbs_banned_ops__ = _OBJECT_MODE_DESTRUCTIVE_OPS

    @classmethod
    def on_each_update(cls, update: bpy.types.DepsgraphUpdate) -> bool:
        obj: bpy.types.Object = update.id.original

        # handle object copies
        if obj.active_material:
            if obj.active_material.users > 1:
                for i, mat in enumerate(obj.data.materials):
                    mat = mat.copy()
                    obj.data.materials[i] = mat

        return True


class WoWWMOLight(CustomObject):
    __wbs_bl_object_type__ = 'LIGHT'
    __wbs_prop_group_id__ = 'wow_wmo_light'
    __wbs_allowed_modes__ = set()
    __wbs_allow_scale__ = False
    __wbs_allow_non_uniform_scale__ = False
    __wbs_allow_rotation__ = False
    __wbs_allow_modifiers__ = False
    __wbs_allow_constraints__ = False
    __wbs_allow_material_properties__ = False
    __wbs_allow_particles__ = False
    __wbs_allow_physics__ = False
    __wbs_banned_ops__ = set()


class WoWWMOLiquid(CustomObject):
    __wbs_bl_object_type__ = 'MESH'
    __wbs_prop_group_id__ = 'wow_wmo_liquid'
    __wbs_allowed_modes__ = {'EDIT', 'SCULPT', 'VERTEX_PAINT'}
    __wbs_allow_scale__ = False
    __wbs_allow_non_uniform_scale__ = False
    __wbs_allow_rotation__ = False
    __wbs_allow_modifiers__ = False
    __wbs_allow_constraints__ = False
    __wbs_allow_material_properties__ = False
    __wbs_allow_particles__ = False
    __wbs_allow_physics__ = False
    __wbs_banned_ops__ = {
        'TRANSFORM_OT_mirror',
        'TRANSFORM_OT_mirror',
        'MESH_OT_delete',
        'MESH_OT_duplicate_move',
        'MESH_OT_extrude_region',
        'MESH_OT_extrude_verts_indiv',
        'MESH_OT_split',
        'MESH_OT_symmetrize',
        'MESH_OT_sort_elements',
        'MESH_OT_delete_loose',
        'MESH_OT_decimate',
        'MESH_OT_dissolve_degenerate',
        'MESH_OT_dissolve_limited',
        'MESH_OT_face_make_planar',
        'MESH_OT_face_make_planar',
        'MESH_OT_vert_connect_nonplanar',
        'MESH_OT_vert_connect_concave',
        'MESH_OT_bevel',
        'MESH_OT_merge'
    }

    @staticmethod
    def _liquid_edit_mode_timer(context: bpy.types.Context):
        bpy.ops.wow.liquid_edit_mode(context, 'INVOKE_DEFAULT')

    @staticmethod
    def _edit_mode(_: bpy.types.DepsgraphUpdate):
        win = bpy.context.window

        # avoid focusing settings window if left open
        if win.screen.name == 'temp':

            for win_ in bpy.context.window_manager.windows:
                if win_.screen.name != 'temp':
                    win = win_

        scr = win.screen
        areas3d = [area for area in scr.areas if area.type == 'VIEW_3D']
        region = [region for region in areas3d[0].regions if region.type == 'WINDOW'][0]
        space = [space for space in areas3d[0].regions if space.type == 'VIEW_3D']

        override = {'window': win,
                    'screen': scr,
                    'area': areas3d[0],
                    'region': region,
                    'scene': bpy.context.scene,
                    'workspace': bpy.context.workspace,
                    'space_data': space,
                    'region_data': region
                    }

        # we need a timer here to prevent operator recognizing tab event as exit
        bpy.app.timers.register(partial(WoWWMOLiquid._liquid_edit_mode_timer, override), first_interval=0.1)

    @staticmethod
    def _sculpt_mode(_: bpy.types.DepsgraphUpdate):
        for brush in bpy.data.brushes:
            brush.sculpt_plane = 'Z'

    __wbs_on_mode_handlers__ = {
        'EDIT': _edit_mode,
        'SCULPT': _sculpt_mode
    }


class WoWWMOPortal(CustomObject):
    __wbs_bl_object_type__ = 'MESH'
    __wbs_prop_group_id__ = 'wow_wmo_portal'
    __wbs_allowed_modes__ = {'EDIT'}
    __wbs_allow_modifiers__ = False
    __wbs_allow_mesh_properties__ = False
    __wbs_allow_particles__ = False
    __wbs_allow_physics__ = False

    @classmethod
    def match(cls, obj: bpy.types.Object) -> bool:
        return super().match(obj) \
            and any(match_id_name(col.name, 'Portals') for col in obj.users_collection)


class WoWWMOCollision(CustomObject):
    __wbs_bl_object_type__ = 'MESH'
    __wbs_prop_group_id__ = ''
    __wbs_allow_modifiers__ = True
    __wbs_allow_constraints__ = False
    __wbs_allow_material_properties__ = False
    __wbs_allow_particles__ = False
    __wbs_allow_physics__ = False

    @classmethod
    def match(cls, obj: bpy.types.Object) -> bool:
        return super().match(obj) \
          and any(match_id_name(col.name, 'Collision') for col in obj.users_collection)

    @classmethod
    def handle_object_if_matched(cls
                                 , update: bpy.types.DepsgraphUpdate) -> bool:
        obj: bpy.types.Object = update.id.original

        return cls.match(obj)


WMO_CUSTOM_OBJECT_TYPES = (
    WoWWMOGroup,
    WoWWMOFog,
    WoWWMOPortal,
    WoWWMOLight,
    WoWWMOLiquid,
    WoWWMOCollision,
    WoWWMODoodad
)
""" Tuple of all custom objects defined in this file. """
