import bpy
import json
import os
from pathlib import Path                        
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty
from bpy_extras.io_utils import ExportHelper

from ..wmo.import_wmo import import_wmo_to_blender_scene
from ..wmo.export_wmo import export_wmo_from_blender_scene
from ..m2.import_m2 import import_m2
from ..m2.export_m2 import export_m2, create_m2
from ..utils.misc import load_game_data
from ..utils.collections import get_current_wow_model_collection, SpecialCollection                                                                                   
from ..ui.preferences import get_project_preferences

#############################################################
######                 Common operators                ######
#############################################################


class WBS_OT_texture_transparency_toggle(bpy.types.Operator):
    bl_idname = 'wow.toggle_image_alpha'
    bl_label = 'Toggle texture transparency'
    bl_description = 'Toggle texture transparency (useful for working in solid mode)'
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.label(text="This will overwrite alpha settings for images. Continue?")

    def execute(self, context):

        for image in bpy.data.images:
            if image.library is not None:
                continue
            image.alpha_mode = 'NONE' if image.alpha_mode in ('PREMUL', 'CHANNEL_PACKED', 'STRAIGHT') else 'STRAIGHT'

        return {'FINISHED'}


class WBS_OT_reload_game_data(bpy.types.Operator):
    bl_idname = 'scene.reload_wow_filesystem'
    bl_label = 'Reload WoW filesystem'
    bl_description = 'Re-establish connection to World of Warcraft client files'
    bl_options = {'REGISTER'}

    def execute(self, context):

        if hasattr(bpy, "wow_game_data"):
            if bpy.wow_game_data.files:
                for storage, type_ in bpy.wow_game_data.files:
                    if type_:
                        storage.close()

            delattr(bpy, "wow_game_data")

        load_game_data()

        if not bpy.wow_game_data.files:
            self.report({'ERROR'}, "WoW game data is not loaded. Check settings.")
            return {'CANCELLED'}

        self.report({'INFO'}, "WoW game data is reloaded.")

        return {'FINISHED'}

class WBS_OT_save_current_wmo(bpy.types.Operator):
    bl_idname = 'scene.save_current_wmo_collection'
    bl_label = 'Save current WMO object'
    bl_description = "Save the currently selected WMO collection to the Project Folder as a .wmo file using the collection's [Directory Path]."
    bl_options = {'REGISTER'}

    # will save the first wmo collection found for now until wmo scene is changed to an export class
    def execute(self, context):
        scene = context.scene
        if scene and scene.wow_scene.type == 'WMO':

            version = int(scene.wow_scene.version)

            wmo_collection = get_current_wow_model_collection(scene, 'wow_wmo')
            if not bpy.context.collection:
                self.report({'ERROR'}, 'No Collection selected.')
                return {'CANCELLED'}
            
            # act_col: bpy.types.Collection = bpy.context.collection
            # SpecialCollection._get_root_collection(context.scene)

            if not wmo_collection:
                self.report({'ERROR'}, 'Could not find a WoW WMO collection.')
                return {'CANCELLED'}
            
            if not wmo_collection.wow_wmo.dir_path:
                self.report({'WARNING'}, 'WMO Collection ' + wmo_collection.name + ' has empty WoW directory path. \
                                            \nWMO will be saved at the root of the project.')
            
            project_preferences = get_project_preferences()
            if not project_preferences.export_dir_path:
                self.report({'ERROR'}, 'Export path in addon preferences is empty.')
                return {'CANCELLED'}

            # Doesn't work if wow_wmo.dir_path is a full path with Disk name etc, happens if WMO has been imported from local file.
            dir_path = os.path.join(project_preferences.export_dir_path, wmo_collection.wow_wmo.dir_path)
            # dir_path = project_preferences.project_dir_path # temporary so we don't override the old file
            filename = Path(wmo_collection.name).stem + '.wmo'
            filepath = os.path.join(dir_path, filename)

            print("saving wmo to : " + filepath)
            export_wmo_from_blender_scene(filepath, version, False, 'FULL')
            return {'FINISHED'}

        self.report({'ERROR'}, 'Invalid scene type.')
        return {'CANCELLED'}

