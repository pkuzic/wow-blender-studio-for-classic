import bpy


class ActiveObjectOverride:
    """
    Overrides context of selected / active object for operators.
    """

    __slots__ = ('_obj', '_context_override')
    _obj: bpy.types.Object

    def __init__(self, obj: bpy.types.Object, context: bpy.types.Context | None = None):
        """
        Initialize context override helper class.
        :param obj: Object to set as active for this override.
        :param context: Current context.
        """
        self._obj = obj

        if context is None:
            context = bpy.context

        override = context.copy()
        override['active_object'] = obj
        override['selected_objects'] = [obj]

        self._context_override = context.temp_override(**override)

    def __enter__(self):
        self._context_override.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._context_override.__exit__(exc_type, exc_val, exc_tb)

