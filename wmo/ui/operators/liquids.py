import bpy
import bmesh
import os

from math import cos, sin, tan, radians
from time import time

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

from ....addon_common.cookiecutter.cookiecutter import CookieCutter
from ....addon_common.common import ui
from ....addon_common.common.utils import delay_exec
from ....addon_common.common.drawing import Drawing
from ....addon_common.common.boundvar import BoundInt, BoundFloat, BoundBool
from ....addon_common.common.ui_styling import load_defaultstylings
from ....addon_common.common.globals import Globals

from ..handlers import DepsgraphLock
from .. import handlers
from ...ui.collections import get_wmo_collection, SpecialCollections



def angled_vertex(origin: Vector, pos: Vector, angle: float, orientation: float) -> float:
    return origin.z + ((pos.x - origin.x) * cos(orientation) + (pos.y - origin.y) * sin(orientation)) * tan(angle)


def get_median_point(bm: bmesh.types.BMesh) -> Vector:

    selected_vertices = [v for v in bm.verts if v.select]

    f = 1 / len(selected_vertices)

    median = Vector((0, 0, 0))

    for vert in selected_vertices:
        median += vert.co * f

    return median


def align_vertices(bm : bmesh.types.BMesh, mesh : bpy.types.Mesh, median : Vector, angle : float, orientation : float):
    for vert in bm.verts:
        if vert.select:
            vert.co[2] = angled_vertex(median, vert.co, radians(angle), radians(orientation))

    bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=True)


def reload_stylings():
    load_defaultstylings()
    path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ui', 'ui.css')
    try:
        Globals.ui_draw.load_stylesheet(path)
    except AssertionError as e:
        # TODO: show proper dialog to user here!!
        print('could not load stylesheet "%s"' % path)
        print(e)
    Globals.ui_document.body.dirty('Reloaded stylings', children=True)
    Globals.ui_document.body.dirty_styling()
    Globals.ui_document.body.dirty_flow()


event_keymap = {
    'ONE' : 0,
    'TWO' : 1,
    'THREE': 2,
    'FOUR': 3,
    'FIVE': 4,
    'SIX': 5,
    'SEVEN': 6,
    'EIGHT': 7,
    'NUMPAD_1': 0,
    'NUMPAD_2': 1,
    'NUMPAD_3': 2,
    'NUMPAD_4': 3,
    'NUMPAD_5': 4,
    'NUMPAD_6': 5,
    'NUMPAD_7': 6,
    'NUMPAD_8': 7,
}

# some settings container
options = {}
options["variable_1"] = 10.0
options["variable_3"] = True
options["x_size"] = 10
options["y_size"] = 10
options["brush_size"] = 2

flags = {}
flags["flag_1"] = True
flags["flag_2"] = False
flags["flag_3"] = False

flag_checkboxes = []

