from collections import namedtuple

import bpy


from .light import M2_PT_light_panel
from .material import M2_PT_material_panel
from .geoset import M2_PT_geoset_panel
from .attachment import M2_PT_attachment_panel
from .event import M2_PT_event_panel
from .colors import *
from .texture import M2_PT_texture_panel
from .utils import M2_UL_root_elements_template_list, update_current_object, is_obj_unused
from .... import ui_icons

from .transparency import *


######################
###### UI Lists ######
######################


class M2_UL_root_elements_groups_list(M2_UL_root_elements_template_list, bpy.types.UIList):

    icon = 'FILE_3D'


class M2_UL_root_elements_attachments_list(M2_UL_root_elements_template_list, bpy.types.UIList):

    icon = 'POSE_HLT'


class M2_UL_root_elements_events_list(M2_UL_root_elements_template_list, bpy.types.UIList):

    icon = 'PLUGIN'


class M2_UL_root_elements_materials_list(M2_UL_root_elements_template_list, bpy.types.UIList):

    icon = 'MATERIAL_DYNAMIC'


class M2_UL_root_elements_textures_list(M2_UL_root_elements_template_list, bpy.types.UIList):
    
    icon = 'IMAGE_DATA'


class M2_UL_root_elements_lights_list(M2_UL_root_elements_template_list, bpy.types.UIList):

    icon = 'LIGHT'


_ui_lists = {
    'geosets': 'M2_UL_root_elements_groups_list',
    'attachments': 'M2_UL_root_elements_attachments_list',
    'events': 'M2_UL_root_elements_events_list',
    'materials': 'M2_UL_root_elements_materials_list',
    'lights': 'M2_UL_root_elements_lights_list',
    'textures': 'M2_UL_root_elements_textures_list',
}


#####################
##### Panels #####
#####################

m2_widget_items = (
                    ("GEOSETS", "", "M2 Geosets", 'FILE_3D', 0),
                    ("ATTACHMENTS", "", "M2 Attachments", 'POSE_HLT', 1),
                    ("MATERIALS", "", "M2 Materials", 'MATERIAL', 2),
                    ("EVENTS", "", "M2 Events", 'PLUGIN', 3),
                    ("LIGHTS", "", "M2 Lights",'LIGHT', 4),
                    ("TEXTURES", "", "M2 Textures", 'IMAGE_DATA', 5)
                   )

m2_widget_labels = {item[0] : item[2] for item in m2_widget_items}


# class M2_PT_root_elements(bpy.types.Panel):
#     bl_space_type = "PROPERTIES"
#     bl_region_type = "WINDOW"
#     bl_context = "scene"
#     bl_label = "M2 Components"

#     @classmethod
#     def poll(cls, context):
#         return (context.scene is not None
#                 and context.scene.wow_scene.type == 'M2')

#     def draw(self, context):
#         layout = self.layout
        #row = layout.row(align=True)
        #row.prop(context.scene.wow_m2_root_elements, 'cur_widget', expand=True)
        # row.label(text=m2_widget_labels[context.scene.wow_m2_root_elements.cur_widget])
        # col = layout.column()

        # cur_widget = context.scene.wow_m2_root_elements.cur_widget

        # if cur_widget == 'GEOSETS':
        #     draw_m2_geosets_panel(col, context)
        # elif cur_widget == 'MATERIALS':
        #     draw_m2_materials_panel(col, context)
        # elif cur_widget == 'LIGHTS':
        #     draw_m2_lights_panel(col, context)
        # elif cur_widget == 'TEXTURES':
        #     draw_m2_textures_panel(col, context)
        # elif  cur_widget == 'ATTACHMENTS':
        #     draw_m2_attachments_panel(col, context)
        # elif  cur_widget == 'EVENTS':
        #     draw_m2_events_panel(col, context)
        # else:
        #     pass # invalid identifier


def draw_m2_geosets_panel(layout, context):
    layout = draw_list(context, layout, 'cur_geoset', 'geosets')

    root_comps = context.scene.wow_m2_root_elements
    geosets = root_comps.geosets
    cur_geoset = root_comps.cur_geoset

    ctx_override = namedtuple('ctx_override', ('object', 'scene', 'layout'))
    
    # print(geosets)
    # print(len(geosets))
    # print(cur_geoset)

    if len(geosets) > cur_geoset:
        obj = geosets[cur_geoset].pointer
        if obj:
            # print("passed") # can reach here
            box = layout.box()
            box.label(text='Properties', icon='PREFERENCES')

            ctx = ctx_override(obj, context.scene, box)
            M2_PT_geoset_panel.draw(ctx, ctx)


