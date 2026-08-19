import bpy
from ..enums import *

class TexturePathDefaultButton(bpy.types.Operator):
    bl_idname = "wow_m2_texture.set_default_texture"
    bl_label = "Set Default Texture Path"

    def execute(self, context):
        default_texture_path = "textures\\ShaneCube.blp"
        context.object.wow_m2_particle.texture.wow_m2_texture.path = default_texture_path   
        return {'FINISHED'}    
    
class ToggleFlagsOperator(bpy.types.Operator):
    bl_idname = "particles.toggle_flags"
    bl_label = "Toggle Particle Flags"
    
    def execute(self, context):
        context.scene.show_flags = not context.scene.show_flags   
        return {'FINISHED'}
    
bpy.types.Scene.show_flags = bpy.props.BoolProperty(name="Toggle Particle Flags", default=False)   

class M2_PT_particle_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_label = "M2 Particle"

    def draw_header(self, context):
        self.layout.prop(context.object.wow_m2_particle, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        particle = context.object.wow_m2_particle
        col.operator("particles.toggle_flags", text="Toggle Particle Flags") 
        if context.scene.show_flags: 
            col.prop(particle, 'flags', text='Flags')

        col.prop(particle, 'action',text='Action')
        col.prop(particle, 'texture',text='Texture')
        try:
            col.prop(particle.texture.wow_m2_texture, "path", text='Path')
            if len(particle.texture.wow_m2_texture.path) == 0:
                col.operator(TexturePathDefaultButton.bl_idname, text="Set Default Path", icon='FILEBROWSER') 
        except:
            pass
        col.prop(particle, 'geometry_model_filename', text='Geometry Model Filename')
        col.prop(particle, 'recursion_model_filename', text='Recursion Model Filename')
        col.prop(particle, 'blending_type',text="Blending Type")
        col.prop(particle, 'emitter_type',text="Alpha")
        col.prop(particle, 'particle_type',text="Particle Type")
        col.prop(particle, 'side',text="Side")
        col.prop(particle, 'particle_color_index',text="Particle Color Index")
        col.prop(particle, 'texture_tile_rotation',text="Texture Tile Rotation")
        col.prop(particle, 'texture_dimensions_rows',text="Texture Dimension Rows")
        col.prop(particle, 'texture_dimensions_cols',text="Texture Dimension Columns")
        col.prop(particle, 'emission_speed',text="Emission Speed")
        col.prop(particle, 'speed_variation',text="Speed Variation")
        col.prop(particle, 'vertical_range',text="Vertical Range")
        col.prop(particle, 'horizontal_range',text="Horizontal Range")
        col.prop(particle, 'gravity',text="Gravity")
        col.prop(particle, 'lifespan',text="Lifespan")
        col.prop(particle, 'lifespan_vary',text="Lifespan Vary")
        col.prop(particle, 'emission_rate',text="Emission Rate")
        col.prop(particle, 'emission_rate_vary',text="Emission Rate Vary")
        col.prop(particle, 'emission_area_length',text="Emission Area Length")
        col.prop(particle, 'emission_area_width',text="Emission Area Width")
        col.prop(particle, 'z_source',text="Z Source")
        col.prop(particle, 'color',text="Color")
        col.prop(particle, 'alpha',text="Alpha")
        col.prop(particle, 'scale',text="Scale")
        col.prop(particle, 'scale_vary',text="Scale Vary")
        col.prop(particle, 'head_cell',text="Head Cell")
        col.prop(particle, 'tail_cell',text="Tail Cell")
        col.prop(particle, 'tail_length',text="Tail Length")
        col.prop(particle, 'twinkle_speed',text="Twinkle Speed")
        col.prop(particle, 'twinkle_percent',text="Twinkle Percent")
        col.prop(particle, 'twinkle_scale',text="Twinkle Scale")
        col.prop(particle, 'burst_multiplier',text="Burst Multiplier")
        col.prop(particle, 'drag',text="Drag")
        col.prop(particle, 'basespin',text="Base Spin")
        col.prop(particle, 'basespin_vary',text="Base Spin Vary")
        col.prop(particle, 'spin',text="Spin")
        col.prop(particle, 'spin_vary',text="Spin Vary")
        col.prop(particle, 'tumble_min',text="Tumble Min")
        col.prop(particle, 'tumble_max',text="Tumble Max")
        col.prop(particle, 'wind',text="Wind")
        col.prop(particle, 'wind_time',text="Wind Time")
        col.prop(particle, 'follow_speed_1',text="Follow Speed #1")
        col.prop(particle, 'follow_scale_1',text="Follow Scale #1")
        col.prop(particle, 'follow_speed_2',text="Follow Speed #2")
        col.prop(particle, 'follow_scale_2',text="Follow Scale #2")
        col.prop(particle, 'spline_action',text="Spline Action")
        col.prop(particle, 'spline_point',text="Spline Point")
        col.prop(particle, 'active',text="Active")

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and context.scene.wow_scene.type == 'M2'
                and context.object is not None
                and context.object.type == 'EMPTY'
                and not (context.object.wow_m2_event.enabled
                         or context.object.wow_m2_uv_transform.enabled
                         or context.object.wow_m2_camera.enabled
                         or context.object.wow_m2_attachment.enabled
                         or context.object.wow_m2_ribbon.enabled
                         )
        )