class WMO_OT_edit_liquid(CookieCutter, bpy.types.Operator):
    bl_idname = "wow.liquid_edit_mode"
    bl_label = "Edit WoW Liquid"

    default_keymap = {
        'cancel': {'ESC', 'TAB'},
        'grab': 'G',
        'rotate': 'R',
        'equalize': 'E',
        'flag': 'F',
        'paint': {'LEFTMOUSE', 'SHIFT+LEFTMOUSE'}
    }

    @property
    def variable_2_gs(self):
        return getattr(self, '_var_cut_count_value', 0)

    @variable_2_gs.setter
    def variable_2_gs(self, v):
        if self.variable_2 == v: return
        self.variable_2 = v
        # if self.variable_2.disabled: return

    def start(self):
        self.init_loc = 0.0
        self.speed_modifier = 1.0

        self.orientation = 0.0
        self.angle = 0.0

        self.median = Vector((0, 0, 0))
        self.color_type = 'TEXTURE'
        self.shading_type = 'SOLID'

        self.selected_verts = {}
        self.viewports = []
        self.init_time = time()

        self.obj = self.context.object
        self.mesh = self.context.object.data

        self.active_tool = 'select'

        DepsgraphLock().push()

        bpy.ops.mesh.select_mode(bpy.context.copy(), type='VERT', action='ENABLE', use_extend=True)
        bpy.ops.mesh.select_mode(bpy.context.copy(), type='EDGE', action='ENABLE', use_extend=True)
        bpy.ops.mesh.select_mode(bpy.context.copy(), type='FACE', action='ENABLE', use_extend=True)
        bpy.ops.mesh.select_all(action='SELECT')

        bpy.ops.wm.tool_set_by_id(bpy.context.copy(), name="builtin.select_box")  # force a benign select tool

        # create a bmesh to operate on
        self.bm = bmesh.from_edit_mesh(self.context.object.data)
        self.bm.verts.ensure_lookup_table()

        # create BVH tree for ray_casting
        self.bvh_tree = BVHTree.FromBMesh(self.bm)

        # store viewports
        self.viewports = [a for a in self.context.screen.areas if a.type == 'VIEW_3D']

        for viewport in self.viewports:
            self.color_type = viewport.spaces[0].shading.color_type
            self.shading_type = viewport.spaces[0].shading.type
            viewport.spaces[0].shading.type = 'SOLID'
            viewport.spaces[0].shading.color_type = 'VERTEX'

        # setup UI variables

        self.tools = {
            "select": ("Select (TODO : Select tool)", "select.png", "Select liquid area"),
            "grab": ("Raise / Lower (G)", "raise_lower.png", "Raise \ Lower liquid surface"),
            "rotate": ("Rotate (R)", "rotate.png", "Rotate liquid area"),
            "equalize": ("Equalize (E)", "equalize.png", "Equalize liquid level"),
            "flag": ("Edit flags (F)", "flags.png", "Mark flags on the liquid grid. Hold Shift to unmark"),
        }

        self.variable_1 = BoundFloat('''options['variable_1']''', min_value=0.5, max_value=15.5)
        self.variable_2 = BoundInt('''self.variable_2_gs''', min_value=0, max_value=10)
        self.variable_3 = BoundBool('''options['variable_3']''')

        self.x_size = BoundInt('''options['x_size']''', min_value=1, max_value=100000) # uint32, is there a limit ?
        self.y_size = BoundInt('''options['y_size']''', min_value=1, max_value=100000)

        self.brush_size = BoundInt('''options['brush_size']''', min_value=1, max_value=4)

        self.flag_1 = BoundBool('''flags['flag_1']''')
        self.flag_2 = BoundBool('''flags['flag_2']''')
        self.flag_3 = BoundBool('''flags['flag_3']''')

        self.blender_ui_set()
        self.setup_ui()

    def blender_ui_set(self):
        self.viewaa_simplify()
        self.manipulator_hide()
        self._space.show_gizmo = True
        self.panels_hide()
        #self.region_darken()

    def update_ui(self):
        self.ui_main.dirty('update', parent=True, children=True)

    def select_tool(self, action):

        tool_id = "tool-{}".format(action)

        e = self.document.body.getElementById('tool-{}'.format(tool_id))
        if e: e.checked = True

        self.active_tool = action

        self.update_ui()

    def setup_ui(self):

        reload_stylings()

        self.ui_main = ui.framed_dialog(label='Liquid Editor',
                                        resizable=None,
                                        resizable_x=True,
                                        resizable_y=False,
                                        closeable=False,
                                        moveable=True,
                                        hide_on_close=True,
                                        parent=self.document.body)

        # tools
        ui_tools = ui.div(id="tools", parent=self.ui_main)

        def add_tool(action="", name="", icon="", title=""):
            nonlocal ui_tools
            nonlocal self
            # must be a fn so that local vars are unique and correctly captured
            lbl, img = name, icon

            radio = ui.input_radio(id='tool-{}'.format(action), value=lbl.lower(), title=title, name="tool",
                                   classes="tool", checked=False, parent=ui_tools)
            radio.add_eventListener('on_input', delay_exec('''if radio.checked: self.select_tool("{}")'''.format(action)))
            ui.img(src=img, parent=radio, title=title)
            ui.label(innerText=lbl, parent=radio, title=title)

        for key, value in self.tools.items(): add_tool(action=key, name=value[0], icon=value[1], title=value[2])

        # ui.button(label='ui.button', title='self.tool_action() method linked to button', parent=ui_tools,
        #           on_mouseclick=self.tool_action)
        

        # create a collapsille container to hold a few variables
