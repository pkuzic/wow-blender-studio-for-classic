import bpy

from ..panels.root_elements import is_obj_unused


class M2_OT_destroy_property(bpy.types.Operator):
    bl_idname = "scene.wow_m2_destroy_wow_property"
    bl_label = "Disable Property"
    bl_options = {'UNDO', 'REGISTER', 'INTERNAL'}

    prop_group:  bpy.props.StringProperty()

    prop_map = {
        'wow_m2_geoset': 'geosets',
        'wow_m2_light': 'lights',
        'wow_m2_material': 'materials'
    }

    @classmethod
    def poll(cls, context):
        return context.scene.wow_scene.type == 'M2' and hasattr(context, 'object') and context.object

    def execute(self, context):

        getattr(context.object, self.prop_group).enabled = False

        col = getattr(bpy.context.scene.wow_m2_root_elements, self.prop_map[self.prop_group])

        idx = col.find(context.object.name)

        if idx >= 0:
            col.remove(idx)

        return {'FINISHED'}


class M2_OT_root_elements_components_change(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_root_elements_change'
    bl_label = 'Add / Remove'
    bl_description = 'Add / Remove'
    bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

    col_name:  bpy.props.StringProperty(options={'HIDDEN'})
    cur_idx_name:  bpy.props.StringProperty(options={'HIDDEN'})
    action:  bpy.props.StringProperty(default='ADD', options={'HIDDEN'})
    add_action:  bpy.props.EnumProperty(
        items=[('EMPTY', 'Empty', ''),
               ('NEW', 'New', '')],
        default='EMPTY',
        options={'HIDDEN'}
    )

    def execute(self, context):

        if self.action == 'ADD':

            if self.col_name != 'materials' \
            and bpy.context.view_layer.objects.active \
            and bpy.context.view_layer.objects.active.mode != 'OBJECT':
                self.report({'ERROR'}, "Object mode must be active.")
                return {'CANCELLED'}

            if self.col_name == 'geosets':
                
                print("trying to add geoset")

                obj = bpy.context.view_layer.objects.active

                if obj and obj.select_get():

                    if obj.type != 'MESH':
                        self.report({'ERROR'}, "Object must be a mesh")
                        return {'CANCELLED'}

                    if not is_obj_unused(obj):

                        if not obj.wow_m2_geoset.enabled:
                            self.report({'ERROR'}, "Object is already used")
                            return {'CANCELLED'}

                        else:
                            win = bpy.context.window
                            scr = win.screen
                            areas3d = [area for area in scr.areas if area.type == 'VIEW_3D']
                            region = [region for region in areas3d[0].regions if region.type == 'WINDOW']

                            override = {'window': win,
                                        'screen': scr,
                                        'area': areas3d[0],
                                        'region': region[0],
                                        'scene': bpy.context.scene,
                                        'object': obj
                                        }

                            bpy.ops.scene.wow_m2_destroy_wow_property(override, prop_group='wow_m2_geoset')
                            self.report({'INFO'}, "Geoset was overriden")

                    slot = bpy.context.scene.wow_m2_root_elements.geosets.add()
                    slot.pointer = obj

                else:
                    bpy.context.scene.wow_m2_root_elements.geosets.add()

            elif self.col_name == 'lights':
                slot = bpy.context.scene.wow_m2_root_elements.lights.add()

                if self.add_action == 'NEW':
                    light = bpy.data.objects.new(name='LIGHT', object_data=bpy.data.lights.new('LIGHT', type='POINT'))
                    bpy.context.collection.objects.link(light)
                    light.location = bpy.context.scene.cursor.location
                    slot.pointer = light

            elif self.col_name == 'materials':

                slot = bpy.context.scene.wow_m2_root_elements.materials.add()

                if self.add_action == 'NEW':
                    new_mat = bpy.data.materials.new('Material')
                    slot.pointer = new_mat

            elif self.col_name == 'textures':

                slot = bpy.context.scene.wow_m2_root_elements.textures.add()

                # if self.add_action == 'NEW':
                #     new_text = bpy.data.images.new('Texture')
                #     slot.pointer = new_text

            elif self.col_name == 'attachments':
                #TODO
                bpy.context.scene.wow_m2_root_elements.attachments.add()

            elif self.col_name == 'events':
                #TODO
                

                # bpy.ops.object.empty_add(type='CUBE', location=(0, 0, 0))
                # obj = bpy.context.view_layer.objects.active
                # obj.scale = (0.019463, 0.019463, 0.019463)
                # bpy.ops.object.constraint_add(type='CHILD_OF')
                # constraint = obj.constraints[-1]
                # constraint.target = self.rig # TODO rig
                # obj.parent = self.rig

                # obj.name = "Event_{}".format(token)
                # obj.wow_m2_event.enabled = True
                
                slot = bpy.context.scene.wow_m2_root_elements.events.add()
                # slot.pointer = obj


        elif self.action == 'REMOVE':

            col = getattr(context.scene.wow_m2_root_elements, self.col_name)
            cur_idx = getattr(context.scene.wow_m2_root_elements, self.cur_idx_name)

            if len(col) <= cur_idx:
                return {'FINISHED'}

            item = col[cur_idx].pointer

            if item:
                if self.col_name == 'geosets':
                    item.wow_m2_geoset.enabled = False

                elif self.col_name == 'lights':
                    item.wow_m2_light.enabled = False

                elif self.col_name == 'materials':
                    item.wow_m2_material.enabled = False

                elif self.col_name == 'textures':
                    item.wow_m2_texture.enabled = False
                               
                elif self.col_name == 'attachments':
                    item.wow_m2_attachment.enabled = False
                
                elif self.col_name == 'events':
                    item.wow_m2_event.enabled = False


            col.remove(cur_idx)

        else:
            self.report({'ERROR'}, 'Unsupported token')
            return {'CANCELLED'}

        return {'FINISHED'}
