from ..utils.bl_context_utils import ActiveObjectOverride
from ..ui.message_stack import MessageStack

import bpy
import inspect
import importlib
import types

from typing import Set, Iterable, Dict, Callable, Type
from types import FunctionType
from functools import wraps


class CustomObject:
    __wbs_bl_object_type__: str
    """ Type of Blender bpy.types.Object. """

    __wbs_prop_group_id__: str
    """ String name of property group in the object to control data. """

    __wbs_allowed_modes__: Set[str] = {}
    """ Blender modes allowed for this object. 'OBJECT' mode is implicitly always allowed. """

    __wbs_allow_scale__: bool = True
    """ Allow scaling of object. """

    __wbs_allow_non_uniform_scale__: bool = True
    """ Allow non-uniform scaling of object. """

    __wbs_allow_rotation__: bool = True
    """ Allow rotating the object. """

    __wbs_allow_modifiers__: bool = True
    """ Allow modifiers to be used on the object. """

    __wbs_allow_particles__: bool = True
    """ Allow particle systems to be used on the object. """

    __wbs_allow_physics__: bool = True
    """ Allow physics to influence the object. """

    __wbs_allow_constraints__: bool = True
    """ Allow particle constraints to be used on the object. """

    __wbs_allow_mesh_properties__: bool = True
    """ Allow mesh properties to be available through this object. """

    __wbs_allow_material_properties__: bool = True
    """ Allow material properties to be available through this object. """

    __wbs_banned_ops__: Iterable[str] = {}
    """ List of banned operators, that lead to post_banned_op() function fired. By default removes an object."""

    __wbs_on_mode_handlers__: Dict[str, Callable[[bpy.types.DepsgraphUpdate], None]] = {}
    """ Dict of per-mode handlers run in specific modes. """

    _required = {'__wbs_bl_object_type__', '__wbs_prop_group_id__'}
    """ Required fields to override in derived classes. """

    def __init_subclass__(cls, **kwargs):
        for requirement in cls._required:
            if not hasattr(cls, requirement):
                raise NotImplementedError(f'"{cls.__name__}" must override "{requirement}".')

        super().__init_subclass__(**kwargs)

    @classmethod
    def match(cls, obj: bpy.types.Object) -> bool:
        """
        Checks if a Blender object satisfies the criteria of a custom object type.
        :param obj: Blender object.
        :return: True if matched, else False.
        """

        # check Blender object type validity
        if cls.__wbs_bl_object_type__ != obj.type:
            return False

        # check if special property group is enabled
        try:
            if not getattr(obj, cls.__wbs_prop_group_id__).enabled:
                return False
        except AttributeError:
            pass

        # check if any other special property is enabled
        for subclass in CustomObject.__subclasses__():
            if subclass is cls:
                continue

            try:
                if getattr(obj, subclass.__wbs_prop_group_id__).enabled:
                    return False
            except AttributeError:
                pass

        return True

    @classmethod
    def handle_object_if_matched(cls
                                 , update: bpy.types.DepsgraphUpdate) -> bool:
        """
        Handles the custom object update checks.
        :param update: Depsgraph update for this object.
        :return: True if handled, else False.
        """
        obj: bpy.types.Object = update.id.original

        # skip non-matching object
        if not cls.match(obj):
            return False

        cls.on_each_update(update)

        # check if any of the banned operators ran
        if bpy.context.active_operator is not None and bpy.context.active_operator.bl_idname in cls.__wbs_banned_ops__:
            cls.on_banned_operator_use(update, bpy.context.active_operator.bl_idname)
            return True

        # make sure we are not in a prohibited mode
        if obj.mode != 'OBJECT' and obj.mode not in cls.__wbs_allowed_modes__:
            with ActiveObjectOverride(obj):
                MessageStack().push_message(msg=f'Object "{obj.name}" of custom type "{cls.__name__}" '
                                                f'cannot use mode \'{obj.mode}\'', icon='ERROR')
                bpy.ops.object.mode_set(mode='OBJECT')

            cls.on_mode_change_failure(update, obj.mode)

        # check validity of transform operations
        if update.is_updated_transform:
            # handle scale
            if not cls.__wbs_allow_scale__:
                obj.scale = (1, 1, 1)
            elif not cls.__wbs_allow_non_uniform_scale__:
                scale = (obj.scale[0] + obj.scale[1] + obj.scale[2]) / 3
                obj.scale = (scale, scale, scale)

            # handle rotation
            if not cls.__wbs_allow_rotation__:
                rot_mode = obj.rotation_mode
                obj.rotation_mode = 'XYZ'
                update.id.original.rotation_euler = (0, 0, 0)
                obj.rotation_mode = rot_mode

        # check if modifiers need cleaning
        if not cls.__wbs_allow_modifiers__ and len(obj.modifiers):
            obj.modifiers.clear()
            MessageStack().push_message(msg=f'Object "{obj.name}" of custom type "{cls.__name__}" '
                                            f'cannot use modifiers.', icon='ERROR')

        # check if particles need cleaning
        if not cls.__wbs_allow_particles__ and len(obj.particle_systems):
            obj.particle_systems.clear()
            MessageStack().push_message(msg=f'Object "{obj.name}" of custom type "{cls.__name__}" '
                                            f'cannot use particle systems.', icon='ERROR')

        # check if constraints need cleaning
        if not cls.__wbs_allow_constraints__ and len(obj.constraints):
            obj.constraints.clear()
            MessageStack().push_message(msg=f'Object "{obj.name}" of custom type "{cls.__name__}" '
                                            f'cannot use constraints.', icon='ERROR')

        # execute mode handlers
        mode_handler = cls.__wbs_on_mode_handlers__.get(update.id.original.mode)

        if mode_handler is not None:
            mode_handler(update)

        return True

    @classmethod
    def on_mode_change_failure(cls, update: bpy.types.DepsgraphUpdate, attempted_mode: str, ):
        """
        Called on attempt to enter a prohibited Blender mode. Override this to support handling this.
        :param update: Current update.
        :param attempted_mode: Attempted mode identifier.
        """
        ...

    @classmethod
    def on_banned_operator_use(cls, update: bpy.types.DepsgraphUpdate, bl_op_id_name: str):
        """
        Called after the use of a banned operator. Deletes an object by default and displays an error message.
        Override to support custom behavior.
        :param update: Current update.
        :param bl_op_id_name: Name of the executed / invoked operator.
        """
        bpy.data.objects.remove(update.id.original, do_unlink=True)

        op_class = getattr(bpy.types, bl_op_id_name)
        MessageStack().push_message(msg=f'Object "{update.id.original.name}" of custom type "{cls.__name__}" '
                                        f'was removed due to the use of prohibited action "{op_class.bl_lavel}" '
                                        f'({op_class.bl_idname}). Use undo to cancel.', icon='ERROR')

    @classmethod
    def on_each_update(cls, update: bpy.types.DepsgraphUpdate) -> bool:
        """
        Called on each update. Override for custom behavior.
        :param update: Current update.
        :return If returns True, handle_object_if_matched() proceeds to other checks, else stops after this step.
        """
        return True