#        container = ui.collapsible('ui.collapse container', parent=self.ui_main)
#
#        i1 = ui.labeled_input_text(label='Sui.labeled_input_text',
#                                   title='float property to BoundFLoat',
#                                   value=self.variable_1)
#
#        i2 = ui.labeled_input_text(label='ui.labled_input_text',
#                                   title='integer property to BoundInt',
#                                   value=self.variable_2)
#
#        i3 = ui.input_checkbox(
#            label='ui.input_checkbox',
#            title='True/False property to BoundBool')
#
#        container.builder([i1, i2, i3])

        size_container = ui.collapsible('Liquid Size', parent=self.ui_main, collapsed=False)

        j1 = ui.labeled_input_text(label='X subdivisions',
                                   title='Amount of WoW liquid planes in a row. One plane is 4.1666625 in its radius.',
                                   value=self.x_size)

        j2 = ui.labeled_input_text(label='Y subdivisions',
                                   title='Amount of WoW liquid planes in a row. One plane is 4.1666625 in its radius.',
                                   value=self.y_size)

        # j3 = ui.button(label='Apply size', on_mouseclick=self.set_grid_size)
        j3 = ui.button(label='Apply size ( Not implemented yet)')

        size_container.builder([j1, j2, j3])

        self.get_grid_size()

        flags_brush_size = ui.labeled_input_text(label='Flags brush size', parent=ui_tools,
                                   title='Size of the brush used to paint flags, from 1 to 4. Also press K/shift+K to set/unset all the liquid.',
                                   value=self.brush_size)

        chk_flag_1 = ui.input_checkbox(
            label='No Render flag', parent=ui_tools,
            title='Set "No Render" as the flag to set/unset',
            on_mouseclick=lambda: self.set_editable_flag(1),
            value = self.flag_1)
        
        chk_flag_2 = ui.input_checkbox(
            label='Fishing flag', parent=ui_tools,
            title='Set "Fishing" as the flag to set/unset',
            on_mouseclick=lambda: self.set_editable_flag(2),
            value = self.flag_2)

        chk_flag_3 = ui.input_checkbox(
            label='Fatigue Flag', parent=ui_tools,
            title='Set "Fatigue" as the flag to set/unset',
            on_mouseclick=lambda: self.set_editable_flag(3),
            value = self.flag_3)

        self.flag_checkboxes = [chk_flag_1, chk_flag_2, chk_flag_3]
        chk_flag_1.checked = True
        self.mesh.vertex_colors.get("flag_0").active = True
        
        ui.button(label='Sculpt liquid', title="Sculpt the Liquid mesh, locked in Z edit.", parent=ui_tools,
                  on_mouseclick=self.activate_sculpt_mode)

    def set_editable_flag(self, flag): # TODO : come up with a better solution

        if flag == 1:
            self.mesh.vertex_colors.get("flag_0").active = True
            if self.flag_checkboxes[0].checked:
                return
            else:
                self.flag_checkboxes[1].checked = False
                self.flag_checkboxes[2].checked = False
        elif flag == 2:
            self.mesh.vertex_colors.get("flag_6").active = True
            if self.flag_checkboxes[1].checked:
                # self.flag_checkboxes[1].checked = True
                return
            else:
                # self.flag_2.set(False)
                self.flag_checkboxes[0].checked = False
                # self.flag_3.set(False)
                self.flag_checkboxes[2].checked = False
        elif flag == 3:
            self.mesh.vertex_colors.get("flag_7").active = True
            if self.flag_checkboxes[2].checked:
                # self.flag_checkboxes[2].checked = True
                return
            else:
                self.flag_checkboxes[0].checked = False
                self.flag_checkboxes[1].checked = False

    def get_grid_size(self):

        x_tiles = round(self.context.object.dimensions[0] / 4.1666625)
        y_tiles = round(self.context.object.dimensions[1] / 4.1666625)
        self.x_size.set(x_tiles)
        self.y_size.set(y_tiles)

    def set_grid_size(self):
        start_vertex = 0
        sum = 0
        for vertex in self.context.object.data.vertices:
            cur_sum = vertex.co[0] + vertex.co[1]

            if cur_sum < sum:
                start_vertex = vertex.index
                sum = cur_sum

        old_x_tiles = round(self.context.object.dimensions[0] / 4.1666625)
        old_y_tiles = round(self.context.object.dimensions[1] / 4.1666625)
        old_x_verts = old_x_tiles + 1
        old_y_verts = old_y_tiles + 1
        position = self.context.object.data.vertices[start_vertex].co.to_tuple()
        
        if old_x_tiles == self.x_size.get() and old_y_tiles == self.y_size.get():
            return
        
        # create each missing vert (for in newmax tile - cur tile)

        x_verts = self.x_size.get()+1
        y_verts = self.y_size.get()+1

        vertices = []
        for y in range(old_y_verts, y_verts):
            y_pos = position[1] + y * 4.1666625
            for x in range(old_x_verts, x_verts):
                x_pos = position[1] + x * 4.1666625
                vertices.append((x_pos, y_pos, position[2]))

        # calculate faces
        indices = []
        for y in range(self.y_size.get()):
            for x in range(self.x_size.get()):
                indices.append(y * x_verts + x)
                indices.append(y * x_verts + x + 1)
                indices.append((y + 1) * y_verts + x)
                indices.append((y + 1) * y_verts + x + 1)

        faces = []

        for i in range(0, len(indices), 4):
            faces.append((indices[i], indices[i + 1], indices[i + 3], indices[i + 2]))

        bpy.ops.object.mode_set(mode='OBJECT')

        print(len(vertices))

        print(len(faces))

        name = "_Liquid"
        mesh = bpy.data.meshes.new(name)
        # obj = bpy.data.objects.new(name, mesh)