def draw_m2_lights_panel(layout, context):
    layout = draw_list(context, layout, 'cur_light', 'lights')

    root_comps = context.scene.wow_m2_root_elements
    lights = root_comps.lights
    cur_light = root_comps.cur_light

    ctx_override = namedtuple('ctx_override', ('object', 'scene', 'layout'))

    if len(lights) > cur_light:
        obj = lights[cur_light].pointer
        if obj:
            box = layout.box()
            box.label(text='Properties', icon='PREFERENCES')

            ctx = ctx_override(obj, context.scene, box)
            M2_PT_light_panel.draw(ctx, ctx)


def draw_m2_events_panel(layout, context):
    layout = draw_list(context, layout, 'cur_event', 'events')

    root_comps = context.scene.wow_m2_root_elements
    events = root_comps.events
    cur_event = root_comps.cur_event

    ctx_override = namedtuple('ctx_override', ('object', 'scene', 'layout'))

    if len(events) > cur_event:
        obj = events[cur_event].pointer
        if obj:
            box = layout.box()
            box.label(text='Properties', icon='PREFERENCES')

            ctx = ctx_override(obj, context.scene, box)
            M2_PT_event_panel.draw(ctx, ctx)


def draw_m2_attachments_panel(layout, context):
    layout = draw_list(context, layout, 'cur_attachment', 'attachments')

    root_comps = context.scene.wow_m2_root_elements
    attachments = root_comps.attachments
    cur_attachment = root_comps.cur_attachment

    ctx_override = namedtuple('ctx_override', ('object', 'scene', 'layout'))

    if len(attachments) > cur_attachment:
        obj = attachments[cur_attachment].pointer
        if obj:
            box = layout.box()
            box.label(text='Properties', icon='PREFERENCES')

            ctx = ctx_override(obj, context.scene, box)
            M2_PT_attachment_panel.draw(ctx, ctx)


def draw_m2_materials_panel(layout, context):
    layout = draw_list(context, layout, 'cur_material', 'materials')

    if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode == 'EDIT':
        row = layout.row(align=True)
        row.operator("object.wow_m2_material_assign", text="Assign")
        row.operator("object.wow_m2_material_select", text="Select")
        row.operator("object.wow_m2_material_deselect", text="Deselect")

    root_comps = context.scene.wow_m2_root_elements
    materials = root_comps.materials
    cur_material = root_comps.cur_material

    ctx_override = namedtuple('ctx_override', ('material', 'scene', 'layout'))

    if len(materials) > cur_material:
        mat = materials[cur_material].pointer
        if mat:
            box = layout.box()
            box.label(text='Properties', icon='PREFERENCES')

            ctx = ctx_override(mat, context.scene, box)
            M2_PT_material_panel.draw(ctx, ctx)


def draw_m2_textures_panel(layout, context):
    layout = draw_list(context, layout, 'cur_texture', 'textures')

    if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode == 'EDIT':
        row = layout.row(align=True)
        row.operator("object.wow_m2_texture_assign", text="Assign")
        row.operator("object.wow_m2_texture_select", text="Select")
        row.operator("object.wow_m2_texture_deselect", text="Deselect")

    root_comps = context.scene.wow_m2_root_elements
    textures = root_comps.textures
    cur_texture = root_comps.cur_texture

    ctx_override = namedtuple('ctx_override', ('edit_image', 'scene', 'layout'))

    if len(textures) > cur_texture:
        text = textures[cur_texture].pointer
        if text:
            box = layout.box()
            box.label(text='Properties', icon='PREFERENCES')

            ctx = ctx_override(text, context.scene, box)
            M2_PT_texture_panel.draw(ctx, ctx)


def draw_list(context, col, cur_idx_name, col_name):

    row = col.row()
    sub_col1 = row.column()
    sub_col1.template_list(_ui_lists[col_name], "",
                           context.scene.wow_m2_root_elements,
                           col_name, context.scene.wow_m2_root_elements, cur_idx_name)
    sub_col_parent = row.column()
    sub_col2 = sub_col_parent.column(align=True)

    if col_name not in():
        op = sub_col2.operator("scene.wow_m2_root_elements_change", text='', icon='ADD')
        op.action, op.add_action, op.col_name, op.cur_idx_name = 'ADD', 'NEW', col_name, cur_idx_name

    if col_name not in ('attachments', 'events'):
        op = sub_col2.operator("scene.wow_m2_root_elements_change", text='', icon='COLLECTION_NEW')
        op.action, op.add_action, op.col_name, op.cur_idx_name = 'ADD', 'EMPTY', col_name, cur_idx_name

    op = sub_col2.operator("scene.wow_m2_root_elements_change", text='', icon='REMOVE')
    op.action, op.col_name, op.cur_idx_name = 'REMOVE', col_name, cur_idx_name

    return sub_col1


