import bpy
from ..enums import *
from ...bl_render.cycles import update_m2_mat_node_tree_cycles
    
class TexturePathDefaultButton(bpy.types.Operator):
    bl_idname = "wow_m2_texture.set_default_texture"
    bl_label = "Set Default Texture Path"

    texture_index: bpy.props.IntProperty()

    def execute(self, context):
        default_texture_path = "textures\\ShaneCube.blp"
        if self.texture_index == 1:  
            context.material.wow_m2_material.texture_1.wow_m2_texture.path = default_texture_path
        elif self.texture_index == 2:
            context.material.wow_m2_material.texture_2.wow_m2_texture.path = default_texture_path    
        return {'FINISHED'}    
        
class TextureSlotPropertyGroup(bpy.types.PropertyGroup):
    texture_flags: bpy.props.EnumProperty(
        name="Texture flags",
        description="WoW M2 texture flags",
        items=TEXTURE_FLAGS,
        options={"ENUM_FLAG"},
        default={'1', '2'}
    )

    texture_type: bpy.props.EnumProperty(
        name="Texture type",
        description="WoW M2 texture type",
        items=TEXTURE_TYPES
    )
    
    path: bpy.props.StringProperty(
        name='Path',
        description='Path to .blp file in wow file system.'
    )   

class ToggleTexturesOperator(bpy.types.Operator):
    bl_idname = "object.toggle_textures"
    bl_label = "Toggle Textures"
    
    def execute(self, context):
        context.scene.show_textures = not context.scene.show_textures        
        return {'FINISHED'}
    
class ToggleRenderFlagsOperator(bpy.types.Operator):
    bl_idname = "object.toggle_render_flags"
    bl_label = "Toggle Render Flags"

    texture_index: bpy.props.IntProperty()
    
    def execute(self, context):
        if self.texture_index == 1:  
            context.scene.show_t1_render_flags = not context.scene.show_t1_render_flags
        elif self.texture_index == 2:  
            context.scene.show_t2_render_flags = not context.scene.show_t2_render_flags            
        return {'FINISHED'}

bpy.types.Scene.show_textures = bpy.props.BoolProperty(name="Show Textures", default=True)        
bpy.types.Scene.show_t1_render_flags = bpy.props.BoolProperty(name="Show Render Flags", default=False)    
bpy.types.Scene.show_t2_render_flags = bpy.props.BoolProperty(name="Show Render Flags", default=False)

class M2_PT_Duplicate_Image(bpy.types.Operator):
    bl_idname = "image.duplicate"
    bl_label = "Duplicate Texture"
    bl_description = "Duplicate Texture"
    bl_options = {'REGISTER', 'UNDO_GROUPED'}

    texture_index: bpy.props.IntProperty()

    def execute(self, context):
        material = context.material.wow_m2_material
        
        if self.texture_index == 1 and material.texture_1:
            new_image = material.texture_1.copy()
            new_image.name = material.texture_1.name + "_copy"
            material.texture_1 = new_image
        elif self.texture_index == 2 and material.texture_2:
            new_image = material.texture_2.copy()
            new_image.name = material.texture_2.name + "_copy"
            material.texture_2 = new_image
        else:
            self.report({'WARNING'}, "No image found to copy")
        
        update_material_name()
        
        return {'FINISHED'}

