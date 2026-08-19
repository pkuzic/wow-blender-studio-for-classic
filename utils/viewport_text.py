import bpy
import blf
import os
import time


class WBS_Viewport_Text_Display(bpy.types.Operator):

    bl_idname = "wbs.viewport_text_display"
    bl_label = "Generic Text Display"
    _timer = None
    _draw_handler = None
    _start_time = None
    message: bpy.props.StringProperty()
    font_size: bpy.props.IntProperty(default=24)
    y_offset: bpy.props.IntProperty(default=67)
    color:bpy.props.FloatVectorProperty(
        size=4,
        default=(1.0, 1.0, 1.0, 1.0)
    )

    def draw_callback_px(self, context, message, font_size, y_offset, color):

        
        script_paths = bpy.utils.script_paths()
        addons_path = os.path.join(script_paths[0], "addons")
        addon_name = 'io_scene_wmo'
        font_rel_path = os.path.join("fonts", "frizqt_ck.ttf")
        font_path = os.path.join(addons_path, addon_name, font_rel_path)
        
        font_id = blf.load(font_path)
        blf.size(font_id, font_size, 72)
        width, height = context.area.width, context.area.height
        text_width, text_height = blf.dimensions(font_id, message)
        text_x = (width - text_width) / 2
        text_y = height - text_height - y_offset

        blf.position(font_id, text_x, text_y, 0)
        if color is None:
            color = (1, 1, 1, 1)
        blf.color(font_id, *color)
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 5, 0, 0, 0, 1)
        blf.shadow_offset(font_id, 1, -2)
        blf.draw(font_id, message)
        blf.disable(font_id, blf.SHADOW)

    def modal(self, context, event):
        if (time.time() - self._start_time) > 3.5:
            self.cancel(context)
            return {'CANCELLED'}
        
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        self._start_time = time.time()
        args = (context, self.message, self.font_size, self.y_offset, self.color)
        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_px, args, 'WINDOW', 'POST_PIXEL')
        
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, 'WINDOW')
            self._draw_handler = None
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None