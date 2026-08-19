import bpy

from ..enums import ANIMATION_FLAGS
from ....pywowlib.enums.m2_enums import M2SequenceNames
from ....pywowlib import WoWVersions


###############################
## User Interface
###############################
class M2_Animation_IDS:

    context = None
    m2_sequence_names = M2SequenceNames()
    anim_ids = m2_sequence_names.get_anim_ids(context)

# TODO: hacky way to display the right indices in the ui panel
def resolve_alias_next(alias_next):
    alias_ctr = -1
    for i,anim in enumerate(bpy.context.scene.wow_m2_animations):
        if not anim.is_global_sequence:
            alias_ctr+=1
        if alias_ctr == alias_next:
            return i,anim
    return -1,None

def get_non_global_sequence_animations(animations):
    """Returns a list of animations that are not global sequences."""
    return [anim for anim in animations if not anim.is_global_sequence]

def n_global_sequences():
    g_sequences = sum(1 for anim in bpy.context.scene.wow_m2_animations if anim.is_global_sequence)
    return g_sequences
    
#### Pop-up dialog ####

class M2_OT_animation_editor_dialog(bpy.types.Operator):
    bl_idname = 'scene.wow_animation_editor_toggle'
    bl_label = 'WoW M2 Animation Editor'

    is_playing_anim = False

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=820)

    def draw(self, context):
        layout = self.layout
        split = layout.split(factor=0.5)

        # Top row - collections: animations, objects
        # Animations column

        col = split.column()
        col.label(text='Animations:', icon='SEQUENCE')

        row = col.row()
        sub_col1 = row.column()
        sub_col1.template_list("M2_UL_animation_editor_animation_list", "", context.scene, "wow_m2_animations", context.scene,
                               "wow_m2_cur_anim_index")
        sub_col_parent = row.column()
        sub_col2 = sub_col_parent.column(align=True)
        sub_col2.operator("scene.wow_m2_animation_editor_seq_add", text='', icon='ADD')
        sub_col2.operator("scene.wow_m2_animation_editor_seq_duplicate", text='', icon='DUPLICATE')
        sub_col2.operator("scene.wow_m2_animation_editor_seq_remove", text='', icon='REMOVE')

        sub_col_parent.separator()

        sub_col3 = sub_col_parent.column(align=True)
        sub_col3.operator("scene.wow_m2_animation_editor_seq_move", text='', icon='TRIA_UP').direction = 'UP'
        sub_col3.operator("scene.wow_m2_animation_editor_seq_move", text='', icon='TRIA_DOWN').direction = 'DOWN'

        sub_col_parent.separator()

        sub_col4 = sub_col_parent.column(align=True)
        sub_col4.operator("scene.wow_m2_animation_editor_seq_cleanup", text='', icon='GHOST_DISABLED')

        # Objects column

        col = split.column()
        col.label(text='Objects:', icon='OBJECT_DATA')

        cur_anim_track = None

        try:
            cur_anim_track = context.scene.wow_m2_animations[context.scene.wow_m2_cur_anim_index]

        except IndexError:
            pass

        cur_anim_pair = None

        if cur_anim_track and context.scene.wow_m2_cur_anim_index >= 0:

            row = col.row()
            sub_col1 = row.column()

            sub_col1.template_list("M2_UL_animation_editor_sequence_object_list", "", cur_anim_track, "anim_pairs",
                                   cur_anim_track, "active_object_index")
            sub_col2 = row.column(align=True)
            sub_col2.operator("scene.wow_m2_animation_editor_object_add", text='', icon='ADD')
            sub_col2.operator("scene.wow_m2_animation_editor_object_remove", text='', icon='REMOVE')

            try:
                cur_anim_pair = cur_anim_track.anim_pairs[cur_anim_track.active_object_index]
            except IndexError:
                pass
        else:
            col.label(text='No sequence selected.', icon='ERROR')

        # Lower row of top layout: active item editing properties
        split = layout.split(factor=0.5)
        col = split.column()

        if cur_anim_track and context.scene.wow_m2_cur_anim_index >= 0:
            row = col.row()
            row_split = row.split(factor=0.935)
            row_split = row_split.row(align=True)
            row_split.prop(cur_anim_track, "playback_speed", text='Speed')

            if context.scene.sync_mode == 'AUDIO_SYNC' and context.user_preferences.system.audio_device == 'JACK':
                sub = row_split.row(align=True)
                sub.scale_x = 2.0
                sub.operator("screen.animation_play", text="", icon='PLAY')

            row = row_split.row(align=True)
            if not context.screen.is_animation_playing:
                if context.scene.sync_mode == 'AUDIO_SYNC' and context.user_preferences.system.audio_device == 'JACK':
                    sub = row.row(align=True)
                    sub.scale_x = 2.0
                    sub.operator("screen.animation_play", text="", icon='PLAY')
                else:
                    row.operator("screen.animation_play", text="", icon='PLAY_REVERSE').reverse = True
                    row.operator("screen.animation_play", text="", icon='PLAY')
            else:
                sub = row.row(align=True)
                sub.scale_x = 2.0
                sub.operator("screen.animation_play", text="", icon='PAUSE')

            row = row_split.row(align=True)
            row.operator("scene.wow_m2_animation_editor_seq_deselect", text='', icon='ARMATURE_DATA')

            if cur_anim_pair:

                col = split.column()

                row_split = col.row().split(factor=0.93)
                row = row_split.row(align=True)
                row_split = row.split(factor=0.30)
                row_split.row().label(text='Object' if cur_anim_pair.type == 'OBJECT' else 'Scene')
                row = row_split.row(align=True)
                row.prop(cur_anim_pair, "type", text="", expand=True)

                if cur_anim_pair.type == 'OBJECT':
                    row.prop(cur_anim_pair, "object", text='')

                    if cur_anim_pair.object:
                        row.row().operator("scene.wow_m2_animation_editor_select_object",
                                            text='', icon='ZOOM_SELECTED').name = cur_anim_pair.object.name
                    else:
                        sub_row = row.row()
                        sub_row.enabled = False
                        sub_row.label(text="", icon='ZOOM_SELECTED')
                else:
                    row.prop(cur_anim_pair, "scene", text='')

                row_split = col.row().split(factor=0.93)
                row = row_split.row(align=True)
                col = row.column()
                col.scale_x = 0.54
                col.label(text="Action:")

                col = row.column(align=True)
                col.scale_x = 1.0 if cur_anim_pair.action else 1.55
                col.template_ID(cur_anim_pair, "action", new="scene.wow_m2_animation_editor_action_add",
                                unlink="scene.wow_m2_animation_editor_action_unlink")

            else:
                # Draw a placeholder row layout to avoid constant window resize

                col = split.column()

                row = col.row()
                row_split = row.split(factor=0.88)
                row_split.label(text="Object: no object selected")

                row = col.row()
                row_split = row.split(factor=0.88)
                row_split.label(text="Action: no action available")

            # Lower row: animation and blender playback properties

            row = layout.row()
            row.separator()
            layout.row().label(text="Animation properties", icon='SETTINGS')

            split = layout.split(factor=0.5)

            col = split.column()
            col.separator()
            col.prop(cur_anim_track, 'is_global_sequence', text='Global sequence')

            col = col.column()
            col.enabled = not cur_anim_track.is_global_sequence

            row = col.row(align=True)
            row.label(text="Animation ID: ")
            row.operator("scene.wow_m2_animation_id_search", text=M2_Animation_IDS.anim_ids[int(cur_anim_track.animation_id)][1],
                         icon='VIEWZOOM')

            col.prop(cur_anim_track, 'move_speed', text="Move speed")

            if int(context.scene.wow_scene.version) >= WoWVersions.WOD:
                col.prop(cur_anim_track, 'blend_time_in', text="Blend time in")
                col.prop(cur_anim_track, 'blend_time_out', text="Blend time out")
            else:
                col.prop(cur_anim_track, 'blend_time', text="Blend time")

            col.prop(cur_anim_track, 'frequency', text="Frequency (%)")

            col.label(text='Random repeat:')
            col.prop(cur_anim_track, 'replay_min', text="Min")
            col.prop(cur_anim_track, 'replay_max', text="Max")

            col.label(text='Relations:')
            row1 = col.row(align=True)
            row1.prop(cur_anim_track, 'VariationNext', text='Next animation')
            row1.operator("scene.wow_m2_animation_editor_go_to_index", text="", icon='ZOOM_SELECTED').anim_index = \
                resolve_alias_next(cur_anim_track.VariationNext)[0]

            row = col.row(align=True)
            row.enabled = cur_anim_track.is_alias
            row.label(text='', icon='FILE_TICK' if resolve_alias_next(cur_anim_track.alias_next)[1] is not None else 'ERROR')
            row.prop(cur_anim_track, 'alias_next', text="Next alias")
            row.operator("scene.wow_m2_animation_editor_go_to_index", text="", icon='ZOOM_SELECTED').anim_index = \
                resolve_alias_next(cur_anim_track.alias_next)[0]

            col.label(text='Bounds:')
            row = col.row(align=True)
            row.enabled = not cur_anim_track.is_global_sequence
            row.prop(cur_anim_track, 'use_preset_bounds')
            row = col.row(align=True)
            row.enabled = not cur_anim_track.is_global_sequence and cur_anim_track.use_preset_bounds
            row.prop(cur_anim_track, 'preset_bounds_min_x')
            row.prop(cur_anim_track, 'preset_bounds_min_y')
            row.prop(cur_anim_track, 'preset_bounds_min_z')
            row = col.row(align=True)
            row.enabled = not cur_anim_track.is_global_sequence and cur_anim_track.use_preset_bounds
            row.prop(cur_anim_track, 'preset_bounds_max_x')
            row.prop(cur_anim_track, 'preset_bounds_max_y')
            row.prop(cur_anim_track, 'preset_bounds_max_z')
            row = col.row(align=True)
            row.enabled = not cur_anim_track.is_global_sequence and cur_anim_track.use_preset_bounds
            row.prop(cur_anim_track, 'preset_bounds_radius')

            col = split.column()
            col.enabled = not cur_anim_track.is_global_sequence
            col.label(text='Flags:')
            col.separator()
            col.prop(cur_anim_track, 'flags', text="Flags")
            col.separator()
            col.prop(cur_anim_track, 'use_preset_duration', text='Use Preset Duration')
            col.prop(cur_anim_track, 'duration', text='Duration')

    def check(self, context):  # redraw the popup window
        return True


