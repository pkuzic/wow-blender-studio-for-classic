import bpy
import bmesh
import os

from ...bl_render import load_wmo_shader_dependencies, update_wmo_mat_node_tree
from ...utils.wmv import wmv_get_last_texture, wow_export_get_last_texture
from ....utils.misc import resolve_texture_path, resolve_outside_texture_path, load_game_data
from ...utils.materials import load_texture
from ....ui.preferences import get_project_preferences
from ...ui.handlers import DepsgraphLock
from ..custom_objects import WoWWMOGroup


class WMO_OT_generate_materials(bpy.types.Operator):
    bl_idname = "scene.wow_wmo_generate_materials"
    bl_label = "Generate WMO Materials"
    bl_description = "Generate WMO materials."
    bl_options = {'UNDO', 'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.scene.wow_scene.type == 'WMO'

    def execute(self, context):
        load_wmo_shader_dependencies()

        materials = []

        if context.selected_objects:
            for obj in context.selected_objects:
                if not WoWWMOGroup.match(obj):
                    continue

                materials.extend(obj.data.materials)

        for mat in materials:

            tex = None
            if mat.use_nodes:

                for node in mat.node_tree.nodes:
                    if node.bl_idname == 'ShaderNodeTexImage':
                        tex = node.image
                        break

            update_wmo_mat_node_tree(mat)

            with DepsgraphLock():

                # if context.scene.wow_wmo_root_elements.materials.find(mat.name) < 0:
                if bpy.data.materials.find(mat.name) < 0:
                    mat.wow_wmo_material.diff_texture_1 = tex

        return {'FINISHED'}


class WMO_OT_material_assign(bpy.types.Operator):
    bl_idname = "object.wow_wmo_material_assign"
    bl_label = "Assign WMO Material"
    bl_description = "Assign WMO material to selected faces."
    bl_options = {'UNDO', 'REGISTER', 'INTERNAL'}

    def execute(self, context):

        mesh = context.view_layer.objects.active.data
        bm = bmesh.from_edit_mesh(mesh)
        # mat = context.scene.wow_wmo_root_elements.materials[context.scene.wow_wmo_root_elements.cur_material]

        # TODO : cur material in new system?
        mat = bpy.data.materials[cur_material]

        # if not mat.pointer:
        #     self.report({'ERROR'}, "Cannot assign an empty material")
        #     return {'CANCELLED'}

        mat_index = mesh.materials.find(mat.name)

        if mat_index < 0:
            mat_index = len(mesh.materials)
            mesh.materials.append(mat)

        for face in bm.faces:
            if not face.select:
                continue

            face.material_index = mat_index

        bmesh.update_edit_mesh(mesh)

        return {'FINISHED'}


class WMO_OT_material_select(bpy.types.Operator):
    bl_idname = "object.wow_wmo_material_select"
    bl_label = "Select WMO Material"
    bl_description = "Select WMO material to selected faces."
    bl_options = {'UNDO', 'REGISTER', 'INTERNAL'}

    def execute(self, context):

        mesh = context.view_layer.objects.active.data
        bm = bmesh.from_edit_mesh(mesh)
        
        #mat = context.scene.wow_wmo_root_elements.materials[context.scene.wow_wmo_root_elements.cur_material]
        # TODO : cur material in new system
        mat = bpy.data.materials[cur_material]

        # if not mat.pointer:
        #     self.report({'ERROR'}, "Cannot select an empty material")
        #     return {'CANCELLED'}

        mat_index = mesh.materials.find(mat.name)

        for face in bm.faces:
            if face.material_index == mat_index:
                face.select = True

        bmesh.update_edit_mesh(mesh)

        return {'FINISHED'}


class WMO_OT_material_deselect(bpy.types.Operator):
    bl_idname = "object.wow_wmo_material_deselect"
    bl_label = "Deselect WMO Material"
    bl_description = "Deselect WMO material to selected faces."
    bl_options = {'UNDO', 'REGISTER', 'INTERNAL'}

    def execute(self, context):

        mesh = context.view_layer.objects.active.data
        bm = bmesh.from_edit_mesh(mesh)
        # mat = context.scene.wow_wmo_root_elements.materials[context.scene.wow_wmo_root_elements.cur_material]
        # TODO
        mat = bpy.data.materials[cur_material]
        # if not mat.pointer:
        #     self.report({'ERROR'}, "Cannot deselect an empty material")
        #     return {'CANCELLED'}

        mat_index = mesh.materials.find(mat.name)

        for face in bm.faces:
            if face.material_index == mat_index:
                face.select = False

        bmesh.update_edit_mesh(mesh)

        return {'FINISHED'}


class WMO_OT_fill_textures(bpy.types.Operator):
    bl_idname = 'scene.wow_fill_textures'
    bl_label = 'Fill textures'
    bl_description = "Fill Texture field of WoW materials with paths from applied image"
    bl_options = {'REGISTER'}

    def execute(self, context):

        for ob in filter(lambda o: WoWWMOGroup.match(o), bpy.context.selected_objects):
            mesh = ob.data
            for material in mesh.materials:
                if not WoWWMOGroup.match(ob) :
                    continue 
                

                texture1 = material.wow_wmo_material.diff_texture_1
                texture2 = material.wow_wmo_material.diff_texture_2   


                if not texture1 or texture1.type != 'IMAGE':
                    continue

                t1_resolved_path = resolve_texture_path(texture1.filepath)
                if t1_resolved_path is None:
                    t1_resolved_path = resolve_outside_texture_path(texture1.filepath)

                texture1.wow_wmo_texture.path = t1_resolved_path    

                if not texture2 or texture2.type != 'IMAGE':
                    continue                          
                
                if texture2 is not None:

                    t2_resolved_path = resolve_texture_path(texture2.filepath)
                    if t2_resolved_path is None:
                        t2_resolved_path = resolve_outside_texture_path(texture2.filepath)

                texture2.wow_wmo_texture.path = t2_resolved_path

        self.report({'INFO'}, "Done filling texture paths")

        return {'FINISHED'}


class WMO_OT_import_texture(bpy.types.Operator):
    bl_idname = "scene.wow_wmo_texture_import"
    bl_label = "Import WoW Texture"
    bl_description = "Import last texture from WoW Model Viewer as a WMO material.\n(Browse WMV in 'Images' mode, modeling textures are usualy in 'Dungeons' directory)"
    bl_options = {'UNDO', 'REGISTER'}

    def execute(self, context):

        project_preferences = get_project_preferences()
        game_data = load_game_data()

        if not game_data:
            self.report({'ERROR'}, "Importing texture failed. Game data was not loaded.")
            return {'CANCELLED'}
        
        if project_preferences.import_method == 'WMV':
            path = wmv_get_last_texture().capitalize()
        elif project_preferences.import_method == 'WowExport' or 'NoggitRed':
            path = wow_export_get_last_texture().capitalize()

        if not path:
            self.report({'ERROR'}, "WMV log does not contain any texture paths.")
            return {'CANCELLED'}

        game_data.extract_textures_as_png(project_preferences.cache_dir_path, (path,))
        texture = load_texture({}, path, project_preferences.cache_dir_path)

        mat = bpy.data.materials.new(name="T1_" + os.path.basename(path).replace('.blp', ''))
        mat.wow_wmo_material.diff_texture_1 = texture
        mat.wow_wmo_material.diff_color = (0.584314,0.584314,0.584314,1)
        mat.wow_wmo_material.emissive_color = (0,0,0,1)


        load_wmo_shader_dependencies()
        update_wmo_mat_node_tree(mat)

        print("Info: Successfully imported texture: " + mat.name)
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully imported texture: " + mat.name, font_size=24, y_offset=67)        

        return {'FINISHED'}