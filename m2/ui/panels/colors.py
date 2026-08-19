import bpy


class M2_PT_colors_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_label = "M2 Colors"

    def draw(self, context):
        # layout = self.layout

        # col = layout.column()

        # row = col.row()
        # sub_col1 = row.column()
        # sub_col1.template_list("M2_UL_color_list", "", context.scene, "wow_m2_colors", context.scene,
        #                        "wow_m2_cur_color_index")

        # sub_col2 = row.column().column(align=True)
        # sub_col2.operator("scene.wow_m2_colors_add_color", text='', icon='ADD')
        # sub_col2.operator("scene.wow_m2_colors_remove_color", text='', icon='REMOVE')

        layout = self.layout

        # Create two columns side by side
        split = layout.split(factor=0.5)

        # Left column for the color list
        col_left = split.column()

        row = col_left.row()
        sub_col1 = row.column()
        sub_col1.template_list("M2_UL_color_list", "", context.scene, "wow_m2_colors", context.scene,
                            "wow_m2_cur_color_index")

        # Right column for the alpha list
        col_right = split.column()

        row = col_right.row()
        sub_col1 = row.column()
        sub_col1.template_list("M2_UL_color_alpha_list", "", context.scene, "wow_m2_color_alpha",
                            context.scene, "wow_m2_cur_color_alpha_index")

        sub_col2 = row.column().column(align=True)
        sub_col2.operator("scene.wow_m2_colors_add_color", text='', icon='ADD')
        sub_col2.operator("scene.wow_m2_colors_remove_color", text='', icon='REMOVE')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_UL_color_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):
        self.use_filter_show = False

        if self.layout_type in {'DEFAULT', 'COMPACT'}:

            row = layout.row(align=True)
            cur_color_prop_group = context.scene.wow_m2_colors[index]
            row.prop(cur_color_prop_group, "name", text="", icon='COLOR', emboss=False)
            row.prop(cur_color_prop_group, "color", text="")

        elif self.layout_type in {'GRID'}:
            pass


class M2_OT_color_add(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_colors_add_color'
    bl_label = 'Add WoW color'
    bl_description = 'Add WoW color'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        color = context.scene.wow_m2_colors.add()
        context.scene.wow_m2_cur_color_index = len(context.scene.wow_m2_colors) - 1
        color.name = 'Color_{}'.format(context.scene.wow_m2_cur_color_index)

        value = context.scene.wow_m2_color_alpha.add()
        context.scene.wow_m2_cur_color_alpha_index = len(context.scene.wow_m2_color_alpha) - 1
        value.name = 'Color_{}_Alpha'.format(context.scene.wow_m2_cur_color_alpha_index)

        return {'FINISHED'}


class M2_OT_color_remove(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_colors_remove_color'
    bl_label = 'Remove WoW color'
    bl_description = 'Remove WoW color'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        context.scene.wow_m2_colors.remove(context.scene.wow_m2_cur_color_index)
        context.scene.wow_m2_color_alpha.remove(context.scene.wow_m2_cur_color_index)

        return {'FINISHED'}


def update_color_change(self, context):
    for mat in bpy.data.materials:
        if mat.use_nodes and len(mat.texture_paint_slots) > mat.paint_active_slot and mat.texture_paint_slots[mat.paint_active_slot].texture.wow_m2_texture.color == self.name:
            mat.node_tree.nodes['ColorRamp'].color_ramp.elements[0].color = self.color
            mat.invert_z = mat.invert_z

class WowM2ColorPropertyGroup(bpy.types.PropertyGroup):

    color:  bpy.props.FloatVectorProperty(
        name='Color',
        description='The color applied to WoW material. Can be animated. Alpha defines model transparency and is multiplied with transparency value',
        subtype='COLOR',
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=10.0,
        soft_max=1.0,
        update=update_color_change

    )

    name:  bpy.props.StringProperty(
        name='Color name',
        description='Only used for scene organization purposes, ignored on export'
    )


def register():
    bpy.types.Scene.wow_m2_colors = bpy.props.CollectionProperty(
        name='Colors',
        type=WowM2ColorPropertyGroup
    )

    bpy.types.Scene.wow_m2_cur_color_index = bpy.props.IntProperty()


def unregister():
    del bpy.types.Scene.wow_m2_colors
    del bpy.types.Scene.wow_m2_cur_color_index