class M2_OT_animation_editor_id_search(bpy.types.Operator):
    bl_idname = "scene.wow_m2_animation_id_search"
    bl_label = "Search animation ID"
    bl_description = "Select WoW M2 animation ID"
    bl_options = {'REGISTER', 'INTERNAL'}
    bl_property = "animation_id"

    animation_id:  bpy.props.EnumProperty(items=M2_Animation_IDS.anim_ids)

    def execute(self, context):

        context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index].animation_id = self.animation_id

        # refresh UI after setting the property
        for region in context.area.regions:
            if region.type == "UI":
                region.tag_redraw()

        self.report({'INFO'}, "Animation ID set successfully.")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"FINISHED"}


#### UI List layouts ####

# Animation List

def update_animation_collection(self, context):

    anim_ids = M2_Animation_IDS.anim_ids
    index_cache = {}

    num_global_sequences = n_global_sequences()

    for i, anim in enumerate(bpy.context.scene.wow_m2_animations):
        anim_id = int(anim.animation_id) if not anim.is_global_sequence else -1
        last_idx = index_cache.get(anim_id)

        if last_idx is not None:
            anim.chain_index = last_idx + 1
            index_cache[anim_id] += 1
        else:
            anim.chain_index = 0
            index_cache[anim_id] = 0

        if not anim.is_global_sequence:
            if not anim.is_alias:
                anim.name = "#{} {} ({})".format(i - num_global_sequences, anim_ids[int(anim.animation_id)][1], anim.chain_index)
            else:
                anim.name = "#{} {} ({}) -> #{}".format(i - num_global_sequences, anim_ids[int(anim.animation_id)][1],
                                                        anim.chain_index, resolve_alias_next(anim.alias_next)[0] - num_global_sequences)
        else:
            anim.name = "#{} Global Sequence ({})".format(i, anim.chain_index)