class M2_PT_material_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_label = "M2 Material"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text='Textures')
        col.operator("object.toggle_textures", text="Toggle Textures") 
        if context.scene.show_textures:
            col.separator()
            col.label(text='Texture 1')
            sub_col = col.column()
            row = sub_col.row()
            row.prop(context.material.wow_m2_material, "texture_1", text="")
            op = row.operator("image.duplicate", text="", icon='IMAGE_DATA')
            op.texture_index = 1

            if context.material.wow_m2_material.texture_1:
                col.prop(context.material.wow_m2_material.texture_1.wow_m2_texture, "flags")
                col.separator()
                col.prop(context.material.wow_m2_material.texture_1.wow_m2_texture, "texture_type")
                # only show path setting if texture type is hardcoded
                if context.material.wow_m2_material.texture_1.wow_m2_texture.texture_type == "0":
                    col.prop(context.material.wow_m2_material.texture_1.wow_m2_texture, "path", text='Path')
                    # Check if path is empty, then show the button
                    if len(context.material.wow_m2_material.texture_1.wow_m2_texture.path) == 0:
                        op = col.operator(TexturePathDefaultButton.bl_idname, text="Set Default Path", icon='FILEBROWSER') 
                        op.texture_index = 1
                col.separator()
                col.label(text='Blending')
                col.prop(context.material.wow_m2_material, "texture_1_blending_mode", text="")  
                to = col.operator("object.toggle_render_flags", text="Toggle Render Flags")  
                to.texture_index = 1        
                if context.scene.show_t1_render_flags:
                    col.separator()
                    col.label(text='Render Flags:')
                    box = col.box()
                    box.prop(context.material.wow_m2_material, "texture_1_render_flags", text="Texture 1 Render Flags", toggle=True)   
                col.separator()
                col.prop(context.material.wow_m2_material, "texture_1_mapping")
                sub_col = col.column()
                row = sub_col.row()
                row.prop(context.material.wow_m2_material, "texture_1_animation") 
                op = row.operator("scene.wow_m2_geoset_add_texture_transform", text='', icon='RNA_ADD') 
                op.channel = 1        

                col.separator()
                col.label(text='Texture 2')
                sub_col = col.column()
                row = sub_col.row()
                row.prop(context.material.wow_m2_material, "texture_2", text="")
                op = row.operator("image.duplicate", text="", icon='IMAGE_DATA')
                op.texture_index = 2

                if context.material.wow_m2_material.texture_2:
                    col.prop(context.material.wow_m2_material.texture_2.wow_m2_texture, "flags")
                    col.separator()
                    col.prop(context.material.wow_m2_material.texture_2.wow_m2_texture, "texture_type")
                    # only show path setting if texture type is hardcoded
                    if context.material.wow_m2_material.texture_2.wow_m2_texture.texture_type == "0":
                        col.prop(context.material.wow_m2_material.texture_2.wow_m2_texture, "path", text='Path')
                        if len(context.material.wow_m2_material.texture_2.wow_m2_texture.path) == 0:
                            op = col.operator(TexturePathDefaultButton.bl_idname, text="Set Default Path", icon='FILEBROWSER')    
                            op.texture_index = 2
                    col.separator()
                    col.label(text='Blending')
                    col.prop(context.material.wow_m2_material, "texture_2_blending_mode", text="")
                    to = col.operator("object.toggle_render_flags", text="Toggle Render Flags")  
                    to.texture_index = 2        
                    if context.scene.show_t2_render_flags:
                        col.separator()
                        col.label(text='Render Flags:')
                        box = col.box()
                        box.prop(context.material.wow_m2_material, "texture_2_render_flags", text="Texture 2 Render Flags", toggle=True)                     
                    col.separator()
                    col.prop(context.material.wow_m2_material, "texture_2_mapping")
                    sub_col = col.column()
                    row = sub_col.row()
                    row.prop(context.material.wow_m2_material, "texture_2_animation") 
                    op = row.operator("scene.wow_m2_geoset_add_texture_transform", text='', icon='RNA_ADD')  
                    op.channel = 2  
        
        col.separator()
        col.label(text='Flags:')
        col.prop(context.material.wow_m2_material, "flags")
        col.separator()
        col.label(text='Sorting control:')
        col.prop(context.material.wow_m2_material, "priority_plane")
        col.separator()
        col.prop_search(context.material.wow_m2_material, "color",
                        context.scene, "wow_m2_colors", text='Color', icon='COLOR')
        col.prop_search(context.material.wow_m2_material, "transparency",
                        context.scene, "wow_m2_transparency", text='Transparency', icon='RESTRICT_VIEW_OFF')

    @classmethod
    def poll(cls, context):
        return(context.scene is not None
               and context.scene.wow_scene.type == 'M2'
               and context.material is not None)