class WBS_OT_save_current_m2(bpy.types.Operator):
    bl_idname = 'scene.save_current_m2'
    bl_label = 'Save current M2 object'
    bl_description = "Save the currently selected M2 to the Export Folder as a .m2 file using the Scene [Game Path]."
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        if scene and scene.wow_scene.type == 'M2':

            version = int(scene.wow_scene.version)
            
            project_preferences = get_project_preferences()
            if not project_preferences.export_dir_path:
                self.report({'ERROR'}, 'Export path in addon preferences is empty.')
                return {'CANCELLED'}

            scene_gamepath = scene.wow_scene.game_path.replace('/', '\\')
            dir_path = os.path.join(project_preferences.export_dir_path, os.path.dirname(scene_gamepath))
            os.makedirs(dir_path, exist_ok=True)
            filename = os.path.basename(scene_gamepath)
            filepath = os.path.join(dir_path, filename)

            print("Saving M2 to : " + filepath)
            export_m2(version, filepath, selected_only = False, fill_textures = True, forward_axis = 'X+', scale = 1.0, merge_vertices = True)
            return {'FINISHED'}

        self.report({'ERROR'}, 'Invalid scene type.')
        return {'CANCELLED'}        

#############################################################
######             Import/Export Operators             ######
#############################################################


class WBS_OT_wmo_import(bpy.types.Operator):
    """Load WMO mesh data"""
    bl_idname = "import_mesh.wmo"
    bl_label = "Import WMO"
    bl_options = {'UNDO', 'REGISTER'}

    filepath: StringProperty(
        subtype='FILE_PATH',
        )

    filter_glob: StringProperty(
        default="*.wmo",
        options={'HIDDEN'}
        )

    import_lights: BoolProperty(
        name="Import lights",
        description="Import WMO lights to scene",
        default=True,
        )

    import_doodads: BoolProperty(
        name="Import doodads",
        description='Import WMO doodads to scene',
        default=True
    )

    import_fogs: BoolProperty(
        name="Import fogs",
        description="Import WMO fogs to scene",
        default=True,
        )

    group_objects: BoolProperty(
        name="Group objects",
        description="Group all objects of this WMO on import",
        default=False,
        )

    def execute(self, context):
        version = int(context.scene.wow_scene.version)

        import_wmo_to_blender_scene(self.filepath, version)
        context.scene.wow_scene.type = 'WMO'
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}


class WBS_OT_wmo_export(bpy.types.Operator, ExportHelper):
    """Save WMO mesh data"""
    bl_idname = "export_mesh.wmo"
    bl_label = "Export WMO"
    bl_options = {'PRESET', 'REGISTER'}

    filename_ext = ".wmo"

    filter_glob: StringProperty(
        default="*.wmo",
        options={'HIDDEN'}
    )

    export_method: EnumProperty(
        name='Export Method',
        description='Partial export if the scene was exported before and was not critically modified',
        items=[('FULL', 'Full', 'Full'),
               ('PARTIAL', 'Partial', 'Partial')
               ]
    )

    export_selected: BoolProperty(
        name="Export selected objects",
        description="Export only selected objects on the scene",
        default=False,
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'export_method', expand=True)

        if self.export_method == 'FULL':
            layout.prop(self, 'export_selected')

    def execute(self, context):
        if context.scene and context.scene.wow_scene.type == 'WMO':

            if self.export_method == 'PARTIAL' and context.scene.wow_wmo_root_elements.is_update_critical:
                self.report({'ERROR'}, 'Partial export is not available. The changes are critical.')
                return {'CANCELLED'}

            version = int(context.scene.wow_scene.version)

            export_wmo_from_blender_scene(self.filepath, version, self.export_selected, self.export_method)
            return {'FINISHED'}

        self.report({'ERROR'}, 'Invalid scene type.')
        return {'CANCELLED'}

