from ..config import ADDON_MODULE_NAME

from typing import Optional, List, Tuple
import bpy


def get_addon_preferences() -> 'WBS_AP_Preferences':
    """
    Gets current Blender addon preferences for this addon in any context.
    :return: Addon preferences.
    """
    return bpy.context.preferences.addons[ADDON_MODULE_NAME].preferences


def get_project_preferences() -> Optional['WBS_PG_ProjectPreferences']:
    """
    Gets current project preferences in any context.
    :return: Project preferences or None.
    """
    addon_preferences = get_addon_preferences()

    if not len(addon_preferences.projects):
        raise UserWarning("No active project. Check WBS settings.")

    return addon_preferences.projects[addon_preferences.active_project_index]


class WBS_UL_Projects(bpy.types.UIList):
    """ UI List displaying currently saved projects. """

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.3)
        split.prop(item, "name", text="", emboss=False, translate=False
                   , icon='RADIOBUT_ON' if index == data.active_project_index else 'RADIOBUT_OFF')

    def invoke(self, context, event):
        ...

class WBS_PG_ExportMethodSetting(bpy.types.PropertyGroup):
    """ Property group for individual export method settings. """

    name: bpy.props.StringProperty(
        name="Export Setting Name",
        description="Name of the export folder setting"
    )

    value: bpy.props.StringProperty(
        name="Export Directory Path",
        description="Value of the export folder setting",
        subtype='DIR_PATH'
    )

class WBS_PG_ProjectPreferences(bpy.types.PropertyGroup):
    """ Property group holding data for project preferences set. """

    wow_path: bpy.props.StringProperty(
        name="WoW Client Path",
        subtype='DIR_PATH'
    )

    wmv_path: bpy.props.StringProperty(
        name="WoW Model Viewer Log Path",
        subtype='FILE_PATH'
    )

    wow_export_path: bpy.props.StringProperty(
        name="WoW Export Runtimelog Path", 
        subtype='FILE_PATH'
    )

    noggit_red_path: bpy.props.StringProperty(
        name="Noggit Red log Path",
        subtype='FILE_PATH'
    )

    time_import_method: bpy.props.EnumProperty(
        name="Time Conversion Import Method",
        items=[
            ('Convert', "Convert to 30 FPS", "(WBS Method)"),
            ('Keep Original', "Keep_Original", "Don't convert timestamps"),
        ],
        default='Convert',
        description="Choose the preferred method for timestamp import."
    )

    import_method: bpy.props.EnumProperty(
        name="Import Method",
        items=[
            ('WMV', "WMV", "Use WoW Model Viewer"),
            ('WowExport', "WowExport", "Use WoW Export"),
            ('NoggitRed', "NoggitRed", "Use Noggit Red"),
        ],
        default='WMV',
        description="Choose the preferred method of import for WoW files."
    )

    export_method_settings: bpy.props.CollectionProperty(
        type=WBS_PG_ExportMethodSetting,
        name="Export Folder Settings",
        description="Settings for the export methods"
    )

    export_dir_path: bpy.props.StringProperty(
        name="Export Directory Path",
        description="A directory for WBS to export M2/WBS, could be ascension Data client, or a patch folder inside it.",
        subtype="DIR_PATH"
    )

    active_export_method_index: bpy.props.IntProperty(default=0)

    def update_export_dir_path(self, context):
        method = self.export_method_settings[int(self.export_method_enum)]
        self.active_export_method_index = int(self.export_method_enum)
        self.export_dir_path = method.value
        
    def export_method_items(self, context) -> List[Tuple[str, str, str]]:
        return [(str(i), method.name, "") for i, method in enumerate(self.export_method_settings)]

    export_method_enum: bpy.props.EnumProperty(
        name="Export Method",
        description="Select Export Method",
        items=export_method_items,
        update=update_export_dir_path
    )

    cache_dir_path: bpy.props.StringProperty(
        name="Cache Directory Path",
        description="Any folder that can be used to store textures and other temporary files.",
        subtype="DIR_PATH"
    )

    project_dir_path: bpy.props.StringProperty(
        name="Project Directory Path",
        description="A directory Blender saves WoW files to and treats it as top-priority patch.",
        subtype="DIR_PATH"
    )

    merge_vertices: bpy.props.BoolProperty(
        name="Merge Vertices Algorythm when quick saving M2's",
        description="Use the merge vertices algorythm when quick saving m2's with topbar button",
        default=True
    )