def mapping(mapping_method):
    if mapping_method == "UVMap":
        return 0.0
    elif mapping_method == "UVMap.001":
        return 1.0
    elif mapping_method == "Env":
        return -1.0      

def update_geoset_uv_transform_1(self, context):
    obj = context.object

    if obj != None and obj.active_material:
        c_obj = obj.active_material.wow_m2_material.texture_1_animation
        tex_1_mapping = obj.active_material.wow_m2_material.texture_1_mapping

        for node in obj.active_material.node_tree.nodes:
            if node.name == 'Tex1_Mapping':
                node.inputs[0].default_value = mapping(tex_1_mapping)
                break

        if c_obj:

            uv_transform_1 = context.object.modifiers.get('M2TexTransform_1')        
            
            if c_obj is not None:
                if c_obj.wow_m2_uv_transform is not None:
                    if not c_obj.wow_m2_uv_transform.enabled:
                        context.object.wow_m2_geoset.uv_transform = None

            if not uv_transform_1:
                bpy.ops.object.modifier_add(type='UV_WARP')
                uv_transform_1 = context.object.modifiers[-1]
                uv_transform_1.name = 'M2TexTransform_1'
                uv_transform_1.object_from = obj
                uv_transform_1.object_to = c_obj
                uv_transform_1.uv_layer = obj.active_material.wow_m2_material.texture_1_mapping
            else:
                uv_transform_1.object_to = c_obj
                uv_transform_1.uv_layer = obj.active_material.wow_m2_material.texture_1_mapping
        else:
            uv_transform_1 = context.object.modifiers.get('M2TexTransform_1')   
            if uv_transform_1 is not None and c_obj is None:
                context.object.modifiers.remove(uv_transform_1)

def update_geoset_uv_transform_2(self, context):
    obj = context.object

    if obj != None and obj.active_material:
        c_obj = obj.active_material.wow_m2_material.texture_2_animation
        tex_2_mapping = obj.active_material.wow_m2_material.texture_2_mapping

        for node in obj.active_material.node_tree.nodes:
            if node.name == 'Tex2_Mapping':
                node.inputs[0].default_value = mapping(tex_2_mapping)
                break
        
        if c_obj:

            uv_transform_2 = context.object.modifiers.get('M2TexTransform_2')

            if c_obj is not None:
                if c_obj.wow_m2_uv_transform is not None:
                    if not c_obj.wow_m2_uv_transform.enabled:
                        context.object.wow_m2_geoset.uv_transform = None

            if not uv_transform_2:
                bpy.ops.object.modifier_add(type='UV_WARP')
                uv_transform_2 = context.object.modifiers[-1]
                uv_transform_2.name = 'M2TexTransform_2'
                uv_transform_2.object_from = obj
                uv_transform_2.object_to = c_obj
                uv_transform_2.uv_layer = obj.active_material.wow_m2_material.texture_2_mapping
            else:
                uv_transform_2.object_to = c_obj
                uv_transform_2.uv_layer = obj.active_material.wow_m2_material.texture_2_mapping
        else:
            uv_transform_2 = context.object.modifiers.get('M2TexTransform_2')   
            if uv_transform_2 is not None and c_obj is None:
                context.object.modifiers.remove(uv_transform_2)          