class WBS_OT_blp_load_from_game(bpy.types.Operator):
    """Load BLP from game data"""
    bl_idname = "load.blp"
    bl_label = "Load BLP from game data"
    bl_options = {'UNDO','REGISTER'}

    blp_file: StringProperty()
    imported_name: StringProperty()

    def execute(self, context):
        game_data = load_game_data()
        project_preferences = get_project_preferences()

        if not project_preferences.cache_dir_path:
            raise Exception('Error: cache directory is not specified. Check addon settings.')
        
        if game_data and game_data.files:
            files = game_data.extract_textures_as_png(project_preferences.cache_dir_path, [self.blp_file])
            for key,value in files.items():
                img = bpy.data.images.load(os.path.join(value))
                if self.imported_name:
                    img.name = self.imported_name
                else:
                    img.name = os.path.basename(key)
            return {'FINISHED'}
        else:
            raise NotImplementedError('Error: Importing without gamedata loaded is not yet implemented.')

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "blp_file", text="BLP File")

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class WBS_OT_m2_import(bpy.types.Operator):
    """Load M2 data"""
    bl_idname = "import_mesh.m2"
    bl_label = "Import M2"
    bl_options = {'UNDO', 'REGISTER'}

    filepath: StringProperty(
        subtype='FILE_PATH',
        )

    filter_glob: StringProperty(
        default="*.m2",
        options={'HIDDEN'}
        )

    def execute(self, context):
        project_preferences = get_project_preferences()
        time_import_method = project_preferences.time_import_method

        if time_import_method == 'Convert':
            bpy.context.scene.render.fps = 30
            bpy.context.scene.sync_mode = 'NONE'
        else:
            bpy.context.scene.render.fps = 1000
            bpy.context.scene.sync_mode = 'FRAME_DROP'
            
        import_m2(int(context.scene.wow_scene.version), self.filepath, True, time_import_method)      
        context.scene.wow_scene.type = 'M2'
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}

class WBS_OT_m2_export(bpy.types.Operator, ExportHelper):
    """Save M2 mesh data"""
    bl_idname = "export_mesh.m2"
    bl_label = "Export M2"
    bl_options = {'PRESET', 'REGISTER'}

    filename_ext = ".m2"

    filter_glob: StringProperty(
        default="*.m2",
        options={'HIDDEN'}
    )

    export_selected: BoolProperty(
        name="Export selected objects",
        description="Export only selected objects on the scene",
        default=False,
        )

    version: EnumProperty(
        name="Version",
        description="Version of World of Warcraft",
        items=[('264', 'WOTLK', "")],
        default='264'
    )

    forward_axis: EnumProperty(
        name="Forward Axis",
        description="The direction the exported model is facing",
        items=[('X+','X+',''), ('X-','X-',''), ('Y+','Y+',''), ('Y-','Y-','')],
        default='X+'
    )

    scale: FloatProperty (
        name="Scale",
        description="How much to scale the output model",
        default=1.0
    )

    autofill_textures: BoolProperty(
        name="Fill texture paths",
        description="Automatically assign texture paths based on texture filenames",
        default=True
        )
    
    merge_vertices: BoolProperty(
        name="Merge vertices",
        description="Execute merge vertices algorithm for splitting uv islands after",
        default=True
    )

    def execute(self, context):
        if context.scene:
            context.scene.wow_scene.type = 'M2'
            export_m2(int(context.scene.wow_scene.version), self.filepath, self.export_selected, self.autofill_textures, self.forward_axis, self.scale, self.merge_vertices)
            return {'FINISHED'}

        self.report({'ERROR'}, 'Invalid scene type.')