class WBS_OT_ProjectListActions(bpy.types.Operator):
    """
    Moves items up and down the list of projects, adds or removes.
    """

    bl_idname = "wbs.project_list_action"
    bl_label = "List Actions"
    bl_description = "Move items up and down, add and remove"
    bl_options = {'REGISTER', 'INTERNAL'}

    action: bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REMOVE', "Remove", ""),
            ('ADD', "Add", ""),
            ('DUPLICATE', "Duplicate", "")))

    @classmethod
    def description(cls, context, properties):
        match properties.action:
            case 'UP':
                return "Move project up the list"
            case 'DOWN':
                return "Move project down the list"
            case 'ADD':
                return "Add new project"
            case 'DUPLICATE':
                return "Duplicate current project"            
            case 'REMOVE':
                return "Remove project from the list"
            case _:
                raise NotImplementedError()

    def duplicate_project(self, source, target):
        target.name = f"{source.name}_copy"
        target.wow_path = source.wow_path
        target.wmv_path = source.wmv_path
        target.wow_export_path = source.wow_export_path
        target.noggit_red_path = source.noggit_red_path
        target.time_import_method = source.time_import_method
        target.import_method = source.import_method
        target.cache_dir_path = source.cache_dir_path
        target.project_dir_path = source.project_dir_path
        target.export_dir_path = source.export_dir_path
        target.merge_vertices = source.merge_vertices

        for setting in source.export_method_settings:
            new_setting = target.export_method_settings.add()
            new_setting.name = setting.name
            new_setting.value = setting.value

    def invoke(self, context, event):
        addon_prefs = get_addon_preferences()
        idx = addon_prefs.active_project_index

        match self.action:
            case 'DOWN':
                if idx < len(addon_prefs.projects) - 1:
                    addon_prefs.projects.move(idx, idx + 1)
                    addon_prefs.active_project_index += 1
            case 'UP':
                if idx >= 1:
                    addon_prefs.projects.move(idx, idx - 1)
                    addon_prefs.active_project_index -= 1
            case 'REMOVE':
                if len(addon_prefs.projects):
                    addon_prefs.active_project_index -= 1
                    addon_prefs.projects.remove(idx)
            case 'ADD':
                item = addon_prefs.projects.add()
                item.name = 'New project'
                addon_prefs.active_project_index = len(addon_prefs.projects) - 1
            case 'DUPLICATE':
                if len(addon_prefs.projects):
                    source = addon_prefs.projects[idx]
                    target = addon_prefs.projects.add()
                    self.duplicate_project(source, target)
                    addon_prefs.active_project_index = len(addon_prefs.projects) - 1

        return {"FINISHED"}

class WBS_UL_Export(bpy.types.UIList):
    """ UI List displaying currently saved export methods. """

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.3)
        split.prop(item, "name", text="", emboss=False, translate=False
                   , icon='RADIOBUT_ON' if index == data.active_export_method_index else 'RADIOBUT_OFF')

    def invoke(self, context, event):
        ...