def update_material_texture(self, context):
    obj = context.object

    if obj != None and obj.active_material:
        tex_1 = obj.active_material.wow_m2_material.texture_1
        tex_2 = obj.active_material.wow_m2_material.texture_2
        
        for node in obj.active_material.node_tree.nodes:
            if node.name == 'Tex1_image':
                tex1_image = node
                tex1_image.image = tex_1
            if node.name == 'Tex2_image':
                tex2_image = node
                tex2_image.image = tex_2
            if node.name == 'Blending':
                tex_mix = node
            if node.name == 'Alpha_Blending':
                tex_alpha_mix = node
            if node.name == 'Color':
                c_mix = node
            if node.name == 'Transparency':
                t_mix = node
        
        if tex_mix and tex1_image and c_mix:
            tree = obj.active_material.node_tree
            links = tree.links

            if tex_2:
                links.new(tex_mix.outputs[2], c_mix.inputs[6])   
                links.new(tex_alpha_mix.outputs[2], t_mix.inputs[0]) 
            else:
                links.new(tex1_image.outputs[0], c_mix.inputs[6])
                links.new(tex1_image.outputs[1], t_mix.inputs[0]) 
                       

        update_material_name()    

BLENDING_MODES_DICT = {
    "0": "Opaque",
    "1": "AlphaKey",
    "2": "Alpha",
    "3": "NoAlphaAdd",
    "4": "Add",
    "5": "Mod",
    "6": "Mod2X",
    "7": "BlendAdd"
}

def update_material_name():
    obj = bpy.context.object

    if obj is not None and obj.active_material:

        tex_1 = obj.active_material.wow_m2_material.texture_1
        tex_2 = obj.active_material.wow_m2_material.texture_2
        tex_1_name = None
        tex_2_name = None

        if tex_1 is not None:
            tex_1_name = str(tex_1.name).replace('.png', '')
        if tex_2 is not None:
            tex_2_name = str(tex_2.name).replace('.png', '')

        texture_1_blending_mode = obj.active_material.wow_m2_material.texture_1_blending_mode
        texture_2_blending_mode = obj.active_material.wow_m2_material.texture_2_blending_mode
 
        texture_1_blending_mode_name = BLENDING_MODES_DICT.get(str(texture_1_blending_mode), "Unknown")
        texture_2_blending_mode_name = BLENDING_MODES_DICT.get(str(texture_2_blending_mode), "Unknown")

        if tex_1_name:
            if tex_2_name:
                obj.active_material.name = 'T1_{}_({})_T2_{}_({})'.format(
                    tex_1_name, texture_1_blending_mode_name, tex_2_name, texture_2_blending_mode_name
                )
            else:
                obj.active_material.name = 'T1_{}_({})'.format(
                    tex_1_name, texture_1_blending_mode_name
                )        

def update_transparency(self, context):
    obj = context.object

    if obj != None and obj.active_material:
            
        transparency_node = obj.active_material.node_tree.nodes.get('Transparency')

        if transparency_node:

            trans_name = obj.active_material.wow_m2_material.transparency
            trans_index = int(''.join(filter(str.isdigit, trans_name)))                    
            transparency_node.label = f'Transparency_{trans_index}_OFF'

            for driver in transparency_node.id_data.animation_data.drivers:
                if driver.data_path == 'nodes["Transparency"].inputs[1].default_value':
                    existing_driver = driver.driver
                    
                    for var in existing_driver.variables:
                        if var.name == 'Transparency':
                            transparency_var = var.targets[0]
                                                            
                            transparency_var.data_path = f'wow_m2_transparency[{trans_index}].value'
                            transparency_node.label = f'Transparency_{trans_index}_ON'