# 
        # # create mesh from python data
        mesh.from_pydata(vertices, [], faces)
        mesh.update(calc_edges=True)
        mesh.validate()

        # self.bm.verts

        bm = bmesh.new()
        bm.from_mesh(mesh)

        bpy.ops.object.mode_set(mode='EDIT')

        bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)


    def should_pass_through(self, context, event):

        # allow selection events to pass through
        return True if event.type in {'A', 'B', 'C'} else False

    def tool_action(self):
        print('tool action')
        return
    
    def activate_sculpt_mode(self):
        bpy.ops.object.mode_set(mode='SCULPT')

        for viewport in self.viewports:
            viewport.spaces[0].shading.type = self.shading_type
            viewport.spaces[0].shading.color_type = self.color_type
        self.done(cancel=False)
        return

    def activate_tool(self, name):
        self.active_tool = name
        e = self.document.body.getElementById('tool-{}'.format(self.active_tool))
        if e: e.checked = True


    def update_bmesh(self):
        self.bm = bmesh.from_edit_mesh(self.context.object.data)
        self.bm.verts.ensure_lookup_table()

    def select_all_verts(self):
        # for v in self.mesh:
        #     v.select = True
        bpy.ops.mesh.select_all(action='SELECT')
    
    def unselect_all_verts(self):
        bpy.ops.mesh.select_all(action='DESELECT')

    @CookieCutter.FSM_State('main', 'enter')
    def enter_main(self):
        self.update_bmesh()

    @CookieCutter.FSM_State('main')
    def modal_main(self):

        self.context.area.tag_redraw()
        Drawing.set_cursor('DEFAULT')

        if self.actions.pressed('grab') or self.active_tool == 'grab':
            bpy.ops.mesh.select_all(action='SELECT')
            self.activate_tool('grab')

            Drawing.set_cursor('MOVE_X')
            self.init_loc = self.event.mouse_x
            self.selected_verts = {vert: vert.co[2] for vert in self.bm.verts if vert.select}

            return 'grab'

        elif self.actions.pressed('rotate') or self.active_tool == 'rotate':
            self.activate_tool('rotate')

            self.report({'INFO'}, "Rotating vertices. Shift + Scroll - tilt | Alt + Scroll - rotate")
            bpy.ops.mesh.select_all(action='SELECT')

            self.selected_verts = {vert: vert.co[2] for vert in self.bm.verts if vert.select}
            self.median = get_median_point(self.bm)
            self.orientation = 0.0
            self.angle = 0.0

            return 'rotate'

        elif self.actions.pressed('equalize') or self.active_tool == 'equalize':
            bpy.ops.mesh.select_all(action='SELECT')
            self.activate_tool('equalize')
            return 'equalize'

        elif self.actions.pressed('flag') or self.active_tool == 'flag':
            bpy.ops.mesh.select_all(action='DESELECT')
            self.activate_tool('flag')
            
            return 'flag'

        elif self.actions.pressed('cancel') and (time() - self.init_time) > 0.5:

            bpy.ops.object.mode_set(mode='OBJECT')

            for viewport in self.viewports:
                viewport.spaces[0].shading.type = self.shading_type
                viewport.spaces[0].shading.color_type = self.color_type

            DepsgraphLock().pop()
            self.done(cancel=False)
            return 'finished'

        else:
            self.activate_tool('select')
            # return 'select'

    @CookieCutter.FSM_State('select')
    def modal_select(self):
        if self.active_tool != 'select':
            return 'main'

        if self.actions.pressed('cancel') and (time() - self.init_time) > 0.5:

            bpy.ops.object.mode_set(mode='OBJECT')

            for viewport in self.viewports:
                viewport.spaces[0].shading.type = self.shading_type
                viewport.spaces[0].shading.color_type = self.color_type

            DepsgraphLock().DEPSGRAPH_UPDATE_LOCK = False

            self.done(cancel=False)
            return 'finished'

    @CookieCutter.FSM_State('grab')
    def modal_grab(self):

        if self.active_tool != 'grab':
            return 'main'
        else:
            self.activate_tool('grab')

        # alter vertex height
        if self.actions.mousemove:

            fac = 10 if self.actions.shift else 30
            for vert, height in self.selected_verts.items():
                vert.co[2] = height + (self.event.mouse_x - self.init_loc) / fac

            bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)

        # accept
        if self.actions.event_type == 'LEFTMOUSE':
            self.active_tool = 'select'
            return 'main'

        # cancel
        elif self.actions.event_type == 'RIGHTMOUSE':

            for vert, height in self.selected_verts.items():
                vert.co[2] = height

                bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)

            self.active_tool = 'select'

            return 'main'

        # switch state
        for action in self.default_keymap.keys():

            if self.actions.pressed(action):
                self.update_bmesh()
                self.activate_tool(action)
                return action

        return 'grab'

    @CookieCutter.FSM_State('rotate')
    def modal_rotate(self):

        if self.active_tool != 'rotate':
            return 'main'

        Drawing.set_cursor('SCROLL_Y')

        if self.actions.event_type == 'WHEELUPMOUSE':

            if self.actions.shift:
                self.angle = min(self.angle + 5, 89.9)
                align_vertices(self.bm, self.context.object.data, self.median, self.angle, self.orientation)

            elif self.actions.alt:
                self.orientation += 10

                if self.orientation > 360:
                    self.orientation -= 360

                align_vertices(self.bm, self.context.object.data, self.median, self.angle, self.orientation)

        elif self.actions.event_type == 'WHEELDOWNMOUSE':

            if self.actions.shift:
                self.angle = max(self.angle - 5, -89.9)
                align_vertices(self.bm, self.context.object.data, self.median, self.angle, self.orientation)

            elif self.actions.alt:
                self.orientation -= 10

                if self.orientation < 0:
                    self.orientation = 360 - self.orientation

                align_vertices(self.bm, self.context.object.data, self.median, self.angle, self.orientation)

        # accept
        if self.actions.event_type == 'LEFTMOUSE':
            self.active_tool = 'select'
            return 'main'

        # cancel
        elif self.actions.event_type == 'RIGHTMOUSE':

            for vert, height in self.selected_verts.items():
                vert.co[2] = height

                bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)

            self.active_tool = 'select'

            return 'main'

        # switch state
        for action in self.default_keymap.keys():

            if self.actions.pressed(action):
                self.update_bmesh()
                self.activate_tool(action)
                return action

        return 'rotate'

    @CookieCutter.FSM_State('equalize')
    def equalize(self):

        median = get_median_point(self.bm)

        for vert in self.bm.verts:
            if vert.select:
                vert.co[2] = median[2]

        bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)
        self.report({'INFO'}, "Equalized vertex height")

        self.active_tool = 'select'

        return 'main'

    @CookieCutter.FSM_State('flag')
    def modal_flag(self):

        if self.active_tool != 'flag':
            return 'main'

        Drawing.set_cursor('PAINT_BRUSH')

        # if self.actions.event_type in event_keymap.keys():
 
        #     flag_number = event_keymap.get(self.actions.event_type, 0)
        #     layer = self.mesh.vertex_colors.get("flag_{}".format(flag_number))
        #     layer.active = True

        layer = self.bm.loops.layers.color.active
        color = (0, 0, 255, 255) if not self.actions.shift else (255, 255, 255, 255)

        if self.actions.event_type == 'K':
            bpy.ops.mesh.select_all(action='SELECT') # Remove when selecting tool is fixed
            for face in self.bm.faces:
                if face.select:
                    for loop in face.loops:
                        loop[layer] = color

            bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)
            bpy.ops.mesh.select_all(action='DESELECT')
            self.report({'INFO'}, "Flag unset" if self.actions.shift else "Flag set")

        if not self.actions.released('paint'):

            # TODO: radius brush

            # get the context arguments
            region = self.context.region
            rv3d = self.context.region_data
            coord = self.event.mouse_region_x, self.event.mouse_region_y

            # get the ray from the viewport and mouse
            view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

            ray_target = ray_origin + view_vector

            ray_origin_obj = self.obj.matrix_world.inverted() @ ray_origin
            ray_target_obj = self.obj.matrix_world.inverted() @ ray_target

            ray_direction_obj = ray_target_obj - ray_origin_obj

            # cast the ray

            location, normal, face_index, distance = self.bvh_tree.ray_cast(ray_origin_obj, ray_direction_obj)

            if face_index is not None:
                color = (0, 0, 255, 255) if not self.actions.shift else (255, 255, 255, 255)

                face = self.bm.faces[face_index]

                ############
                # This is extremly innefficient, capped the variable at 3 or it lags too much.
                # TODO : find a betetr way
                faces_list = []
                faces_list.append(face)

                size_count = 1
                while size_count < self.brush_size.get():
                    curr_faces = faces_list.copy()
                    for face in faces_list:
                        for vert in face.verts:
                            linked_faces = vert.link_faces
                            for linked_face in linked_faces:
                                curr_faces.append(linked_face)
                    size_count += 1
                    
                    for curr_face in curr_faces:
                        faces_list.append(curr_face)

                for face in faces_list:
                    for loop in face.loops:
                        loop[layer] = color
                ##############

                # for loop in face.loops:
                #     loop[layer] = color

                bmesh.update_edit_mesh(self.mesh, loop_triangles=True, destructive=True)

        if self.actions.event_type == 'RIGHTMOUSE':
            self.active_tool = 'select'
            return 'main'
        else:
          return 'flag'



