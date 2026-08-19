import bpy

class M2_UL_color_alpha_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):
        self.use_filter_show = False

        if self.layout_type in {'DEFAULT', 'COMPACT'}:

            row = layout.row(align=True)
            cur_color_alpha_prop_group = context.scene.wow_m2_color_alpha[index]
            row.prop(cur_color_alpha_prop_group, "name", text="", icon='RESTRICT_VIEW_OFF', emboss=False)
            row.prop(cur_color_alpha_prop_group, "value", text="")

        elif self.layout_type in {'GRID'}:
            pass


class M2_OT_color_alpha_value_add(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_color_alpha_add_value'
    bl_label = 'Add WoW color alpha'
    bl_description = 'Add WoW color alpha'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        value = context.scene.wow_m2_color_alpha.add()
        context.scene.wow_m2_cur_color_alpha_index = len(context.scene.wow_m2_color_alpha) - 1
        value.name = 'Color_{}_Alpha'.format(context.scene.wow_m2_cur_color_alpha_index)

        color = context.scene.wow_m2_colors.add()
        context.scene.wow_m2_cur_color_index = len(context.scene.wow_m2_colors) - 1
        color.name = 'Color_{}'.format(context.scene.wow_m2_cur_color_index)

        return {'FINISHED'}


class M2_OT_color_alpha_value_remove(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_color_alpha_remove_value'
    bl_label = 'Remove WoW color alpha'
    bl_description = 'Remove WoW color alpha'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        context.scene.wow_m2_color_alpha.remove(context.scene.wow_m2_cur_color_alpha_index)
        context.scene.wow_m2_colors.remove(context.scene.wow_m2_cur_color_alpha_index)

        return {'FINISHED'}


# def update_transparency_change(self, context):
#     for mat in bpy.data.materials:
#         if mat.use_nodes and len(mat.texture_paint_slots) > mat.paint_active_slot and mat.texture_paint_slots[mat.paint_active_slot].texture.wow_m2_texture.transparency == self.name:
#             mat.node_tree.nodes['Math'].inputs[1].default_value = self.value
#             mat.invert_z = mat.invert_z


class WowM2ColorAlphaPropertyGroup(bpy.types.PropertyGroup):

    value:  bpy.props.FloatProperty(
        name='Alpha',
        description='Defines alpha for color. Can be animated.',
        min=0.0,
        max=1.0,
        default=1.0,
    )

    name:  bpy.props.StringProperty(
        name='Color alpha name',
        description='Only used for scene organization purposes, ignored on export'
    )


def register():
    bpy.types.Scene.wow_m2_color_alpha = bpy.props.CollectionProperty(
        name='Alpha',
        type=WowM2ColorAlphaPropertyGroup
    )

    bpy.types.Scene.wow_m2_cur_color_alpha_index = bpy.props.IntProperty()


def unregister():
    del bpy.types.Scene.wow_m2_color_alpha
    del bpy.types.Scene.wow_m2_cur_color_alpha_index

