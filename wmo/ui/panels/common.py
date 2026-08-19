from ....ui.enums import WoWSceneTypes

import bpy


def panel_poll(cls, context: bpy.types.Context) -> bool:
    """
    Common poll for some WMO panels to determined if a panel should be rendered..
    :param cls: Panel.
    :param context: Current context.
    :return: True if should be rendered, else False.
    """
    return (context.scene is not None
            and context.scene.wow_scene.type == WoWSceneTypes.WMO.name)