class CustomObjectInterfaceHandler:
    """ This class handles patching of Blender's bpy.types.Panel subclasses to support custom context-aware polls. """

    _altered_panels: Dict[Type[bpy.types.Panel], Callable[[Type[bpy.types.Panel], bpy.types.Context], None]] = {}
    """ Panel classes and their original poll methods. """

    @staticmethod
    def copy_func(f: FunctionType, name=None):
        """
        Copies a function.
        :param f: Function to copy.
        :param name: Custom name for copied function.
        :return: a function with same code, globals, defaults, closure, and
        name (or provide a new name).
        """
        fn = types.FunctionType(f.__code__, f.__globals__, name or f.__name__,
                                f.__defaults__, f.__closure__)
        # in case f was given attrs (note this dict is a shallow copy):
        fn.__dict__.update(f.__dict__)
        return fn

    @classmethod
    def register(cls):
        """ Installs poll() hooks to matching panels. """

        for typename in dir(bpy.types):

            # skip this addon panels
            if typename.startswith('WMO') or typename.startswith('M2'):
                continue

            try:
                bpy_type_desc = getattr(bpy.types, typename)

                if not inspect.isclass(bpy_type_desc) \
                   or not issubclass(bpy_type_desc, bpy.types.Panel) \
                   or not (not hasattr(bpy_type_desc, 'bl_parent_id') or not bpy_type_desc.bl_parent_id) \
                   or bpy_type_desc.bl_context not in {'modifier'
                                                       , 'physics'
                                                       , 'particle'
                                                       , 'constraint'
                                                       , 'data'
                                                       , 'material'}:
                    continue

                bpy_module = importlib.import_module(getattr(bpy.types, typename).__module__)
                bpy_type = getattr(bpy_module, typename)
            except RuntimeError:
                continue
            except AttributeError:
                continue

            cls._altered_panels[bpy_type] = cls.copy_func(bpy_type.poll.__func__, name='poll')

        for panel, panel_poll in cls._altered_panels.items():

            @wraps(panel_poll)
            def poll_override(cls, context):
                try:
                    if not context.object:
                        return CustomObjectInterfaceHandler._altered_panels.get(cls)(cls, context)

                    for custom_obj in CustomObject.__subclasses__():
                        bl_context = cls.bl_context
                        if custom_obj.match(context.object):
                            if (not custom_obj.__wbs_allow_modifiers__ and bl_context == 'modifier') \
                                    or (not custom_obj.__wbs_allow_physics__ and bl_context == 'physics') \
                                    or (not custom_obj.__wbs_allow_particles__ and bl_context == 'particle') \
                                    or (not custom_obj.__wbs_allow_constraints__ and bl_context == 'constraint') \
                                    or (not custom_obj.__wbs_allow_mesh_properties__ and bl_context == 'data') \
                                    or (not custom_obj.__wbs_allow_material_properties__ and bl_context == 'material'):
                                return False

                except AttributeError:
                    pass

                return CustomObjectInterfaceHandler._altered_panels.get(cls)(cls, context)

            panel.poll = classmethod(poll_override)

    @classmethod
    def unregister(cls):
        """ Uninstalls poll() hooks. """

        for panel, orig_panel_poll in cls._altered_panels.items():
            panel.poll = classmethod(cls.copy_func(orig_panel_poll, name='poll'))

        cls._altered_panels.clear()



def register():
    CustomObjectInterfaceHandler.register()


def unregister():
    CustomObjectInterfaceHandler.unregister()