class WBS_OT_ExportMethodActions(bpy.types.Operator):
    """
    Adds or removes export method settings.
    """

    bl_idname = "wbs.export_method_action"
    bl_label = "Export Method Actions"
    bl_description = "Add or remove export method settings"
    bl_options = {'REGISTER', 'INTERNAL'}

    action: bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('ADD', "Add", ""),
            ('REMOVE', "Remove", "")))
        
    @classmethod
    def description(cls, context, properties):
        match properties.action:
            case 'UP':
                return "Move project up the list"
            case 'DOWN':
                return "Move project down the list"
            case 'ADD':
                return "Add new export method setting"
            case 'REMOVE':
                return "Remove selected export method setting"
            case _:
                raise NotImplementedError()

    def invoke(self, context, event):
        proj_prefs = get_project_preferences()
        idx = proj_prefs.active_export_method_index

        match self.action:
            case 'DOWN':
                if idx < len(proj_prefs.export_method_settings) - 1:
                    proj_prefs.export_method_settings.move(idx, idx + 1)
                    proj_prefs.active_export_method_index += 1
            case 'UP':
                if idx >= 1:
                    proj_prefs.export_method_settings.move(idx, idx - 1)
                    proj_prefs.active_export_method_index -= 1            
            case 'ADD':
                item = proj_prefs.export_method_settings.add()
                item.name = 'New setting'
                item.value = ''
                proj_prefs.active_export_method_index = len(proj_prefs.export_method_settings) - 1
            case 'REMOVE':
                if len(proj_prefs.export_method_settings):
                    proj_prefs.export_method_settings.remove(idx)
                    proj_prefs.active_export_method_index -= 1

        return {"FINISHED"}

class WBS_AP_Preferences(bpy.types.AddonPreferences):
    """
    Stores global preferences for the addon.
    """

    bl_idname = 'io_scene_wmo'

    projects: bpy.props.CollectionProperty(
        type=WBS_PG_ProjectPreferences,
        name='Projects',
        description='Project presets.',
        options=set()
    )

    active_project_index: bpy.props.IntProperty(default=0)

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        row = layout.row()
        row.template_list('WBS_UL_Projects', '', self, 'projects', self, 'active_project_index', rows=2)

        col = row.column(align=True)
        col.operator("wbs.project_list_action", text="Create project").action = 'ADD'
        col.operator("wbs.project_list_action", text="Duplicate project").action = 'DUPLICATE'
        col.operator("wbs.project_list_action", text="Remove project").action = 'REMOVE'
        col.separator()
        col.operator("wbs.project_list_action", icon='TRIA_UP', text="").action = 'UP'
        col.operator("wbs.project_list_action", icon='TRIA_DOWN', text="").action = 'DOWN'
        col.separator()

        if proj_prefs := get_project_preferences():
            col = layout.column(align=True)
            col.label(text='Project settings:', icon='SETTINGS')
            box = col.box()
            box.prop(proj_prefs, 'wow_path')
            box.prop(proj_prefs, 'time_import_method')
            box.prop(proj_prefs, 'import_method')
            if proj_prefs.import_method == 'WMV':
                box.prop(proj_prefs, 'wmv_path')
            elif proj_prefs.import_method == 'WowExport':
                box.prop(proj_prefs, 'wow_export_path')  
            elif proj_prefs.import_method == 'NoggitRed':
                box.prop(proj_prefs, 'noggit_red_path')                 
            box.prop(proj_prefs, 'cache_dir_path')
            box.prop(proj_prefs, 'project_dir_path')
            box.prop(proj_prefs, 'export_method_enum', text='Export Directory Path')

            col = layout.column(align=True)
            col.label(text='Export Folder Settings:', icon='SETTINGS')
            row = col.row()
            row.template_list('WBS_UL_Export', '', proj_prefs, 'export_method_settings', proj_prefs, 'active_export_method_index')

            sub_col = row.column(align=True)
            sub_col.operator("wbs.export_method_action", text="", icon='ADD').action = 'ADD'
            sub_col.operator("wbs.export_method_action", text="", icon='REMOVE').action = 'REMOVE'

            sub_col.operator("wbs.export_method_action", icon='TRIA_UP', text="").action = 'UP'
            sub_col.operator("wbs.export_method_action", icon='TRIA_DOWN', text="").action = 'DOWN'

            if proj_prefs.export_method_settings:
                setting = proj_prefs.export_method_settings[proj_prefs.active_export_method_index]
                box = col.box()
                box.prop(setting, 'name')
                box.prop(setting, 'value')
            col.separator()
            col = layout.column(align=True)
            col.label(text='M2 Quick Save Settings:', icon='SETTINGS')
            box = col.box()
            box.prop(proj_prefs, 'merge_vertices', text='Merge Vertices')                