###########################
##### Property Groups #####
###########################

prop_map = {
    'wow_m2_geoset': 'geosets',
    'wow_m2_attachment' : 'attachments',
    'wow_m2_material': 'materials',
    'wow_m2_event' : 'events',
    'wow_m2_light': 'lights',
    'wow_m2_texture': 'texture',
}


def update_object_pointer(self, context, prop, obj_type):

    if self.pointer:

        # handle replacing pointer value
        if self.pointer_old:
            if getattr(context.scene.wow_m2_root_elements, prop_map[prop]).find(self.pointer.name) < 0:
                getattr(self.pointer_old, prop).enabled = False
            self.pointer_old = None

        # check if object is another type
        if not is_obj_unused(self.pointer) \
                or self.pointer.type != obj_type \
                or getattr(context.scene.wow_m2_root_elements, prop_map[prop]).find(self.pointer.name) >= 0:
            # TODO : disabled this because it fucks up events/attachments pointers
            # self.pointer = None
            return

        # print("updating object pointer")
        print(self.pointer)
        print(type(self.pointer))
        getattr(self.pointer, prop).enabled = True
        self.pointer_old = self.pointer
        self.name = self.pointer.name

    elif self.pointer_old:
        # handle deletion
        getattr(self.pointer_old, prop).enabled = False
        self.pointer_old = None
        self.name = ""



def update_geoset_pointer(self, context):
    update_object_pointer(self, context, 'wow_m2_geoset', 'MESH')

    # force pass index recalculation
    if self.pointer:
        act_obj = context.view_layer.objects.active
        context.view_layer.objects.active = self.pointer

        self.pointer.wow_m2_geoset.mesh_part_group = self.pointer.wow_m2_geoset.mesh_part_group
        self.pointer.wow_m2_geoset.mesh_part_id = self.pointer.wow_m2_geoset.mesh_part_id

        context.view_layer.objects.active = act_obj



def update_material_pointer(self, context):

    if self.pointer:

        # handle replacing pointer value
        if self.pointer_old\
        and context.scene.wow_m2_root_elements.materials.find(self.pointer.name) < 0:
            self.pointer_old.wow_m2_material.enabled = False
            self.pointer_old = None

        # check if material is used
        if self.pointer.wow_m2_material.enabled \
        and context.scene.wow_m2_root_elements.materials.find(self.pointer.name) >= 0:
            self.pointer = None # !! BUG HAPPENS THERE, it removes elements from their slots
            return

        self.pointer.wow_m2_material.enabled = True
        self.pointer.wow_m2_material.self_pointer = self.pointer
        self.pointer_old = self.pointer
        self.name = self.pointer.name

        # force pass index recalculation

        ctx_override = namedtuple('ctx_override', ('material',))
        ctx = ctx_override(self.pointer)
        # update_shader(self.pointer.wow_m2_material, ctx)
        # update_flags(self.pointer.wow_m2_material, ctx)

    elif self.pointer_old:
        # handle deletion
        self.pointer_old.wow_m2_material.enabled = False
        self.pointer_old = None
        self.name = ""


def update_texture_pointer(self, context):
    
    if self.pointer:

        # handle replacing pointer value
        if self.pointer_old\
        and context.scene.wow_m2_root_elements.textures.find(self.pointer.name) < 0:
            self.pointer_old.wow_m2_texture.enabled = False
            self.pointer_old = None

        # check if texture is used
        if self.pointer.wow_m2_texture.enabled \
        and context.scene.wow_m2_root_elements.textures.find(self.pointer.name) >= 0:
            self.pointer = None
            return

        self.pointer.wow_m2_texture.enabled = True
        self.pointer.wow_m2_texture.self_pointer = self.pointer
        self.pointer_old = self.pointer
        self.name = self.pointer.name

        # force pass index recalculation

        ctx_override = namedtuple('ctx_override', ('texture',))
        ctx = ctx_override(self.pointer)

    elif self.pointer_old:
        # handle deletion
        self.pointer_old.wow_m2_texture.enabled = False
        self.pointer_old = None
        self.name = ""
        


class M2GeosetPointerPropertyGroup(bpy.types.PropertyGroup):

    pointer:  bpy.props.PointerProperty(
        name='M2 Geoset',
        type=bpy.types.Object,
        poll=lambda self, obj: is_obj_unused(obj) and obj.type == 'MESH',
        # update=lambda self, ctx: update_object_pointer(self, ctx, 'wow_m2_geoset', 'GEOSET')
        update=update_geoset_pointer
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Object)

    name:  bpy.props.StringProperty()


