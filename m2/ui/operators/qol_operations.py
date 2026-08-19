import bpy

class M2_OT_disable_drivers(bpy.types.Operator):
    bl_idname = 'scene.m2_ot_disable_drivers'
    bl_label = 'Disable Drivers'
    bl_description = "Disables drivers from materials so you can copy/paste them to other scenes"
    bl_options = {'REGISTER', 'UNDO_GROUPED'}

    def execute(self, context):
        for mat in bpy.data.materials:
            if mat.node_tree:
                nodes = mat.node_tree.nodes

                transparency_node = nodes.get("Transparency")
                color_node = nodes.get("Color")
                color_alpha_mix = nodes.get("Color_Alpha_Mix")

                if transparency_node:
                    input_socket = transparency_node.inputs[1]
                    if input_socket.is_linked:
                        continue

                    transp_driver_path = f'nodes["Transparency"].inputs[1].default_value'
                    transparency_node.label = transparency_node.label.replace("ON", "OFF")

                    if mat.node_tree.animation_data:
                        for driver in mat.node_tree.animation_data.drivers:
                            if driver.data_path == transp_driver_path:
                                try:
                                    transparency_node.inputs[1].driver_remove("default_value")
                                except TypeError as e:
                                    print(f"Error removing driver from Transparency node: {e}")
                                break

                # Handle Color Node
                if color_node:
                    color_driver_path = f'nodes["Color"].inputs[7].default_value'

                    if mat.node_tree.animation_data:
                        for driver in mat.node_tree.animation_data.drivers:
                            if driver.data_path == color_driver_path:
                                try:
                                    color_node.inputs[7].driver_remove("default_value")
                                except (TypeError, IndexError) as e:
                                    print(f"Error removing driver from Color node: {e}")
                                break

                    color_node.label = color_node.label.replace("ON", "OFF")

                # Handle Color_Alpha_Mix Node
                if color_alpha_mix:
                    input_socket = color_alpha_mix.inputs[1]
                    if input_socket.is_linked:
                        continue

                    col_alpha_driver_path = f'nodes["Color_Alpha_Mix"].inputs[1].default_value'
                    color_alpha_mix.label = color_alpha_mix.label.replace("ON", "OFF")

                    if mat.node_tree.animation_data:
                        for driver in mat.node_tree.animation_data.drivers:
                            if driver.data_path == col_alpha_driver_path:
                                try:
                                    color_alpha_mix.inputs[1].driver_remove("default_value")
                                except TypeError as e:
                                    print(f"Error removing driver from Color_Alpha_Mix node: {e}")
                                break

        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Drivers Disabled!", font_size=24, y_offset=67)      
        return {'FINISHED'}

class M2_OT_enable_drivers(bpy.types.Operator):
    bl_idname = 'scene.m2_ot_enable_drivers'
    bl_label = 'Enable Drivers'
    bl_description = "Enables drivers for materials after copying/pasting them to other scenes"
    bl_options = {'REGISTER', 'UNDO_GROUPED'}

    def execute(self, context):
        for mat in bpy.data.materials:
            if mat.node_tree:
                nodes = mat.node_tree.nodes
                transparency_node = nodes.get("Transparency")
                color_node = nodes.get("Color")
                color_alpha_mix = nodes.get("Color_Alpha_Mix")

                if transparency_node:
                    input_socket = transparency_node.inputs[1]
                    if input_socket.is_linked:
                        continue
                    driver_path = f'nodes["Transparency"].inputs[1].default_value'
                    
                    driver_exists = False
                    if mat.node_tree.animation_data:
                        for driver in mat.node_tree.animation_data.drivers:
                            if driver.data_path == driver_path:
                                driver_exists = True
                                break

                    if not driver_exists:
                        try:
                            driver = transparency_node.inputs[1].driver_add("default_value").driver
                            driver.type = 'SCRIPTED'
                            driver.expression= 'Transparency'
                            trans_name_var = driver.variables.new()
                            trans_name_var.name = 'Transparency'
                            trans_name_var.targets[0].id_type = 'SCENE'
                            trans_name_var.targets[0].id = bpy.context.scene
                            trans_name = mat.wow_m2_material.transparency
                            trans_index = int(''.join(filter(str.isdigit, trans_name)))
                            trans_name_var.targets[0].data_path = f'wow_m2_transparency[{trans_index}].value'
                            transparency_node.label = transparency_node.label.replace("OFF", "ON")
                        except Exception as e:
                            print(f"Error adding driver: {e}")

                color_name = mat.wow_m2_material.color

                if color_name != "":
                    color_index = int(''.join(filter(str.isdigit, color_name)))
                else:
                    color_index = 0

                if color_node:
                    color_components = ['R', 'G', 'B']
                    if color_node.inputs[0].default_value == 1.0:
                        color_node.label = color_node.label.replace("OFF", "ON")

                    for i, component in enumerate(color_components):
                        driver_path = f'nodes["Color"].inputs[7].default_value[{i}]'

                        driver_exists = False
                        if mat.node_tree.animation_data:
                            for driver in mat.node_tree.animation_data.drivers:
                                if driver.data_path == driver_path:
                                    driver_exists = True
                                    break

                        if not driver_exists:
                            try:
                                driver = color_node.inputs[7].driver_add("default_value", i).driver
                                driver.type = 'SCRIPTED'
                                driver.expression = f'{component}'
                                color_name_var = driver.variables.new()
                                color_name_var.name = f'{component}'
                                color_name_var.targets[0].id_type = 'SCENE'
                                color_name_var.targets[0].id = bpy.context.scene
                                color_name_var.targets[0].data_path = f'wow_m2_colors[{color_index}].color[{i}]'
                            except Exception as e:
                                print(f"Error adding driver to Color node ({component}): {e}")

                # Handle Color_Alpha_Mix Node
                if color_alpha_mix:
                    input_socket = color_alpha_mix.inputs[1]
                    if not input_socket.is_linked:
                        driver_path = f'nodes["Color_Alpha_Mix"].inputs[1].default_value'

                        driver_exists = False
                        if mat.node_tree.animation_data:
                            for driver in mat.node_tree.animation_data.drivers:
                                if driver.data_path == driver_path:
                                    driver_exists = True
                                    break

                        if not driver_exists:
                            try:
                                driver = color_alpha_mix.inputs[1].driver_add("default_value").driver
                                driver.type = 'SCRIPTED'
                                driver.expression = 'Alpha'
                                alpha_mix_name_var = driver.variables.new()
                                alpha_mix_name_var.name = 'Alpha'
                                alpha_mix_name_var.targets[0].id_type = 'SCENE'
                                alpha_mix_name_var.targets[0].id = bpy.context.scene
                                alpha_mix_name_var.targets[0].data_path = f'wow_m2_color_alpha[{color_index}].value'
                                color_alpha_mix.label = color_alpha_mix.label.replace("OFF", "ON")
                            except Exception as e:
                                print(f"Error adding driver to Color_Alpha_Mix node: {e}")


        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Drivers Enabled!", font_size=24, y_offset=67)                                  
        return {'FINISHED'}