class WBS_OT_M2_test(bpy.types.Operator):
    """Read M2 file and compare output with input"""
    bl_idname = "test.m2"
    bl_label = "Test M2"
    bl_options = {'UNDO', 'REGISTER'}

    filepath: StringProperty(
        subtype='FILE_PATH',
        )

    filter_glob: StringProperty(
        default="*.m2",
        options={'HIDDEN'}
        )

    def execute(self, context):
        m2_in = import_m2(int(context.scene.wow_scene.version), self.filepath)
        context.scene.wow_scene.type = 'M2'
        m2_out = create_m2(int(context.scene.wow_scene.version), self.filepath, False, False,'X+',1)

        def objectify(obj_in,visited_stack = []):
            def is_primitive(type_in):
                return type_in in ['bool','float','int','str']

            def has_visited(obj):
                for value in visited_stack:
                    if obj is value:
                        return True
                return False

            obj_type = type(obj_in).__name__
            def skip_field(typename,fieldname):
                if obj_type == 'M2CompBone':
                    return fieldname in ['name','index','parent','children']
                pass

            def transform(value):
                if obj_type == 'M2Array':
                    return value['values']
                if obj_type == 'Array':
                    return value['values']
                else:
                    return value

            if obj_type == 'Vector':
                return (obj_in.x,obj_in.y,obj_in.z) if hasattr(obj_in,'z') else (obj_in.x,obj_in.y)

            if obj_type == 'Quaternion':
                return (obj_in.w,obj_in.x,obj_in.y,obj_in.z)

            if is_primitive(obj_type):
                return obj_in

            visited_stack.append(obj_in)

            if obj_type == 'list' or obj_type == 'tuple':
                list_out = []
                for value in obj_in:
                    value_type = type(value).__name__
                    if not is_primitive(type(value).__name__):
                        if has_visited(value):
                            continue
                        value = objectify(value, visited_stack)
                    list_out.append(value)
                return list_out
            else:
                obj_out = {}
                for key in dir(obj_in):
                    if skip_field(obj_type,key):
                        continue
                    if key.startswith('__'):
                        continue
                    if not hasattr(obj_in,key):
                        continue
                    value = getattr(obj_in,key)
                    if callable(value):
                        continue
                    if not is_primitive(type(value).__name__):
                        if has_visited(value):
                            continue
                        value = objectify(value, visited_stack)
                    obj_out[key] = value
                return transform(obj_out)

        def diff(obj1,obj2):
            if type(obj1) != type(obj2):
                return f'TypeError({str(type(obj1))},{str(type(obj2))}) ({obj1},{obj2})'
            dtype = type(obj1)
            if dtype is dict:
                diffObj = {}
                for k in obj1:
                    if not k in obj2:
                        diffObj[k] = 'LeftOnly'
                    else:
                        diffVal = diff(obj1[k],obj2[k])
                        if not diffVal is None:
                            diffObj[k] = diffVal
                for k in obj2:
                    if not k in obj1:
                        diffObj[k] = 'RightOnly'
                return diffObj if len(diffObj) > 0 else None
            elif dtype is list or dtype is tuple:
                diffObj = {}
                if len(obj1) != len(obj2):
                    diffObj["len"] = str(len(obj1)) + " != " + str(len(obj2))
                for i in range(min(len(obj1),len(obj2))):
                    diffVal = diff(obj1[i],obj2[i])
                    if not diffVal is None:
                        if not "values" in diffObj:
                            diffObj["values"] = {}
                        diffObj["values"][i] = diffVal
                return diffObj if len(diffObj) > 0 else None
            else:
                return str(obj1) + ' != ' + str(obj2) if obj1 != obj2 else None

        with open(self.filepath+".json",'w') as f:
            f.write(json.dumps(diff(objectify(m2_in),objectify(m2_out)),indent=4))
        m2_out.write(self.filepath[:-2]+"out.m2")
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}

class WBS_OT_M2_Print_Warnings(bpy.types.Operator):
    """Print Warnings for M2 Exports"""
    bl_idname = "print_warnings.m2"
    bl_label = "Find common problems with exported M2 models and print warnings about them"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import importlib
        from ..m2.operations import m2_export_warnings
        importlib.reload(m2_export_warnings)
        m2_export_warnings.print_warnings()
        return {'FINISHED'}