def update_color(self, context):
    obj = context.object

    if obj != None and obj.active_material:

        mat = obj.active_material
            
        color_node = mat.node_tree.nodes.get('Color')
        color_alpha_mix = mat.node_tree.nodes.get("Color_Alpha_Mix")
        transparency_node = mat.node_tree.nodes.get("Transparency")
        bsdf = mat.node_tree.nodes.get("BSDF")

        tree = mat.node_tree
        links = tree.links

        color_name = mat.wow_m2_material.color

        if color_name != "":
            color_index = int(''.join(filter(str.isdigit, color_name)))  
            active_color = True    
        else:
            color_index = 0
            active_color = False

        if color_node:
            color_components = ['R', 'G', 'B']
            for i, component in enumerate(color_components):
                for driver in mat.node_tree.animation_data.drivers:
                    if driver.data_path == f'nodes["Color"].inputs[7].default_value':
                        existing_driver = driver.driver
                        
                        for var in existing_driver.variables:
                            if var.name == component:
                                color_var = var.targets[0]                     
                                color_var.data_path = f'wow_m2_colors[{color_index}].color[{i}]'

            if active_color:
                color_node.inputs[0].default_value = 1.0
                color_node.label = f'Color_{color_index}_ON'
            else:
                color_node.inputs[0].default_value = 0.0
                color_node.label = f'Color_{color_index}_OFF'

        if color_alpha_mix:
            for driver in mat.node_tree.animation_data.drivers:
                if driver.data_path == f'nodes["Color_Alpha_Mix"].inputs[1].default_value':
                    existing_driver = driver.driver
                 
                    for var in existing_driver.variables:
                        if var.name == "Alpha":
                            color_var = var.targets[0]                     
                            color_var.data_path = f'wow_m2_color_alpha[{color_index}].value'      

            if transparency_node and bsdf:
                if active_color:
                    color_alpha_mix.label = f'Color_{color_index}_ON'
                    links.new(color_alpha_mix.inputs['Value'], transparency_node.outputs['Value'])
                    links.new(color_alpha_mix.outputs['Value'], bsdf.inputs['Alpha'])
                else:
                    color_alpha_mix.label = f'Color_{color_index}_OFF'
                    links.new(transparency_node.outputs['Value'], bsdf.inputs['Alpha']) 

def update_blending(self, context):
    obj = context.object

    if obj != None and obj.active_material and obj.active_material.wow_m2_material:

        blending_1 = int(obj.active_material.wow_m2_material.texture_1_blending_mode)
        blending_2 = int(obj.active_material.wow_m2_material.texture_2_blending_mode)

        for node in obj.active_material.node_tree.nodes:
            if node.name == 'Tex1_image':
                tex1_image = node
            if node.name == 'Blending':
                tex_mix = node
            if node.name == 'Color':
                c_mix = node
        
        if tex_mix and tex1_image and c_mix:
            tree = obj.active_material.node_tree
            links = tree.links

            tex_2 = obj.active_material.wow_m2_material.texture_2

            if tex_2:
                links.new(tex_mix.outputs[2], c_mix.inputs[6])    
            else:
                links.new(tex1_image.outputs[0], c_mix.inputs[6])
            
            if blending_2 in [1, 2]:
                tex_mix.blend_type = 'MIX'
            elif blending_2 == 4:
                tex_mix.blend_type = 'OVERLAY'
            elif blending_2 == 5:
                tex_mix.blend_type = 'MULTIPLY'                

        # Alpha_mode = obj.active_material.node_tree.nodes.get('Tex1_image')

        # if blending_1 in [1, 2, 4, 5, 6]:
        #     Alpha_mode.image.alpha_mode = 'CHANNEL_PACKED'
        # else:
        #     Alpha_mode.image.alpha_mode = 'NONE'
 
        update_material_name()