class M2_UL_animation_editor_animation_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):
        self.use_filter_show = True

        if self.layout_type in {'DEFAULT', 'COMPACT'}:

            row = layout.row()
            row.label(text=item.name, icon='SEQUENCE')

            if not item.is_global_sequence:
                if item.is_alias and len(data.wow_m2_animations) < item.alias_next:
                    row.label(text="", icon='ERROR')
                row.prop(item, "is_primary_sequence", emboss=False, text="",
                         icon='OUTLINER_OB_ARMATURE' if item.is_primary_sequence else 'ARMATURE_DATA')
                row.prop(item, "is_alias", emboss=False, text="",
                         icon='GHOST_ENABLED' if item.is_alias else 'GHOST_DISABLED')
            else:
                row.prop(item, 'stash_to_nla', emboss=False, text="",
                         icon='RESTRICT_RENDER_OFF' if item.stash_to_nla else 'RESTRICT_RENDER_ON')

            row.prop(item, "live_update", emboss=False, text="", icon='PMARKER_SEL' if item.live_update else 'PMARKER')

        elif self.layout_type in {'GRID'}:
            pass

    def filter_items(self, context, data, propname):

        col = getattr(data, propname)
        filter_name = self.filter_name.lower()

        flt_flags = [self.bitflag_filter_item
                     if any(filter_name in filter_set for filter_set in (str(i), item.name.lower()))
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


class M2_OT_animation_editor_sequence_add(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_seq_add'
    bl_label = 'Add WoW animation'
    bl_description = 'Add WoW animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        context.scene.wow_m2_animations.add()
        context.scene.wow_m2_cur_anim_index = len(context.scene.wow_m2_animations) - 1
        update_animation_collection(None, None)

        return {'FINISHED'}

class M2_OT_animation_editor_sequence_duplicate(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_seq_duplicate'
    bl_label = 'Duplicate WoW animation'
    bl_description = 'Duplicate WoW animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        anim_to_copy = context.scene.wow_m2_cur_anim_index
        context.scene.wow_m2_animations.add()
        context.scene.wow_m2_cur_anim_index = len(context.scene.wow_m2_animations) - 1
        new_anim = context.scene.wow_m2_cur_anim_index
        animation = context.scene.wow_m2_animations

        animation[new_anim].is_global_sequence = animation[anim_to_copy].is_global_sequence
        animation[new_anim].move_speed = animation[anim_to_copy].move_speed
        animation[new_anim].blend_time = animation[anim_to_copy].blend_time
        animation[new_anim].frequency = animation[anim_to_copy].frequency
        animation[new_anim].use_preset_bounds = animation[anim_to_copy].use_preset_bounds
        animation[new_anim].preset_bounds_min_x = animation[anim_to_copy].preset_bounds_min_x
        animation[new_anim].preset_bounds_min_y = animation[anim_to_copy].preset_bounds_min_y
        animation[new_anim].preset_bounds_min_z = animation[anim_to_copy].preset_bounds_min_z
        animation[new_anim].preset_bounds_max_x = animation[anim_to_copy].preset_bounds_max_x
        animation[new_anim].preset_bounds_max_y = animation[anim_to_copy].preset_bounds_max_y
        animation[new_anim].preset_bounds_max_z = animation[anim_to_copy].preset_bounds_max_z
        animation[new_anim].preset_bounds_radius = animation[anim_to_copy].preset_bounds_radius
        animation[new_anim].flags = animation[anim_to_copy].flags
        animation[new_anim].use_preset_duration = animation[anim_to_copy].use_preset_duration
        animation[new_anim].duration = animation[anim_to_copy].duration

        for i, pair in enumerate(animation[anim_to_copy].anim_pairs):
            bpy.ops.scene.wow_m2_animation_editor_object_add()

            animation[new_anim].anim_pairs[i].type = animation[anim_to_copy].anim_pairs[i].type
            if animation[new_anim].anim_pairs[i].type == 'SCENE':
                animation[new_anim].anim_pairs[i].scene =  animation[anim_to_copy].anim_pairs[i].scene
                animation[new_anim].anim_pairs[i].action =  animation[anim_to_copy].anim_pairs[i].action
            else:
                animation[new_anim].anim_pairs[i].object =  animation[anim_to_copy].anim_pairs[i].object
                animation[new_anim].anim_pairs[i].action =  animation[anim_to_copy].anim_pairs[i].action

        update_animation_collection(None, None)

        return {'FINISHED'}

class M2_OT_animation_editor_sequence_remove(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_seq_remove'
    bl_label = 'Remove WoW animation'
    bl_description = 'Remove WoW animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    # def execute(self, context):
    #     context.scene.wow_m2_animations.remove(context.scene.wow_m2_cur_anim_index)
    #     update_animation_collection(None, None)

    #     return {'FINISHED'}

    def execute(self, context):
        animations = context.scene.wow_m2_animations
        current_index = context.scene.wow_m2_cur_anim_index
        
        # Remove the animation at the current index
        animations.remove(current_index)
        
        # Adjust alias_next and VariationNext indices
        non_global_animations = get_non_global_sequence_animations(animations)
        real_index = current_index - n_global_sequences()

        for anim in non_global_animations:
            # Update alias_next
            if anim.alias_next > real_index:
                anim.alias_next -= 1
            elif anim.alias_next == real_index:
                print('Alias Animation was removed, removed Alias Flag')
                anim.alias_next = 0
                anim.is_alias = False

            # Update VariationNext
            if anim.VariationNext > real_index:
                anim.VariationNext -= 1
            elif anim.VariationNext == real_index:
                print('Next Animation in the chain was removed, next animation is now -1 (Callback)')
                anim.VariationNext = -1

        update_animation_collection(None, None)

        # If the removed animation was the last one, adjust the current index
        if current_index >= len(animations):
            context.scene.wow_m2_cur_anim_index = len(animations) - 1
        else:
            context.scene.wow_m2_cur_anim_index = current_index

        return {'FINISHED'}

class M2_OT_animation_editor_sequence_move(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_seq_move'
    bl_label = 'Move WoW animation'
    bl_description = 'Move WoW animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    direction:  bpy.props.StringProperty()

    def execute(self, context):
        animations = context.scene.wow_m2_animations
        current_index = context.scene.wow_m2_cur_anim_index
        
        non_global_animations = get_non_global_sequence_animations(animations)

        #We'll use real_index for the alias_next and variation_next properties
        real_index = current_index - n_global_sequences()

        # Determine the new index based on the move direction
        if self.direction == 'UP' and current_index > 0:
            new_index = current_index - 1
            new_real_index = real_index - 1
        elif self.direction == 'DOWN' and current_index < len(animations) - 1:
            new_index = current_index + 1
            new_real_index = real_index + 1
        else:
            raise NotImplementedError("Only UP and DOWN movement in the UI list is supported.")

        # Swap the alias_next and VariationNext indices
        for anim in non_global_animations:
            if anim.alias_next == real_index:
                anim.alias_next = new_real_index
            elif anim.alias_next == new_real_index:
                anim.alias_next = real_index

            if anim.VariationNext == real_index:
                anim.VariationNext = new_real_index
            elif anim.VariationNext == new_real_index:
                anim.VariationNext = real_index

        animations.move(current_index, new_index)
        context.scene.wow_m2_cur_anim_index = new_index
        
        update_animation_collection(None, None)

        return {'FINISHED'}

class M2_OT_animation_editor_sequence_cleanup(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_seq_cleanup'
    bl_label = 'Clean up WoW animations'
    bl_description = 'Clean up empty objects from WoW animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        for i, wow_seq in enumerate(context.scene.wow_m2_animations):
            to_remove = []
            for j, pair in enumerate(context.scene.wow_m2_animations[i].anim_pairs):
                
                if context.scene.wow_m2_animations[i].anim_pairs[j].type == 'SCENE' and context.scene.wow_m2_animations[i].anim_pairs[j].scene == None:
                    to_remove.append(j)
                elif context.scene.wow_m2_animations[i].anim_pairs[j].type == 'OBJECT' and context.scene.wow_m2_animations[i].anim_pairs[j].object == None:
                    to_remove.append(j)

            to_remove.sort(reverse=True)
                
            for index in to_remove:
                context.scene.wow_m2_animations[i].anim_pairs.remove(index)

        update_animation_collection(None, None)

        return {'FINISHED'}
    
class M2_OT_animation_editor_sequence_deselect(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_seq_deselect'
    bl_label = 'Get back to rest pose'
    bl_description = 'Deselect WoW animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        context.scene.wow_m2_cur_anim_index = -1

        for obj in context.scene.objects:
            if obj.animation_data:
                obj.animation_data.action = None

            # TODO: set to rest pose here

        return {'FINISHED'}
    
class M2_OT_animation_editor_play_global_sequence(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_play_global_sequence'
    bl_label = 'Play all global sequences along animation'
    bl_description = 'Play all global sequences'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        context.scene.wow_m2_play_global_sequences = not context.scene.wow_m2_play_global_sequences

        update_animation(self, context)

        return {'FINISHED'}    


class M2_OT_animation_editor_go_to_animation(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_go_to_index'
    bl_label = 'Go to this WoW animation'
    bl_options = {'REGISTER', 'INTERNAL'}

    anim_index:  bpy.props.IntProperty()

    def execute(self, context):
        if self.anim_index < len(context.scene.wow_m2_animations):
            context.scene.wow_m2_cur_anim_index = self.anim_index

            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Invalid animation index")
            return {'CANCELLED'}


# Object list
class M2_UL_animation_editor_sequence_object_list(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        self.use_filter_show = True

        ob = data
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row()
            if item.type == 'OBJECT' and item.object:

                icon = 'OBJECT_DATA'

                if item.object.type == 'ARMATURE':
                    icon = 'OUTLINER_OB_ARMATURE'
                elif item.object.type == 'LIGHT':
                    icon = 'LIGHT_SUN'
                elif item.object.type == 'CAMERA':
                    icon = 'RESTRICT_RENDER_OFF'
                elif item.object.type == 'EMPTY':
                    if item.object.wow_m2_attachment.enabled:
                        icon = 'CONSTRAINT'
                    elif item.object.wow_m2_event.enabled:
                        icon = 'PLUGIN'
                    elif item.object.wow_m2_camera.enabled:
                        icon = 'OUTLINER_DATA_EMPTY'
                    elif item.object.wow_m2_uv_transform.enabled:
                        icon = 'ASSET_MANAGER'
                    elif item.object.wow_m2_particle.enabled:
                        icon = 'OBJECT_DATA'

                row.label(text=item.object.name, icon=icon)
            elif item.type == 'SCENE' and item.scene:
                row.label(text=item.scene.name, icon='SCENE_DATA')
            else:
                row.label(text="Empty slot", icon='MATCUBE')

        elif self.layout_type in {'GRID'}:
            pass

    def filter_items(self, context, data, propname):

        col = getattr(data, propname)
        filter_name = self.filter_name.lower()

        flt_flags = [self.bitflag_filter_item
                     if any(filter_name in filter_set for filter_set in (str(i), item.object.name.lower()
                                                                         if item.object else 'Empty slot'))
                     else 0 for i, item in enumerate(col, 1)
                     ]

        if self.use_filter_sort_alpha:
            flt_neworder = [x[1] for x in sorted(
                zip([x[0] for x in sorted(enumerate(col),key=lambda x: x[1].object.name
                                          if x[1].object else 'Empty slot')], range(len(col)))
            )
            ]
        else:
            flt_neworder = []

        return flt_flags, flt_neworder


class M2_OT_animation_editor_object_add(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_object_add'
    bl_label = 'Add object'
    bl_description = 'Add new object to selected animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        scene = context.scene

        try:
            sequence = scene.wow_m2_animations[scene.wow_m2_cur_anim_index]
            sequence.anim_pairs.add()

        except IndexError:
            self.report({'ERROR'}, "No animation sequence selected")
            return {'CANCELLED'}

        return {'FINISHED'}


class M2_OT_animation_editor_object_remove(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_object_remove'
    bl_label = 'Remove object'
    bl_description = 'Remove object from selected animation sequence'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        scene = context.scene

        try:
            sequence = scene.wow_m2_animations[scene.wow_m2_cur_anim_index]
            sequence.anim_pairs.remove(sequence.active_object_index)

        except IndexError:
            self.report({'ERROR'}, "No animation sequence selected")
            return {'CANCELLED'}

        return {'FINISHED'}


class M2_OT_animation_editor_object_select(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_select_object'
    bl_label = 'Select object'
    bl_options = {'REGISTER', 'INTERNAL'}

    name:  bpy.props.StringProperty()

    def execute(self, context):
        bpy.data.objects[self.name].select_set(True)
        return {'FINISHED'}


class M2_OT_animation_editor_action_add(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_action_add'
    bl_label = 'Add new action'
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        scene = context.scene
        sequence = scene.wow_m2_animations[scene.wow_m2_cur_anim_index]
        anim_pair = sequence.anim_pairs[sequence.active_object_index]
        anim_pair.action = bpy.data.actions.new(name="")
        anim_pair.action.use_fake_user = True

        return {'FINISHED'}


class M2_OT_animation_editor_action_unlink(bpy.types.Operator):
    bl_idname = 'scene.wow_m2_animation_editor_action_unlink'
    bl_label = 'Unlink action'
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        sequence = context.scene.wow_m2_animations[context.scene.wow_m2_cur_anim_index]
        anim_pair = sequence.anim_pairs[sequence.active_object_index]
        return anim_pair.action is not None

    def execute(self, context):
        scene = context.scene
        sequence = scene.wow_m2_animations[scene.wow_m2_cur_anim_index]
        anim_pair = sequence.anim_pairs[sequence.active_object_index]
        anim_pair.action = None
        return {'FINISHED'}

###############################
## Property groups
###############################


def poll_object(self, obj):
    # TODO: safer polling

    if obj.name not in bpy.context.scene.objects:
        return False

    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]

    for anim_pair in sequence.anim_pairs:
        if anim_pair.object == obj:
            return False

    if obj.type not in ('CAMERA', 'ARMATURE', 'LIGHT', 'EMPTY'):
        return False

    if obj.type == 'EMPTY' and not (obj.wow_m2_uv_transform.enabled
                                    or obj.wow_m2_attachment.enabled
                                    or obj.wow_m2_event.enabled
                                    or obj.wow_m2_camera.enabled
                                    or obj.wow_m2_particle.enabled
                                    or obj.wow_m2_ribbon.enabled):
        return False

    return True

def poll_scene(self, scene):

    if scene.name != bpy.context.scene.name:
        return False

    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]

    for anim_pair in sequence.anim_pairs:
        if anim_pair.scene == scene:
            return False

    return True


def update_object(self, context):
    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
    anim_pair = sequence.anim_pairs[sequence.active_object_index]

    if anim_pair.object:
        anim_pair.object.animation_data_create()
        anim_pair.object.animation_data.action_blend_type = 'ADD'


def update_scene(self, context):
    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
    anim_pair = sequence.anim_pairs[sequence.active_object_index]

    if anim_pair.scene:
        anim_pair.scene.animation_data_create()
        anim_pair.scene.animation_data.action_blend_type = 'ADD'


def update_action(self, context):
    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
    anim_pair = sequence.anim_pairs[sequence.active_object_index]
    if anim_pair.type == 'OBJECT' and anim_pair.object and anim_pair.object.animation_data:
        anim_pair.object.animation_data.action = anim_pair.action
    elif anim_pair.type == 'SCENE' and anim_pair.scene and anim_pair.scene.animation_data:
        anim_pair.scene.animation_data.action = anim_pair.action


def update_anim_pair_type(self, context):
    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
    anim_pair = sequence.anim_pairs[sequence.active_object_index]
    if anim_pair.type == 'OBJECT':
        anim_pair.scene = None
    else:
        anim_pair.object = None


class WowM2AnimationEditorAnimationPairsPropertyGroup(bpy.types.PropertyGroup):

    type:  bpy.props.EnumProperty(
        name="Type",
        description="Defines whether object or scene is animated",
        items=[('OBJECT', "Object", "", 'OBJECT_DATA', 0),
               ('SCENE', "Scene", "", 'SCENE_DATA', 1)],
        default='OBJECT',
        update=update_anim_pair_type
    )

    object:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Object",
        description="Object to animate in this animation sequence",
        poll=poll_object,
        update=update_object
    )

    scene:  bpy.props.PointerProperty(
        type=bpy.types.Scene,
        name="Scene",
        description="Scene to animate in this animation sequence",
        poll=poll_scene,
        update=update_scene
    )

    action:  bpy.props.PointerProperty(
        type=bpy.types.Action,
        name="Action",
        description="Action to use in this animation sequence",
        update=update_action
    )


def update_playback_speed(self, context):
    sequence = bpy.context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
    context.scene.render.fps_base = sequence.playback_speed


def update_primary_sequence(self, context):
    flag_set = self.flags
    is_changed = False

    if self.is_primary_sequence and '32' not in flag_set:
        flag_set.add('32')
        is_changed = True
    elif not self.is_primary_sequence and '32' in flag_set:
        flag_set.remove('32')
        is_changed = True

    if is_changed:
        self.flags = flag_set


def update_animation_flags(self, context):
    self.is_primary_sequence = '32' in self.flags
    self.is_alias = '64' in self.flags


def update_alias(self, context):
    flag_set = self.flags
    is_changed = False

    if self.is_alias and '64' not in flag_set:
        flag_set.add('64')
        is_changed = True
    elif not self.is_alias and '64' in flag_set:
        flag_set.remove('64')
        is_changed = True

    if is_changed:
        self.flags = flag_set

    update_animation_collection(None, None)

def get_second_to_last_global_sequence_animation_index(animations):
    """Returns the index of the second-to-last found global sequence animation, or -1 if there aren't at least two."""
    found = -1
    second_to_last = -1
    
    for i in range(len(animations)):
        if animations[i].is_global_sequence:
            second_to_last = found
            found = i
    
    return second_to_last

def update_global_sequence(self, context):
    # animations = context.scene.wow_m2_animations
    # current_index = context.scene.wow_m2_cur_anim_index

    # is_global_sequence = animations[current_index].is_global_sequence

    # if is_global_sequence:
    #     last_global_animation = get_second_to_last_global_sequence_animation_index(animations) + 1

    #     if last_global_animation >= 0 and last_global_animation < len(animations):
    #         animations.move(current_index, last_global_animation)
    #         context.scene.wow_m2_cur_anim_index = last_global_animation

    update_animation_collection(None, None)

def update_stash_to_nla(self, context):
    if self.stash_to_nla and not context.scene.wow_m2_animations[context.scene.wow_m2_cur_anim_index] == self:
        for anim_pair in self.anim_pairs:
            if (anim_pair.object or anim_pair.scene) and anim_pair.action:
                obj = anim_pair.object if anim_pair.type == 'OBJECT' else anim_pair.scene

                nla_track = obj.animation_data.nla_tracks.get(anim_pair.action.name)

                if not nla_track:
                    nla_track = obj.animation_data.nla_tracks.new()
                    nla_track.is_solo = False
                    nla_track.lock = True
                    nla_track.mute = False

                nla_track.name = anim_pair.action.name

                for strip in nla_track.strips:
                    nla_track.strips.remove(strip)

                strip = nla_track.strips.new(name=anim_pair.action.name, start=0, action=anim_pair.action)
                strip.blend_type = 'ADD'

                if obj.animation_data.action:
                    strip.frame_end = obj.animation_data.action.frame_range[1]
     
    else:
        for anim_pair in self.anim_pairs:
            if (anim_pair.object or anim_pair.scene) and anim_pair.action:
                obj = anim_pair.object if anim_pair.type == 'OBJECT' else anim_pair.scene
                nla_track = obj.animation_data.nla_tracks.get(anim_pair.action.name)

                if nla_track:
                    obj.animation_data.nla_tracks.remove(nla_track)

    update_scene_frame_range()

def get_frequency_percentage(frequency):
    return (frequency / 32767) * 100

def convert_frequency_percentage(frequency):
    return (int((frequency / 100) * 32767))

class WowM2AnimationEditorPropertyGroup(bpy.types.PropertyGroup):

    # Collection

    anim_pairs:  bpy.props.CollectionProperty(type=WowM2AnimationEditorAnimationPairsPropertyGroup)

    active_object_index:  bpy.props.IntProperty(update=update_animation_collection)

    chain_index:  bpy.props.IntProperty()

    name:  bpy.props.StringProperty()

    # Playback properties

    playback_speed:  bpy.props.FloatProperty(
        name="Speed",
        description="Playback speed of this animation. Does not affect in-game playback speed.",
        min=0.1,
        max=120,
        default=1.0,
        update=update_playback_speed
    )

    stash_to_nla:  bpy.props.BoolProperty(
        name='Enable persistent playing',
        description='Enable persistent playing of this global sequences, no matter what animation is chosen',
        update=update_stash_to_nla
    )

    live_update:  bpy.props.BoolProperty(
        name='Live update',
        description='Automatically update materials that have live update turned on. May decrease FPS.'
    )

    # Layout properties
    is_primary_sequence:  bpy.props.BoolProperty(
        name='Primary sequence',
        description="If set, the animation data is in the .m2 file, else in an .anim file",
        default=True,
        update=update_primary_sequence
    )

    is_alias:  bpy.props.BoolProperty(
        name='Is alias',
        description="The animation uses transformation data from another sequence, changing its action won't affect the in-game track",
        default=False,
        update=update_alias
    )

    # Actual properties
    is_global_sequence:  bpy.props.BoolProperty(
        name="Global sequence",
        description='Global sequences are animation loops that are constantly played and blended with current animation',
        default=False
    )

    animation_id:  bpy.props.EnumProperty(
        name="animation_id",
        description="WoW Animation ID",
        items=M2_Animation_IDS.anim_ids,
        update=update_animation_collection
    )

    flags:  bpy.props.EnumProperty(
        name='Flags',
        description="WoW M2 Animation Flags",
        items=ANIMATION_FLAGS,
        options={"ENUM_FLAG"},
        default={"32"},
        update=update_animation_flags
    )

    move_speed:  bpy.props.FloatProperty(
        name="Move speed",
        description="The speed the character moves with in this animation",
        default=0.0
    )

    use_preset_duration: bpy.props.BoolProperty(
        name="Use Preset Duration",
        description="Use preset duration data instead of calculating on export",
        default=False
    )

    duration:  bpy.props.IntProperty(
        name="Duration",
        description="Duration of the animation",
        min=0
    )

    frequency:  bpy.props.FloatProperty(
        name="Frequency",
        description="This is used to determine how often the animation is played as a percentage %",
        min=0.0,
        max=100.0,
        default=100.0
    )

    replay_min:  bpy.props.IntProperty(
        name="Replay Min",
        description="Client will pick a random number of repetitions within bounds if given.",
        min=0,
        max=65535
    )

    replay_max:  bpy.props.IntProperty(
        name="Replay Max",
        description="Client will pick a random number of repetitions within bounds if given.",
        min=0,
        max=65535
    )

    VariationNext: bpy.props.IntProperty(
        name='Next Variation',
        description='Id of the following animation of this animation_id, last one should be -1',
        min=-1,
        default=-1,
        update=update_animation_collection
        
    )

    alias_next:  bpy.props.IntProperty(
        name='Alias',
        description='Index of animation used as a alias for this one',
        min=0,
        update=update_animation_collection
    )

    blend_time:  bpy.props.IntProperty(
        name="Blend time",
        description="",
        min=0,
        default=150
    )

    blend_time_in:  bpy.props.IntProperty(
        name="Blend time",
        description="",
        min=0
    )

    blend_time_out:  bpy.props.IntProperty(
        name="Blend time",
        description="",
        min=0
    )

    use_preset_bounds: bpy.props.BoolProperty(
        name="Use Preset Bounds",
        description="Use preset bounds data instead of calculating on export",
        default=False
    )

    preset_bounds_min_x: bpy.props.FloatProperty(
        name="Min X",
        description="",
        default=0,
    )

    preset_bounds_min_y: bpy.props.FloatProperty(
        name="Min Y",
        description="",
        default=0,
    )

    preset_bounds_min_z: bpy.props.FloatProperty(
        name="Min Z",
        description="",
        default=0,
    )

    preset_bounds_max_x: bpy.props.FloatProperty(
        name="Max X",
        description="",
        default=0,
    )

    preset_bounds_max_y: bpy.props.FloatProperty(
        name="Max Y",
        description="",
        default=0,
    )

    preset_bounds_max_z: bpy.props.FloatProperty(
        name="Max Z",
        description="",
        default=0,
    )

    preset_bounds_radius: bpy.props.FloatProperty(
        name="Radius",
        description="",
        default=0,
        min=0
    )


def update_scene_frame_range():
    frame_end = 0

    for obj in bpy.context.scene.objects:
        if obj.animation_data and not obj.wow_m2_event.enabled:  # TODO: wtf?

            # set scene frame range based on action length
            if obj.animation_data.action and obj.animation_data.action.frame_range[1] > frame_end:
                frame_end = obj.animation_data.action.frame_range[1]

            # set scene frame range based on camera animation length
            if obj.type == 'CAMERA' or (obj.type == 'EMPTY' and obj.wow_m2_camera.enabled):

                max_frame = 0
                for curve in obj.wow_m2_camera.animation_curves:
                    max_frame += curve.duration

                if max_frame > frame_end:
                    frame_end = max_frame

            for nla_track in obj.animation_data.nla_tracks:
                if not nla_track.mute:
                    for strip in nla_track.strips:
                        if strip.frame_end > frame_end:
                            frame_end = strip.frame_end

    # set scene frame range based on scene action length
    if bpy.context.scene.animation_data and bpy.context.scene.animation_data.action:
        if bpy.context.scene.animation_data.action.frame_range[1] > frame_end:
            frame_end = bpy.context.scene.animation_data.action.frame_range[1]

    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = int(frame_end)

    # update NLA tracks length
    for anim in bpy.context.scene.wow_m2_animations:
        if anim.is_global_sequence and anim.stash_to_nla:
            for anim_pair in anim.anim_pairs:
                if anim_pair.object and anim_pair.action:
                    nla_track = anim_pair.object.animation_data.nla_tracks.get(anim_pair.action.name)

                    if nla_track and len(nla_track.strips):
                        nla_track.strips[-1].frame_end = bpy.context.scene.frame_end


def update_animation(self, context):
    try:
        sequence = context.scene.wow_m2_animations[bpy.context.scene.wow_m2_cur_anim_index]
    except IndexError:
        return

    context.scene.render.fps_base = sequence.playback_speed

    for obj in context.scene.objects:
        if obj.animation_data:
            obj.animation_data.action = None

            if obj.type == 'ARMATURE':
                for bone in obj.pose.bones:
                    bone.location = (0, 0, 0)
                    bone.rotation_mode = 'QUATERNION'
                    bone.rotation_quaternion = (1, 0, 0, 0)
                    bone.scale = (1, 1, 1)

    for color in context.scene.wow_m2_colors:
        color.color = (0.5, 0.5, 0.5)

    for alpha in context.scene.wow_m2_color_alpha:
        alpha.value = 1.0

    for trans in context.scene.wow_m2_transparency:
        trans.value = 1.0

    if bpy.context.scene.animation_data:
        bpy.context.scene.animation_data.action = None

    global_seqs = []

    for i, anim in enumerate(context.scene.wow_m2_animations):

        if i == context.scene.wow_m2_cur_anim_index:
            for anim_pair in anim.anim_pairs:
                if anim_pair.type == 'OBJECT':
                    try:
                        anim_pair.object.animation_data.action = anim_pair.action
                    except:
                        pass
                else:
                    try:
                        anim_pair.scene.animation_data.action = anim_pair.action
                    except:
                        pass


        if anim.is_global_sequence:
            global_seqs.append(anim)

    update_scene_frame_range()      
    
    if context.scene.wow_m2_play_global_sequences:
        for i, anim in enumerate(context.scene.wow_m2_animations):
            if i == context.scene.wow_m2_cur_anim_index:
                if not anim.is_global_sequence:
                    for i, anim in enumerate(global_seqs):
                        for anim_pair in anim.anim_pairs:
                            if anim_pair.type == 'OBJECT':
                                anim_pair.object.animation_data.action = anim_pair.action

    for anim_pair in sequence.anim_pairs:
        if anim_pair.type == 'OBJECT':
            try:
                anim_pair.object.animation_data.action = anim_pair.action
            except:
                pass

    #for seq in global_seqs:
        #update_stash_to_nla(seq, bpy.context)


def register():
    bpy.types.Scene.wow_m2_animations =  bpy.props.CollectionProperty(
        type=WowM2AnimationEditorPropertyGroup,
        name="Animations",
        description="WoW M2 animation sequences"
    )

    bpy.types.Scene.wow_m2_cur_anim_index =  bpy.props.IntProperty(
        name='M2 Animation',
        description='Current WoW M2 animation',
        update=update_animation
    )

    bpy.types.Scene.wow_m2_play_global_sequences = bpy.props.BoolProperty(default=False)


def unregister():
    del bpy.types.Scene.wow_m2_animations
    del bpy.types.Scene.wow_m2_cur_anim_index
    del bpy.types.Scene.wow_m2_play_global_sequences