class WBS_OT_M2_ConvertBones(bpy.types.Operator):
    """Convert Bones and Animation Tracks To WoW-style bones"""
    bl_idname = "convert_bones.m2"
    bl_label = "Convert Bones to WoW"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import importlib
        from ..m2.operations import convert_m2_bones
        importlib.reload(convert_m2_bones)
        convert_m2_bones.convert_m2_bones()
        return {'FINISHED'}

'''
Created on Dec 30, 2019

@author: Patrick
'''
'''
Copyright (C) 2018 CG Cookie
https://github.com/CGCookie/retopoflow
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import bpy
from ..addon_common.cookiecutter.cookiecutter import CookieCutter

from ..addon_common.common import ui
from ..addon_common.common.drawing import Drawing

from ..addon_common.common.boundvar import BoundInt, BoundFloat, BoundBool

# some settings container
options = {}
options["variable_1"] = 10.0
options["variable_3"] = True


# override this pass through to allow anything in 3dview to pass through
def in_region(reg, x, y):
    # first, check outside of area
    if x < reg.x: return False
    if y < reg.y: return False
    if x > reg.x + reg.width: return False
    if y > reg.y + reg.height: return False

    return True


class CookieCutter_UITest(CookieCutter, bpy.types.Operator):
    bl_idname = "view3d.cookiecutter_ui_test"
    bl_label = "CookieCutter UI Test (Example)"

    default_keymap = {
        'commit': 'RET',
        'cancel': 'ESC',
        'test': 'LEFTMOUSE'
    }

    # for this, checkout "polystrips_props.py'
    @property
    def variable_2_gs(self):
        return getattr(self, '_var_cut_count_value', 0)

    @variable_2_gs.setter
    def variable_2_gs(self, v):
        if self.variable_2 == v: return
        self.variable_2 = v
        # if self.variable_2.disabled: return

    ### Redefine/OVerride of defaults methods from CookieCutter ###
    def start(self):
        opts = {
            'pos': 9,
            'movable': True,
            'bgcolor': (0.2, 0.2, 0.2, 0.8),
            'padding': 0,
        }

        # some data storage, simple single variables for now
        # later, more coplex dictionaries or container class
        self.variable_1 = BoundFloat('''options['variable_1']''', min_value=0.5, max_value=15.5)
        self.variable_2 = BoundInt('''self.variable_2_gs''', min_value=0, max_value=10)
        self.variable_3 = BoundBool('''options['variable_3']''')

        self.setup_ui()

    # def update(self):
    # self.ui_action.set_label('Press: %s' % (','.join(self.actions.now_pressed.keys()),))

    def end_commit(self):
        pass

    def end_cancel(self):
        pass

    def end(self):  # happens after end_commit or end_cancel
        pass

    def should_pass_through(self, context, event):
        print(context.region.type)
        print(context.area.type)

        if context.area.type != "VIEW_3D":
            return True

        # first, check outside of area
        outside = False
        if event.mouse_x < context.area.x: outside = True
        if event.mouse_y < context.area.y: outside = True
        if event.mouse_x > context.area.x + context.area.width: outside = True
        if event.mouse_y > context.area.y + context.area.height: outside = True

        if outside:
            print('outside the 3DView area')
            return True

        # make sure we are in the window region, not the header, tools or UI
        for reg in context.area.regions:
            if in_region(reg, event.mouse_x, event.mouse_y) and reg.type != "WINDOW":
                print('in wrong region')
                return True


        return False

    ######## End Redefinitions from CookieCutter Class ###

    # typically, we would definte these somewhere else
    def tool_action(self):
        print('tool action')
        return

    def setup_ui(self):

        # go ahead and open these files
        # addon_common.common.ui
        # addon_common.cookiecutter.cookiecutter_ui

        # know that every CookieCutter instance has self.document upon startup
        # most of our ui elements are going to be children of self.document.body

        # we generate our UI elements using the methods in ui.py

        # we need to read ui_core, particulalry UI_Element

        # collapsible, and framed_dialog
        # first, know

        self.ui_main = ui.framed_dialog(label='ui.framed_dialog',
                                        resiable=None,
                                        resiable_x=True,
                                        resizable_y=False,
                                        closeable=True,
                                        moveable=True,
                                        hide_on_close=True,
                                        parent=self.document.body)

        # tools
        ui_tools = ui.div(id="tools", parent=self.ui_main)
        ui.button(label='ui.button', title='self.tool_action() method linked to button', parent=ui_tools,
                  on_mouseclick=self.tool_action)

        # create a collapsille container to hold a few variables
        container = ui.collapsible('ui.collapse container', parent=self.ui_main)

        i1 = ui.labeled_input_text(label='Sui.labeled_input_text',
                                   title='float property to BoundFLoat',
                                   value=self.variable_1)

        i2 = ui.labeled_input_text(label='ui.labled_input_text',
                                   title='integer property to BoundInt',
                                   value=self.variable_2)

        i3 = ui.input_checkbox(
            label='ui.input_checkbox',
            title='True/False property to BoundBool')

        container.builder([i1, i2, i3])

    @CookieCutter.FSM_State('main')
    def modal_main(self):
        Drawing.set_cursor('DEFAULT')

        if self.actions.pressed('test'):
            self.actions.pass_through = False
            print('aaaaaaaaaand action \n\n')
            return 'test'

        if self.actions.pressed('cancel'):
            print('cancelled')
            self.done(cancel=True)
            return 'cancel'

        if self.actions.pressed('commit'):
            print('committed')
            self.done()
            return 'finished'

    @CookieCutter.FSM_State('test')
    def modal_grab(self):
        Drawing.set_cursor('CROSSHAIR')

        self.actions.unuse('navigate')
        if self.actions.mousemove:
            print('action mousemove!')
            self.report({'INFO'}, "Applied")
            return 'test'  # can return nothing and stay in this state?

        if self.actions.released('test'):
            # self.lbl.set_label('finish action')
            print('finish action')
            return 'main'

    # there are no drawing methods for this example
    # this is all buttons and input wundows


class M2DrawingTest(bpy.types.Operator):
    bl_idname = "wm.render_test"
    bl_label = "M2 Render Test"

    def execute(self, context):

        from render.drawing_manager import DrawingManager

        dm = DrawingManager(handler_mode=True)
        dm.queue_for_drawing(bpy.context.view_layer.objects.active)

        return {'FINISHED'}


class TestBPYBoost(bpy.types.Operator):
    bl_idname = "wm.bpy_boost_test"
    bl_label = "BPY Boost Test"

    def execute(self, context):

        from ..wbs_kernel.wbs_kernel.bpy_boost import BMesh, Window, create_ui_popup

        ds = bpy.context.evaluated_depsgraph_get()
        obj = bpy.context.view_layer.objects.active

        '''
        object_eval = obj.evaluated_get(ds)
        if object_eval:
            mesh = object_eval.to_mesh()

            if mesh:
                # TODO test if this makes sense
                # If negative scaling, we have to invert the normals
                # if not mesh.has_custom_normals and object_eval.matrix_world.determinant() < 0.0:
                #     # Does not handle custom normals
                #     mesh.flip_normals()

                mesh.calc_loop_triangles()
                if not mesh.loop_triangles:
                    object_eval.to_mesh_clear()
                    mesh = None

            if mesh:
                if mesh.use_auto_smooth:
                    if not mesh.has_custom_normals:
                        mesh.calc_normals()
                    mesh.split_faces()

                mesh.calc_loop_triangles()

                if mesh.has_custom_normals:
                    mesh.calc_normals_split()

            ptr = mesh.loop_triangles[0].as_pointer()

        '''
        ptr = obj.data.as_pointer()
        bl_mesh = BMesh(ptr)
        bl_mesh.get_mesh_geometry_batches_raw()

        print('window')

        ptr = context.as_pointer()

        #Window(ptr, 1, "WoW Render Preview")
        create_ui_popup(ptr)

        return {'FINISHED'}