class WowM2MaterialPropertyGroup(bpy.types.PropertyGroup):
    
    enabled:  bpy.props.BoolProperty()

    flags:  bpy.props.EnumProperty(
        name="Material flags",
        description="WoW  M2 material flags",
        items=TEX_UNIT_FLAGS,
        options={"ENUM_FLAG"}
        )

    texture_1_render_flags:  bpy.props.EnumProperty(
        name="Render flags",
        description="WoW  M2 render flags",
        items=RENDER_FLAGS,
        options={"ENUM_FLAG"}
        )
    
    texture_1_animation:  bpy.props.PointerProperty(
        name="UV Transform",
        description="WoW  M2 texture 1 animation",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.wow_m2_uv_transform.enabled,
        update=update_geoset_uv_transform_1
    )

    texture_2_animation:  bpy.props.PointerProperty(
        name="UV Transform",
        description="WoW  M2 texture 2 animation",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.wow_m2_uv_transform.enabled,
        update=update_geoset_uv_transform_2
    )      
    
    texture_2_render_flags:  bpy.props.EnumProperty(
        name="Render flags",
        description="WoW  M2 render flags",
        items=RENDER_FLAGS,
        options={"ENUM_FLAG"}
        )    

    vertex_shader:  bpy.props.EnumProperty(
        items=VERTEX_SHADERS,
        name="Vertex Shader",
        description="WoW vertex shader assigned to this material",
        default='0'
        )

    fragment_shader:  bpy.props.EnumProperty(
        items=FRAGMENT_SHADERS,
        name="Fragment Shader",
        description="WoW fragment shader assigned to this material",
        default='0'
        )

    shader: bpy.props.IntProperty(
        name='Shader'
        )

    texture_1_blending_mode:  bpy.props.EnumProperty(
        items=BLENDING_MODES,
        name="Blending",
        description="WoW material blending mode",
        update=update_blending
        )
    
    texture_2_blending_mode:  bpy.props.EnumProperty(
        items=BLENDING_MODES,
        name="Blending",
        description="WoW material blending mode",
        update=update_blending
        )        

    texture_1_mapping: bpy.props.EnumProperty(
        items=TEXTURE_MAPPING,
        name="Mapping",
        description="Select the mapping for Texture 1",
        default='UVMap',
        update=update_geoset_uv_transform_1
    )

    texture_2_mapping: bpy.props.EnumProperty(
        items=TEXTURE_MAPPING,
        name="Mapping",
        description="Select the mapping for Texture 2",
        default='UVMap.001',
        update=update_geoset_uv_transform_2
    )  

    texture_1: bpy.props.PointerProperty(
        type=bpy.types.Image,
        update=update_material_texture
    )

    texture_2: bpy.props.PointerProperty(
        type=bpy.types.Image,
        update=update_material_texture
    )

    #Removed layer, we can calculate it on export by material index
    # layer: bpy.props.IntProperty(
    #     min=0,
    #     max=7
    # )  

    priority_plane: bpy.props.IntProperty(
        min=-127,
        max=127,
        default=0
    )

    color: bpy.props.StringProperty(
        name='Color',
        description='Color track linked to this texture.',
        update=update_color
    )

    transparency: bpy.props.StringProperty(
        name='Transparency',
        description='Transparency track linked to this texture.',
        update=update_transparency
    )

    self_pointer: bpy.props.PointerProperty(type=bpy.types.Material)

def get_animations(self, context):
    global_seqs = []
    for i, anim in enumerate(context.scene.wow_m2_animations):
        if anim.is_global_sequence:
            identifier = str(i)
            name = anim.name
            description = f"Global sequence {i}"

            global_seqs.append((identifier, name, description))

    return global_seqs

