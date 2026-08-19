import bpy
from ....wmo.utils.materials import load_texture
from ....wmo.utils.wmv import wmv_get_last_texture, wow_export_get_last_texture
from ....ui.preferences import get_project_preferences
from ....utils.misc import load_game_data, resolve_outside_texture_path, resolve_texture_path

class M2_fill_textures(bpy.types.Operator):
    bl_idname = 'scene.m2_fill_textures'
    bl_label = 'Fill textures'
    bl_description = "Fill Textures fields of WoW materials with paths from applied image"
    bl_options = {'REGISTER', 'UNDO_GROUPED'}

    def execute(self, context):

        for ob in bpy.context.selected_objects:
            
            mesh = ob.data

            if mesh is None and ob.wow_m2_particle.enabled:
                texture = ob.wow_m2_particle.texture
                resolved_path = resolve_texture_path(texture.filepath)
                if resolved_path is None:
                    resolved_path = resolve_outside_texture_path(texture.filepath)

                texture.wow_m2_texture.path = resolved_path                
            else:
                for material in mesh.materials:
                    if material.wow_m2_material.texture_1:
                        texture = material.wow_m2_material.texture_1
                    
                        resolved_path = resolve_texture_path(texture.filepath)
                        if resolved_path is None:
                            resolved_path = resolve_outside_texture_path(texture.filepath)

                        texture.wow_m2_texture.path = resolved_path

                    if material.wow_m2_material.texture_2:
                        texture2 = material.wow_m2_material.texture_2

                        resolved_path = resolve_texture_path(texture2.filepath)
                        if resolved_path is None:
                            resolved_path = resolve_outside_texture_path(texture2.filepath)

                        texture2.wow_m2_texture.path = resolved_path    

        
        self.report({'INFO'}, "Done filling texture paths")
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Done filling texture paths!", font_size=24, y_offset=67)      

        return {'FINISHED'}

class M2_OT_import_texture(bpy.types.Operator):
    bl_idname = "scene.wow_m2_texture_import"
    bl_label = "Import WoW Texture"
    bl_description = "Import last texture from Import Method as a M2 material."
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
            self.report({'ERROR'}, "Log does not contain any texture paths.")
            return {'CANCELLED'}

        game_data.extract_textures_as_png(project_preferences.cache_dir_path, (path,))
        texture = load_texture({}, path, project_preferences.cache_dir_path)


        print("Info: Successfully imported texture: " + texture.name)
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully imported texture: " + texture.name, font_size=24, y_offset=67)        

        return {'FINISHED'}