class WowM2ParticlePropertyGroup(bpy.types.PropertyGroup):
    enabled:  bpy.props.BoolProperty(
        name='Enabled',
        description='Enabled this object to be a WoW M2 Particle',
        default=False
    )

    action: bpy.props.PointerProperty(
        name='Action',
        description='',
        type=bpy.types.Action
    )

    flags:  bpy.props.EnumProperty(
        name="Material flags",
        description="",
        items=PARTICLE_FLAGS,
        options={"ENUM_FLAG"}
    )

    texture: bpy.props.PointerProperty (
        type=bpy.types.Image
    )

    geometry_model_filename: bpy.props.StringProperty (
        name = 'Geometry Model Filename',
        description = '',
        default = ''
    )

    recursion_model_filename: bpy.props.StringProperty (
        name = 'Recursion Model Filename',
        description = '',
        default = ''
    )

    blending_type:  bpy.props.EnumProperty (
        name='Blending Type',
        description='',
        items = [
            ('0','0: glDisable(GL_BLEND); glDisable(GL_ALPHA_TEST)',''),
            ('1','1: glBlendFunc(GL_SRC_COLOR, GL_ONE)',''),
            ('2','2: glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)',''),
            ('3','3: glDisable(GL_BLEND); glEnable(GL_ALPHA_TEST)',''),
            ('4','4: glBlendFunc(GL_SRC_ALPHA, GL_ONE)',''),
        ]
    )

    emitter_type: bpy.props.EnumProperty(
        name='Emitter Type',
        description='The shape of this emitter',
        items = [
            ('0','Rectangle',''),
            ('1','Sphere',''),
            ('2','Spline',''),
            ('3','Bone',''),
        ]
    )

    particle_color_index: bpy.props.IntProperty(
        name='Particle Color Index',
        description='An index into ParticleColor.dbc',
        default = 0
    )

    particle_type: bpy.props.EnumProperty(
        name='Particle Type',
        description='',
        items = [
            ('0','Normal','Normal particle, usual way to go'),
            ('1','Large Quad','Used in Moonwell water effects'),
            ('2','Unknown','Used in Deeprun Tram'),
        ]
    )

    side: bpy.props.EnumProperty(
        name='Side',
        description='What sides of the particle emits',
        items = [
            ('0','Head',''),
            ('1','Tail',''),
            ('2','Both',''),
        ]
    )

    texture_tile_rotation: bpy.props.IntProperty(
        name='Texture Tile Rotation',
        description='',
        min=-1,
        max=1,
        default=0
    )

    texture_dimensions_rows: bpy.props.IntProperty(
        name='Texture Dimensions Rows',
        description='Used to divide the used texture in rows',
        default=1
    )

    texture_dimensions_cols: bpy.props.IntProperty(
        name='Texture Dimensions Columns',
        description='Used to divide the used texture in columns',
        default=1
    )

    emission_speed: bpy.props.FloatProperty(
        name='Emission Speed',
        description='',
        default=0.0
    )

    speed_variation: bpy.props.FloatProperty(
        name='Speed Variation',
        description='',
        default=0.0
    )

    vertical_range: bpy.props.FloatProperty(
        name='Speed Variation',
        description='',
        default=0.0
    )

    horizontal_range: bpy.props.FloatProperty(
        name='Horizontal Range',
        description='',
        default=0.0
    )

    gravity: bpy.props.FloatProperty(
        name='Gravity',
        description='',
        default=0.0
    )

    lifespan: bpy.props.FloatProperty(
        name='Lifespan',
        description='',
        default=0.0
    )

    lifespan_vary: bpy.props.FloatProperty(
        name='Lifespan Vary',
        description='',
        default=0.0
    )

    emission_rate: bpy.props.FloatProperty(
        name='Emission Rate',
        description='',
        default=0.0
    )

    emission_rate_vary: bpy.props.FloatProperty(
        name='Emission Rate Vary',
        description='',
        default=0.0
    )

    emission_area_length: bpy.props.FloatProperty(
        name='Emission Area Length',
        description='',
        default=0.0
    )

    emission_area_width: bpy.props.FloatProperty(
        name='Emission Area Width',
        description='',
        default=0.0
    )

    z_source: bpy.props.FloatProperty(
        name='Z Source',
        description='',
        default=0.0
    )

    color: bpy.props.FloatVectorProperty(
        name = "Color",
        description="",
        subtype='COLOR',
        size=3,
        default=(1.0,1.0,1.0),
        min=0.0,
        max=1.0
    )

    alpha: bpy.props.FloatProperty(
        name = "Alpha",
        description="",
        default=0,
        min=0,
        max=1
    )

    scale: bpy.props.FloatVectorProperty(
        name = "Scale",
        description="",
        size=2,
        default=(1.0,1.0),
    )

    scale_vary: bpy.props.FloatVectorProperty(
        name = "Scale Vary",
        description="",
        size=2,
        default=(1.0,1.0),
    )

    head_cell: bpy.props.IntProperty(
        name = "Head Cell",
        description = "",
        default = 0
    )

    tail_cell: bpy.props.IntProperty(
        name = "Tail Cell",
        description = "",
        default = 0
    )

    tail_length: bpy.props.FloatProperty(
        name = "Tail Length",
        description = "",
        default = 0
    )

    twinkle_speed: bpy.props.FloatProperty(
        name = "Twinkle Speed",
        description = "",
        default = 0
    )

    twinkle_percent: bpy.props.FloatProperty(
        name = "Twinkle Percent",
        description = "",
        default = 0
    )

    twinkle_scale: bpy.props.FloatVectorProperty(
        name = "Twinkle Scale",
        description = "",
        size=2,
        default=(1.0,1.0)
    )

    burst_multiplier: bpy.props.FloatProperty(
        name = "Burst Multiplier",
        description = "",
        default = 1
    )

    drag: bpy.props.FloatProperty(
        name = "Drag",
        description = "",
        default = 1
    )

    basespin: bpy.props.FloatProperty(
        name = "Base Spin",
        description = "",
        default = 0
    )

    basespin_vary: bpy.props.FloatProperty(
        name = "Base Spin Vary",
        description = "",
        default = 0
    )

    spin: bpy.props.FloatProperty(
        name = "Spin",
        description = "",
        default = 0
    )

    spin_vary: bpy.props.FloatProperty(
        name = "Spin Vary",
        description = "",
        default = 0
    )

    tumble_min: bpy.props.FloatVectorProperty(
        name = "Tumble Min",
        description = "",
        size=3,
        default = (0.0,0.0,0.0),
    )

    tumble_max: bpy.props.FloatVectorProperty(
        name = "Tumble Max",
        description = "",
        size=3,
        default = (0.0,0.0,0.0),
    )

    wind: bpy.props.FloatVectorProperty(
        name = "Wind",
        description = "",
        size=3,
        default = (0.0,0.0,0.0)
    )

    wind_time: bpy.props.FloatProperty(
        name = "Wind Time",
        description = "",
        default = 0
    )

    follow_speed_1: bpy.props.FloatProperty(
        name = "Follow Speed #1",
        description = "",
        default = 0
    )

    follow_scale_1: bpy.props.FloatProperty(
        name = "Follow Scale #1",
        description = "",
        default = 0
    )

    follow_speed_2: bpy.props.FloatProperty(
        name = "Follow Speed #2",
        description = "",
        default = 0
    )

    follow_scale_2: bpy.props.FloatProperty(
        name = "Follow Scale #2",
        description = "",
        default = 0
    )

    spline_action: bpy.props.PointerProperty(
        name = 'Spline Action',
        description = 'FCurve describing the spline point values in this particle. Important: timestamps are only used for ordering, time values are discarded on export.',
        type = bpy.types.Action
    )

    spline_point: bpy.props.FloatVectorProperty(
        name = 'Spline Point',
        description = '',
        size=3,
        default = (0.0,0.0,0.0)
    )

    active: bpy.props.BoolProperty(
        name = "Active",
        description = "",
        default = False
    )

def register():
    bpy.types.Object.wow_m2_particle = bpy.props.PointerProperty(type=WowM2ParticlePropertyGroup)


def unregister():
    del bpy.types.Object.wow_m2_particle