class M2EventPointerPropertyGroup(bpy.types.PropertyGroup):

    pointer:  bpy.props.PointerProperty(
        name='M2 Event',
        type=bpy.types.Object,
        poll=lambda self, obj: is_obj_unused(obj) and obj.type == 'MESH', #check if mesh works
        update=lambda self, ctx: update_object_pointer(self, ctx, 'wow_m2_event', 'EVENT')
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Object)

    name:  bpy.props.StringProperty()


class M2AttachmentPointerPropertyGroup(bpy.types.PropertyGroup):

    pointer:  bpy.props.PointerProperty(
        name='M2 Attachment',
        type=bpy.types.Object,
        poll=lambda self, obj: is_obj_unused(obj)and obj.type == 'MESH', #check if mesh works
        update=lambda self, ctx: update_object_pointer(self, ctx, 'wow_m2_attachment', 'ATTACHMENT')
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Object)

    name:  bpy.props.StringProperty()


class M2LightPointerPropertyGroup(bpy.types.PropertyGroup):

    pointer:  bpy.props.PointerProperty(
        name='M2 Light',
        type=bpy.types.Object,
        poll=lambda self, obj: is_obj_unused(obj) and obj.type == 'LIGHT',
        update=lambda self, ctx: update_object_pointer(self, ctx, 'wow_m2_light', 'LIGHT')
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Object)

    name:  bpy.props.StringProperty()


class M2MaterialPointerPropertyGroup(bpy.types.PropertyGroup):

    pointer:  bpy.props.PointerProperty(
        name='M2 Material',
        type=bpy.types.Material,
        poll=lambda self, mat: not mat.wow_m2_material.enabled,
        update=update_material_pointer
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Material)

    name:  bpy.props.StringProperty()


class M2TexturePointerPropertyGroup(bpy.types.PropertyGroup):
    
    pointer:  bpy.props.PointerProperty(
        name='M2 Texture',
        type=bpy.types.Image,
        poll=lambda self, text: not text.wow_m2_texture.enabled,
        update=update_texture_pointer
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Image)

    name:  bpy.props.StringProperty()


class ColorPointerPropertyGroup(bpy.types.PropertyGroup):
    
    color:  bpy.props.FloatVectorProperty(
        name='Color',
        description='The color applied to WoW material. Can be animated. Alpha defines model transparency and is multiplied with transparency value',
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_color_change
    )

    pointer_old:  bpy.props.PointerProperty(type=bpy.types.Material)

    name:  bpy.props.StringProperty()


class WoWM2_RootComponents(bpy.types.PropertyGroup):

    cur_widget: bpy.props.EnumProperty(
        name='M2 Components',
        items=m2_widget_items
    )

    geosets:  bpy.props.CollectionProperty(type=M2GeosetPointerPropertyGroup)
    cur_geoset:  bpy.props.IntProperty(update=lambda self, ctx: update_current_object(self, ctx, 'geosets', 'cur_geoset'))

    ######################################
    events:  bpy.props.CollectionProperty(type=M2EventPointerPropertyGroup)
    cur_event:  bpy.props.IntProperty(update=lambda self, ctx: update_current_object(self, ctx, 'events', 'cur_event'))

    attachments:  bpy.props.CollectionProperty(type=M2AttachmentPointerPropertyGroup)
    cur_attachment:  bpy.props.IntProperty(update=lambda self, ctx: update_current_object(self, ctx, 'attachments', 'cur_attachment'))
    ######################################

    lights:  bpy.props.CollectionProperty(type=M2LightPointerPropertyGroup)
    cur_light:  bpy.props.IntProperty(update=lambda self, ctx: update_current_object(self, ctx, 'lights', 'cur_light'))

    materials:  bpy.props.CollectionProperty(type=M2MaterialPointerPropertyGroup)
    cur_material:  bpy.props.IntProperty()
    
    colors:  bpy.props.CollectionProperty(type=ColorPointerPropertyGroup)
    cur_color:  bpy.props.IntProperty()
    
    textures:  bpy.props.CollectionProperty(type=M2TexturePointerPropertyGroup)
    cur_texture:  bpy.props.IntProperty()

    # TODO : CAMERAS, PARTICLES, texture transforms ?
    


def register():
    bpy.types.Scene.wow_m2_root_elements = bpy.props.PointerProperty(type=WoWM2_RootComponents)



def unregister():
    del bpy.types.Scene.wow_m2_root_elements
    
