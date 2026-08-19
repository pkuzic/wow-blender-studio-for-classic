import bpy
import io
import os
import bmesh
from .... import PACKAGE_NAME
from ....utils.misc import load_game_data
from ....pywowlib.blp import PNG2BLP
# from ....pywowlib.io_utils.types import *

from ....third_party.tqdm import tqdm

class M2_OT_select_entity(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_select_entity'
    bl_label = 'Select m2 entities'
    bl_description = 'Select all M2 entities of given type'
    bl_options = {'REGISTER', 'INTERNAL'}

    entity:  bpy.props.EnumProperty(
        name="Entity",
        description="Select M2 component entity objects",
        items=[
            ("wow_m2_geoset", "Geosets", ""),
            ("wow_m2_attachment", "Attachments", ""),
            ("wow_m2_event", "Events", ""),
            ("wow_m2_particle", "particles", ""),
            ("wow_m2_camera", "Cameras", ""),
            ("wow_m2_light", "Lights", ""),
            ("Collision", "Collision", ""),
            ("Skeleton", "Bones", "")
        ]
    )

    def execute(self, context):

        for obj in bpy.context.scene.objects:
            if obj.hide_get():
                continue

            if obj.type == 'MESH':
                if obj.wow_m2_geoset:
                    obj.select_set(True)

                    if obj.wow_m2_geoset.collision_mesh:
                        obj.wow_m2_geoset.select_set(True)

                elif self.entity not in ("wow_m2_light", "wow_m2_geoset", "Collision"):
                    if getattr(obj, self.entity):
                        obj.select_set(True)

            elif obj.type == 'LIGHT' and self.entity == "wow_m2_light":
                obj.select_set(True)

        return {'FINISHED'}