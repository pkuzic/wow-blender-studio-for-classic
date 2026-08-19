import bpy

from ....utils.node_builder import NodeTreeBuilder

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

def update_material_name(materials):

    for material in materials:

        tex_1 = material.wow_m2_material.texture_1
        tex_2 = material.wow_m2_material.texture_2
        tex_1_name = None
        tex_2_name = None

        if tex_1 is not None:
            tex_1_name = str(tex_1.name).replace('.png', '')
        if tex_2 is not None:
            tex_2_name = str(tex_2.name).replace('.png', '')

        texture_1_blending_mode = material.wow_m2_material.texture_1_blending_mode
        texture_2_blending_mode = material.wow_m2_material.texture_2_blending_mode
 
        texture_1_blending_mode_name = BLENDING_MODES_DICT.get(str(texture_1_blending_mode), "Unknown")
        texture_2_blending_mode_name = BLENDING_MODES_DICT.get(str(texture_2_blending_mode), "Unknown")

        if tex_1_name:
            if tex_2_name:
                material.name = 'T1_{}_({})_T2_{}_({})'.format(
                    tex_1_name, texture_1_blending_mode_name, tex_2_name, texture_2_blending_mode_name
                )
            else:
                material.name = 'T1_{}_({})'.format(
                    tex_1_name, texture_1_blending_mode_name
                )
                