class WMO_OT_add_liquid(bpy.types.Operator):
    bl_idname = 'scene.wow_add_liquid'
    bl_label = 'Add liquid'
    bl_description = 'Add a WoW liquid plane'
    bl_options = {'REGISTER', 'UNDO'}

    x_planes:  bpy.props.IntProperty(
        name="X subdivisions:",
        description="Amount of WoW liquid planes in a row. One plane is 4.1666625 in its radius.",
        default=10,
        min=1
    )

    y_planes:  bpy.props.IntProperty(
        name="Y subdivisions:",
        description="Amount of WoW liquid planes in a column. One plane is 4.1666625 in its radius.",
        default=10,
        min=1
    )

    def execute(self, context):

        liquid_collection = get_wmo_collection(context.scene, SpecialCollections.Liquids)
        if not liquid_collection:
            self.report({'WARNING'}, "Can't add WMO Liquid: No WMO Object Collection found in the scene.")
            return {'FINISHED'}

        bpy.ops.mesh.primitive_grid_add(x_subdivisions=self.x_planes,
                                        y_subdivisions=self.y_planes,
                                        size=4.1666625
                                        )

        water = bpy.context.view_layer.objects.active
        bpy.ops.transform.resize(value=(self.x_planes, self.y_planes, 1.0))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        water.name += "_Liquid"

        mesh = water.data

        water.wow_wmo_liquid.enabled = True
        # move to collection
        liquid_collection.objects.link(water)

        bit = 1
        counter = 0
        while bit <= 0x80:
            vc_layer = mesh.vertex_colors.new(name="flag_{}".format(counter))

            # set flag 7 which is very likely related to swimming and not fishing (it's enabled in most liquids, even lava)
            if bit == 0x40:
                for poly in mesh.polygons:
                    for loop in poly.loop_indices:
                        vc_layer.data[loop].color = (0, 0, 255, 255)

            counter += 1
            bit <<= 1


        water.hide_set(False if "4" in bpy.context.scene.wow_visibility else True)

        self.report({'INFO'}, "Successfully created WoW liquid: {}".format(water.name))
        return {'FINISHED'}