class M2_OT_add_texture_transform(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_geoset_add_texture_transform'
    bl_label = 'Add Texture Animation (UV) Controller'
    bl_description = 'Add an M2 TT_Controller object to the scene'
    bl_options = {'REGISTER', 'UNDO_GROUPED', 'INTERNAL'}

    anim_index:  bpy.props.IntProperty()
    channel:  bpy.props.IntProperty(min=1, max=2)    

    frame_end: bpy.props.IntProperty(
        name="Final frame",
        default=100,
        min=1
    )

    x_value:  bpy.props.IntProperty(
        description='Final Texture Transform value, -1 or 1 = full UV loop',
        default=1,
        min = -10,
        max = 10,
    ) 

    y_value:  bpy.props.IntProperty(
        description='Final Texture Transform value, -1 or 1 = full UV loop',
        default=1,
        min = -10,
        max = 10,
    )          

    data_path:  bpy.props.EnumProperty(
        description='Choose type of animation',
        items=[('location', 'Location', 'Location'),
            ('rotation_quaternion', 'Rotation', 'Rotation'),
            ('scale', 'Scale', 'Scale')],
        default='location'
    )

    sequence:  bpy.props.EnumProperty(
        description='Choose type of animation',
        items=get_animations
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "data_path", text="L/R/S")
        layout.prop(self, "x_value", text="X Value")
        layout.prop(self, "y_value", text="Y Value")
        layout.prop(self, "frame_end", text="Final Frame")
        layout.prop(self, "sequence", text="Choose Global Sequence")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)
    
    def execute(self, context):

        mat_obj = context.object

        #Create TT_Controller
        bpy.ops.object.empty_add(type='SINGLE_ARROW', location=(0, 0, 0))
        TT_Controllers = [obj for obj in bpy.data.objects if obj.wow_m2_uv_transform.enabled]
        obj = bpy.context.view_layer.objects.active
        obj.name = "TT_Controller_{}".format(len(TT_Controllers))
        obj.wow_m2_uv_transform.enabled = True
        obj.rotation_mode = 'QUATERNION'
        obj.empty_display_size = 0.5
        
        #Animate TT_Controller
        obj.animation_data_create()
        obj.animation_data.action_blend_type = 'ADD'

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = obj
        action_name = ('TT_{}_{}_Custom'.format(len(TT_Controllers), obj.name))
        action = bpy.data.actions.new(name=action_name)
        obj.animation_data.action = action
        frame_start = 0
        frame_end = self.frame_end

        fcurve_x = action.fcurves.new(data_path=self.data_path, index=0, action_group=obj.name)
        fcurve_y = action.fcurves.new(data_path=self.data_path, index=1, action_group=obj.name)
        fcurve_z = action.fcurves.new(data_path=self.data_path, index=2, action_group=obj.name)
        fcurve_x.keyframe_points.insert(frame_start, 0)
        fcurve_y.keyframe_points.insert(frame_start, 0)
        fcurve_z.keyframe_points.insert(frame_start, 0)      
        fcurve_x.keyframe_points.insert(frame_end, self.x_value) 
        fcurve_y.keyframe_points.insert(frame_end, self.y_value) 
        fcurve_z.keyframe_points.insert(frame_end, 0) 

        for fcurve in [fcurve_x, fcurve_y, fcurve_z]:
            for keyframe_point in fcurve.keyframe_points:
                keyframe_point.interpolation = 'LINEAR'        

        #Add TT_Controller to Global Sequence
        index = context.scene.wow_m2_cur_anim_index = int(self.sequence)
        pairs = 0
        for pair in bpy.data.scenes["Scene"].wow_m2_animations[index].anim_pairs:
            pairs += 1

        bpy.ops.scene.wow_m2_animation_editor_object_add()
        bpy.data.scenes["Scene"].wow_m2_animations[index].anim_pairs[pairs].object = obj
        bpy.data.scenes["Scene"].wow_m2_animations[index].anim_pairs[pairs].action = action

        #Add TT_Controller to material
        if self.channel == 1:
            mat_obj.active_material.wow_m2_material.texture_1_animation = obj
        else:
            mat_obj.active_material.wow_m2_material.texture_2_animation = obj

        bpy.context.view_layer.objects.active = mat_obj    

        self.report({'INFO'}, "Successfully created M2 Texture Animation: " + obj.name + "\n")

        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully created M2 Texture Animation", font_size=24, y_offset=67)      
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message=f"If you want to edit it, select: {obj.name}  along with this action: {action_name}", font_size=16, y_offset=100)           

        return {'FINISHED'}
    
def menu_func(self, context):
    self.layout.operator(M2_OT_add_texture_transform.bl_idname)    
        
def register():
    bpy.utils.register_class(TexturePathDefaultButton)
    bpy.types.Material.wow_m2_material = bpy.props.PointerProperty(type=WowM2MaterialPropertyGroup)

def unregister():
    bpy.utils.unregister_class(TexturePathDefaultButton)
    del bpy.types.Material.wow_m2_material