def update_m2_mat_node_tree_cycles(bl_mat):

    # get textures
    img_1 = bl_mat.wow_m2_material.texture_1 if bl_mat.wow_m2_material.texture_1 else None
    img_2 = bl_mat.wow_m2_material.texture_2 if bl_mat.wow_m2_material.texture_2 else None

    def mapping(mapping_method):
        if mapping_method == "UVMap":
            return 0
        elif mapping_method == "UVMap.001":
            return 1
        elif mapping_method == "Env":
            return -1  
            
    tex1_uv = mapping(bl_mat.wow_m2_material.texture_1_mapping) if bl_mat.wow_m2_material.texture_1_mapping else 0
    tex2_uv = mapping(bl_mat.wow_m2_material.texture_2_mapping) if bl_mat.wow_m2_material.texture_2_mapping else 1

    bl_mat.use_nodes = True

    tree = bl_mat.node_tree
    links = tree.links
    tree_builder = NodeTreeBuilder(tree)

    uv_picker_node = bpy.data.node_groups.get("UV Picker")

    uvmap = tree_builder.add_node('ShaderNodeGroup', 'Tex1_Mapping', 0, 0)
    uvmap2 = tree_builder.add_node('ShaderNodeGroup', 'Tex2_Mapping', 0, 1)

    uvmap.node_tree = uv_picker_node
    uvmap2.node_tree = uv_picker_node

    uvmap.inputs[0].default_value= tex1_uv
    uvmap2.inputs[0].default_value = tex2_uv

    bsdf = tree_builder.add_node('ShaderNodeBsdfPrincipled', 'BSDF', 5, 0)
    bsdf.name = 'BSDF'
    tex_image = tree_builder.add_node('ShaderNodeTexImage', 'Tex1_image', 1, 0)
    tex_image2 = tree_builder.add_node('ShaderNodeTexImage', 'Tex2_image', 1, 1)

    if img_1:
        tex_image.image = img_1

    if img_2:
        tex_image2.image = img_2

    bsdf.inputs['Specular'].default_value = 0.0
    links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
    links.new(uvmap.outputs['Result'], tex_image.inputs['Vector'])
    links.new(uvmap2.outputs['Result'], tex_image2.inputs['Vector'])

    output = tree_builder.add_node("ShaderNodeOutputMaterial", 'Material Output', 6, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    alpha_invert = tree_builder.add_node('ShaderNodeInvert', 'Alpha Invert', 2, 0)
    alpha_invert.inputs[0].default_value = 1.0
    links.new(alpha_invert.inputs[1], tex_image.outputs['Alpha'])

    alpha_invert2 = tree_builder.add_node('ShaderNodeInvert', 'Alpha Invert 2', 2, 1)
    alpha_invert2.inputs[0].default_value = 1.0
    links.new(alpha_invert2.inputs[1], tex_image2.outputs['Alpha'])

    tex_mix = tree_builder.add_node('ShaderNodeMix', 'Blending', 3, 0)
    tex_mix.data_type = 'RGBA'
    tex_mix.inputs[0].default_value = 0.2
    tex_mix.blend_type = 'OVERLAY'
    links.new(tex_mix.inputs[0], alpha_invert.outputs['Color'])
    links.new(tex_mix.inputs[6], tex_image.outputs['Color'])
    links.new(tex_mix.inputs[7], tex_image2.outputs['Color'])


    tex_alpha_mix = tree_builder.add_node('ShaderNodeMix', 'Alpha_Blending', 3, 1)
    tex_alpha_mix.data_type = 'RGBA'
    tex_alpha_mix.blend_type = 'SUBTRACT'
    links.new(tex_alpha_mix.inputs[0], alpha_invert2.outputs['Color'])
    links.new(tex_alpha_mix.inputs[6], tex_image.outputs['Alpha'])
    links.new(tex_alpha_mix.inputs[7], tex_image.outputs['Alpha'])

    
    if '4' in bl_mat.wow_m2_material.texture_1_render_flags:
        bl_mat.use_backface_culling = False
    else:
        bl_mat.use_backface_culling = True
    
    if img_2:
        if '4' in bl_mat.wow_m2_material.texture_2_render_flags or '4' in bl_mat.wow_m2_material.texture_1_render_flags:
            bl_mat.use_backface_culling = False
        else:
            bl_mat.use_backface_culling = True

    if bl_mat.wow_m2_material.texture_1_blending_mode == '0':
        links.new(bsdf.inputs['Alpha'], tex_image.outputs['Alpha'])
        links.new(uvmap.outputs['Result'], tex_image.inputs['Vector'])
        bl_mat.blend_method = 'OPAQUE'
        bl_mat.show_transparent_back = False

    if bl_mat.wow_m2_material.texture_1_blending_mode == '1':
        links.new(bsdf.inputs['Alpha'], tex_image.outputs['Alpha'])
        links.new(uvmap.outputs['Result'], tex_image.inputs['Vector'])
        bl_mat.blend_method = 'CLIP'
        bl_mat.alpha_threshold = 0.878431

    if bl_mat.wow_m2_material.texture_1_blending_mode == '2' or bl_mat.wow_m2_material.texture_1_blending_mode == '4':
        links.new(bsdf.inputs['Alpha'], tex_image.outputs['Alpha'])
        links.new(uvmap.outputs['Result'], tex_image.inputs['Vector'])
        bl_mat.blend_method = 'BLEND'

    # Opaque settings
    blending_1 = int(bl_mat.wow_m2_material.texture_1_blending_mode)
    tex_image.image.alpha_mode = 'CHANNEL_PACKED'
    # if blending_1 in [1, 2, 4, 5, 6]:
    #     tex_image.image.alpha_mode = 'CHANNEL_PACKED'
    # else:
    #     tex_image.image.alpha_mode = 'NONE'

    # transparency
    t_mult = tree_builder.add_node('ShaderNodeMath', 'Transparency', 4, 1)
    t_mult.operation = 'MULTIPLY'
    t_mult.name = 'Transparency'
    t_mult.inputs[1].default_value = 1.0

    transparency_curve = bl_mat.node_tree.driver_add("nodes[\"Transparency\"].inputs[1].default_value")
    driver = transparency_curve.driver
    driver.type = 'SCRIPTED'


    trans_name_var = driver.variables.new()
    trans_name_var.name = 'Transparency'
    trans_name_var.targets[0].id_type = 'SCENE'
    trans_name_var.targets[0].id = bpy.context.scene
    
    trans_name = bl_mat.wow_m2_material.transparency

    trans_index = int(''.join(filter(str.isdigit, trans_name)))
    trans_name_var.targets[0].data_path = f'wow_m2_transparency[{trans_index}].value'

    t_mult.label = f'Transparency_{trans_index}_ON'
    
    driver.expression = trans_name_var.name

 

    # color
    c_mix = tree_builder.add_node('ShaderNodeMix', 'Color', 4, 0)
    c_mix.blend_type = 'MULTIPLY'
    c_mix.data_type = 'RGBA'
    c_mix.name = 'Color'
    c_mix.inputs[7].default_value = (1.0, 1.0, 1.0, 1.0)

    #color_alpha
    c_alpha = tree_builder.add_node('ShaderNodeMath', 'Color_Alpha_Mix', 4, 2)
    c_alpha.operation = 'MULTIPLY'
    c_alpha.name = 'Color_Alpha_Mix'
    c_alpha.inputs[1].default_value = 1.0

    #Color_Driver
    color_components = ['R', 'G', 'B']

    color_name = bl_mat.wow_m2_material.color

    if color_name != "":
        color_index = int(''.join(filter(str.isdigit, color_name)))
        c_mix.label = f'Color_{color_index}_ON'
        c_mix.inputs[0].default_value = 1.0

        c_alpha.label = f'Color_{color_index}_Alpha_ON'
    else:
        color_index = 0
        c_mix.label = f'Color_{0}_OFF'
        c_mix.inputs[0].default_value = 0.0

        c_alpha.label = f'Color_{0}_Alpha_OFF'

    for i, component in enumerate(color_components):
        color_curve = bl_mat.node_tree.driver_add(f"nodes[\"Color\"].inputs[7].default_value", i)
        c_driver = color_curve.driver
        c_driver.type = 'SCRIPTED'
        c_driver.expression = f'{component}'

        color_name_var = c_driver.variables.new()
        color_name_var.name = f'{component}'
        color_name_var.targets[0].id_type = 'SCENE'
        color_name_var.targets[0].id = bpy.context.scene
        color_name_var.targets[0].data_path = f'wow_m2_colors[{color_index}].color[{i}]'
    
    color_alpha_curve = bl_mat.node_tree.driver_add(f"nodes[\"Color_Alpha_Mix\"].inputs[1].default_value")
    color_a_driver = color_alpha_curve.driver
    color_a_driver.type = 'SCRIPTED'
    color_a_driver.expression = 'Alpha'

    color_alpha_var = color_a_driver.variables.new()
    color_alpha_var.name = 'Alpha'
    color_alpha_var.targets[0].id_type = 'SCENE'
    color_alpha_var.targets[0].id = bpy.context.scene
    color_alpha_var.targets[0].data_path = f'wow_m2_color_alpha[{color_index}].value'
    
    if color_name != "":
        links.new(c_alpha.inputs['Value'], t_mult.outputs['Value'])
        links.new(c_alpha.outputs['Value'], bsdf.inputs['Alpha'])
    else:
        links.new(t_mult.outputs['Value'], bsdf.inputs['Alpha']) 

    
    if not img_2:
        links.new(tex_image.outputs[0], c_mix.inputs[6])
        links.new(tex_image.outputs['Alpha'], t_mult.inputs['Value'])
    else:
        links.new(tex_mix.outputs[2], c_mix.inputs[6])
        links.new(tex_alpha_mix.outputs[2], t_mult.inputs['Value'])


    links.new(bsdf.inputs['Base Color'], c_mix.outputs[2])