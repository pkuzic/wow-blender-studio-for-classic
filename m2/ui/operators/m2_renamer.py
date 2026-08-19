import bpy
        
class M2RenameOperator(bpy.types.Operator):
    """Rename object, all groups and fcurve data_path"""
    bl_idname = "object.m2_bone_renamer"
    bl_label = "M2 Bone Renamer"
    bl_options = {'REGISTER', 'UNDO_GROUPED'}

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="Prefix add will be added to all objects",
        default="default_",
        maxlen=1024,
        )
    
    rename_armature: bpy.props.BoolProperty(
        name="Rename Armature",
        description="Should the selected armature be renamed?",
        default = False
        )
        
    rename_objects: bpy.props.BoolProperty(
        name="Rename All Objects",
        description="Rename all Scene Objects?",
        default = False
        ) 

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "prefix", text='Prefix')
        layout.prop(self, "rename_armature", text='Rename Armature')
        layout.prop(self, "rename_objects", text='Rename Objects')

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)
        
    def execute(self, context):
        prefix = self.prefix
        rename_armature = self.rename_armature
        rename_objects = self.rename_objects

        obj = context.object

        if obj is None:
            self.report({"WARNING"}, "No object selected! Aborting action...")
            return {'FINISHED'}
        
        if obj.type != 'ARMATURE':
            self.report({"WARNING"}, "Selected object is not a rig (Armature)! Aborting action...")
            return {'FINISHED'}
        
        #Rename Armature
        if rename_armature and not obj.name.startswith(prefix):
            obj.name = prefix + obj.name

        #Rename Objects
        if rename_objects:
            for object in bpy.data.objects:
                if object != obj and not object.name.startswith(prefix):
                    object.name = prefix + object.name

        #Rename Bones
        if hasattr(obj.data, 'bones') and len(obj.data.bones) > 0:
            for bone in obj.data.bones:
                if not bone.name.startswith(prefix):
                    bone.name = prefix + bone.name     

        #Rename FCurves
        for action in bpy.data.actions:
            for group in action.groups:
                if not group.name.startswith(prefix):
                    oldname = group.name
                    group.name = prefix + oldname
                    for fcurve in group.channels:
                        fcurve.data_path = fcurve.data_path.replace(oldname, group.name)
                        
        return {'FINISHED'}