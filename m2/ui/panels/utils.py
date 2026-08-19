import bpy
from ..handlers import DepsgraphLock


_obj_props = ['wow_m2_geoset',
              'wow_m2_attachment',
              'wow_m2_event',
              'wow_m2_light' # bug with light
              ]


def update_current_object(self, context, col_name, cur_item_name):

    if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode != 'OBJECT':
        return

    col = getattr(self, col_name)
    cur_idx = getattr(self, cur_item_name)

    if len(col) <= cur_idx or cur_idx < 0:
        return

    slot = col[cur_idx]

    if bpy.context.view_layer.objects.active == slot.pointer:
        return

    if slot.pointer and not slot.pointer.hide_get():
        with DepsgraphLock():
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = slot.pointer
            slot.pointer.select_set(True)


def is_obj_unused(obj):
    for prop in _obj_props:
        if prop == 'wow_m2_light':
            if obj.type == 'LIGHT' and getattr(obj.data, prop).enabled:
                return False
        else:
            if getattr(obj, prop).enabled:
                return False


    # if obj.wow_m2_geoset.collision_mesh:
    #     return False

    return True


class M2_UL_root_elements_template_list(bpy.types.UIList):

    icon = 'OBJECT_DATA'

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):

        if self.layout_type in {'DEFAULT', 'COMPACT'}:

            # handle material icons
            if self.icon == 'MATERIAL_DYNAMIC':
                texture = item.pointer.wow_m2_material.texture_1 if item.pointer else None
                self.icon = layout.icon(texture) if texture else 'MATERIAL'

            elif self.icon == 'TEXTURE_DYNAMIC':
                texture = item.pointer if item.pointer else None
                self.icon = layout.icon(texture) if texture else 'MATERIAL'

            row = layout.row()
            col = row.column()
            col.scale_x = 0.5

            if isinstance(self.icon, int):
                col.label(text="#{} ".format(index), icon_value=self.icon)

            elif isinstance(self.icon, str):
                col.label(text="#{} ".format(index), icon=self.icon)

            col = row.column()
            s_row = col.row(align=True)
            s_row.prop(item, 'pointer', emboss=True, text='')

        elif self.layout_type in {'GRID'}:
            pass

    def filter_items(self, context, data, propname):

        col = getattr(data, propname)
        filter_name = self.filter_name.lower()

        flt_flags = [self.bitflag_filter_item
                     if any(filter_name in filter_set for filter_set in (str(i), (item.pointer.name if item.pointer else 'Empty slot').lower()))
                     else 0 for i, item in enumerate(col, 1)
                     ]

        if self.use_filter_sort_alpha:
            flt_neworder = [x[1] for x in sorted(
                zip(
                    [x[0] for x in sorted(enumerate(col),
                                          key=lambda x: x[1].name.split()[1] + x[1].name.split()[2])], range(len(col))
                )
            )
            ]
        else:
            flt_neworder = []

        return flt_flags, flt_neworder

class M2_OT_object_list_change(bpy.types.Operator):
    bl_idname = 'object.wow_m2_object_list_change'
    bl_label = 'Add / Remove'
    bl_description = 'Add / Remove'
    bl_options = {'REGISTER','INTERNAL','UNDO'}

    obj_name:  bpy.props.StringProperty(options={'HIDDEN'})
    col_name:  bpy.props.StringProperty(options={'HIDDEN'})
    idx_name:  bpy.props.StringProperty(options={'HIDDEN'})
    action:  bpy.props.StringProperty(default='ADD', options={'HIDDEN'})
    add_action:  bpy.props.EnumProperty(
        items=[('EMPTY', 'Empty', ''),
               ('NEW', 'New', '')],
        default='EMPTY',
        options={'HIDDEN'}
    )

    def execute(self, context):
        obj = getattr(bpy.context.object,self.obj_name)
        col = getattr(obj,self.col_name)
        if self.action == 'ADD':
            slot = col.add()
            setattr(obj,self.idx_name,len(col)-1)
        elif self.action == 'REMOVE':
            idx = getattr(obj,self.idx_name)
            col_len = len(col)
            if idx >= col_len or idx < 0:
                idx = col_len-1
            col.remove(getattr(obj,self.idx_name))
        else:
            raise ValueError(f'Invalid object list action {self.action}')
        return {'FINISHED'}

def draw_object_list(obj,col,label,template,obj_name,col_name,sel_name):
    col.label(text=label)
    row = col.row()
    sub_col1 = row.column()
    sub_col1.template_list(template,'',obj,col_name,obj,sel_name)
    sub_col_parent = row.column()
    sub_col2 = sub_col_parent.column(align=True)

    op1 = sub_col2.operator('object.wow_m2_object_list_change', text='', icon='ADD')
    op1.action, op1.col_name, op1.idx_name, op1.obj_name = 'ADD', col_name, sel_name, obj_name

    op2 = sub_col2.operator('object.wow_m2_object_list_change', text='', icon='REMOVE')
    op2.action, op2.col_name, op2.idx_name, op2.obj_name = 'REMOVE', col_name, sel_name, obj_name