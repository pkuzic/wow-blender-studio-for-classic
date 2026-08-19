import bpy
import bmesh

from bpy.app.handlers import persistent
from .drivers import register as register_m2_driver_utils
from ...utils.misc import show_message_box, singleton

__reload_order_index__ = 0


@singleton
class DepsgraphLock:
    DEPSGRAPH_UPDATE_LOCK = False

    def __enter__(self):
        self.DEPSGRAPH_UPDATE_LOCK = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.DEPSGRAPH_UPDATE_LOCK = False


_obj_props = (
              ('wow_m2_geoset', 'geosets'),
              ('wow_m2_attachment', 'attachments'),
              ('wow_m2_event', 'events'),
              ('wow_m2_light', 'lights')
             )


def _remove_col_items(scene, col_name):
    col = getattr(scene.wow_m2_root_elements, col_name)
    for i, obj in enumerate(col):
        if obj.pointer and obj.pointer.name not in scene.objects:
            col.remove(i)
            break
    else:
        return

    _remove_col_items(scene, col_name)


@persistent
def live_update_materials(dummy):
    try:
        anim = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
        if anim.live_update:
            for mat in bpy.data.materials:
                if mat.wow_m2_material.live_update:
                    mat.invert_z = mat.invert_z
    except IndexError:
        pass


def _add_col_items(scene):
    for i, obj in enumerate(scene.objects):
        if obj.parent:
            for prop, col_name in _obj_props:
                if prop == 'wow_m2_light' and obj.type != 'LIGHT':
                    continue
                prop_group = getattr(obj, prop) if prop != 'wow_m2_light' else obj.data.wow_m2_light
                if prop_group.enabled:
                    col = getattr(scene.wow_m2_root_elements, col_name)
                    if col.find(obj.name) < 0:
                        slot = col.add()
                        slot.pointer = obj


@persistent
def load_handler(dummy):
    register_m2_driver_utils()


@persistent
def on_depsgraph_update(_):
    if DepsgraphLock().DEPSGRAPH_UPDATE_LOCK:
        return

    delete = False

    for update in bpy.context.view_layer.depsgraph.updates:

        try:
            if isinstance(update.id, bpy.types.Object) and update.id.type == 'MESH':
                if update.id.wow_m2_geoset.enabled:
                    obj = bpy.data.objects[update.id.name, update.id.library]
                    mesh = obj.data

                    if obj.mode == 'EDIT':
                        bm = bmesh.from_edit_mesh(mesh)

                        if bm.faces.active:

                            root_elements = bpy.context.scene.wow_m2_root_elements
                            mat_index_active = bm.faces.active.material_index

                            if mesh.materials:
                                mat_index = root_elements.materials.find(mesh.materials[mat_index_active].name)

                                if mat_index >= 0 and root_elements.cur_material != mat_index:

                                    with DepsgraphLock():
                                        root_elements.cur_material = mat_index

                    if update.is_updated_geometry:
                        group_entry = bpy.context.scene.wow_m2_root_elements.geosets.get(obj.name)

                        if group_entry:  # TODO: find out why there is a possible m2 group not in the list yet.
                            group_entry.export = True
                
                elif update.id.wow_m2_attachment.enabled:
                    obj = bpy.data.objects[update.id.name, update.id.library]

                    with DepsgraphLock():
                        # enforce object mode
                        if obj.mode != 'OBJECT':
                            bpy.context.view_layer.objects.active = obj
                            bpy.ops.object.mode_set(mode='OBJECT')

            elif isinstance(update.id, bpy.types.Scene):

                if bpy.context.view_layer.objects.active \
                and bpy.context.view_layer.objects.active.select_get():

                    # sync collection active items
                    act_obj = bpy.context.view_layer.objects.active

                    root_comps = bpy.context.scene.wow_m2_root_elements
                    if act_obj:
                        if act_obj.type == 'MESH':
                            if act_obj.wow_m2_geoset.enabled:
                                slot_idx = root_comps.geosets.find(act_obj.name)
                                root_comps.cur_geoset = slot_idx

                            elif act_obj.wow_m2_attachment.enabled:
                                slot_idx = root_comps.wow_m2_attachments.find(act_obj.name)
                                root_comps.cur_attachment = slot_idx

                            elif act_obj.wow_m2_event.enabled:
                                slot_idx = root_comps.wow_m2_events.find(act_obj.name)
                                root_comps.cur_event = slot_idx

                        elif act_obj.type == 'LAMP':
                            if act_obj.wow_m2_light.enabled:
                                slot_idx = root_comps.lights.find(act_obj.name)
                                root_comps.cur_light = slot_idx
                        

                # fill collections
                n_objs = len(bpy.context.scene.objects) -1 # -1 is to ignore base armature

                if n_objs == bpy.wbs_n_scene_objects:
                    continue

                if n_objs < bpy.wbs_n_scene_objects:
                    bpy.wbs_n_scene_objects = n_objs

                    _remove_col_items(bpy.context.scene, 'geosets')
                    _remove_col_items(bpy.context.scene, 'lights')
                    _remove_col_items(bpy.context.scene, 'events')
                    _remove_col_items(bpy.context.scene, 'attachments')

                else:
                    bpy.wbs_n_scene_objects = n_objs
                    _add_col_items(bpy.context.scene)

            elif isinstance(update.id, bpy.types.Material):

                mat = bpy.data.materials[update.id.name, update.id.library]

                if mat.wow_m2_material.enabled \
                and bpy.context.scene.wow_m2_root_elements.materials.find(mat.name) < 0:
                    mat.wow_m2_material.enabled = False
                    slot = bpy.context.scene.wow_m2_root_elements.materials.add()
                    slot.pointer = mat
            
            elif isinstance(update.id, bpy.types.Image):

                image = bpy.data.images[update.id.name, update.id.library]

                if image.wow_m2_texture.enabled \
                and bpy.context.scene.wow_m2_root_elements.textures.find(image.name) < 0:
                    image.wow_m2_texture.enabled = False
                    slot = bpy.context.scene.wow_m2_root_elements.textures.add()
                    slot.pointer = image

        finally:
            DepsgraphLock().DEPSGRAPH_UPDATE_LOCK = False


# def register():
#     bpy.wbs_n_scene_objects = 0
#     bpy.app.handlers.frame_change_pre.append(live_update_materials)
#     load_handler(None)
#     bpy.app.handlers.load_post.append(load_handler)
    
#     bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


# def unregister():
#     bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
#     del bpy.wbs_n_scene_objects
#     bpy.app.handlers.frame_change_pre.remove(live_update_materials)
#     bpy.app.handlers.load_post.remove(load_handler)
