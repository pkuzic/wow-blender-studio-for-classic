from ...ui.locks import DepsgraphLock
from ...ui.message_stack import MessageStack
from ...utils.collections import SpecialCollection
from ..ui.custom_objects import WMO_CUSTOM_OBJECT_TYPES
from ..ui.collections import WMO_SPECIAL_COLLECTION_TYPES
from ...ui.enums import WoWSceneTypes
from .collections import DoodadSetsCollection

from bpy.app.handlers import persistent
import bpy


def handle_material_update(update: bpy.types.DepsgraphUpdate):
    """
    Handles update to materials.
    :param update: Current update.
    """
    ...  # TODO


def handle_collection_update(scene: bpy.types.Scene, update: bpy.types.DepsgraphUpdate):
    """
    Handles update to collections.
    :param scene: Current scene.
    :param update: Current update.
    """

    collection: bpy.types.Collection = update.id.original

    # check if we are inside a WMO collection.
    if collection.wow_wmo.enabled:
        if collection.name not in scene.collection.children:
            collection.wow_wmo.enabled = False
            return

        # verify integrity of child
        else:
            SpecialCollection.verify_root_collection_integrity(collection, WMO_SPECIAL_COLLECTION_TYPES)
            DoodadSetsCollection.verify_doodad_sets_collection_integrity(scene, collection)
            return

    for col_type in WMO_SPECIAL_COLLECTION_TYPES:
        if col_type.handle_collection_if_matched(scene, update, WMO_SPECIAL_COLLECTION_TYPES):
            break


def handle_object_update(update: bpy.types.DepsgraphUpdate):
    """
    Handles update to objects.
    :param scene: Current scene.
    :param update: Current update.
    """
    for obj_type in WMO_CUSTOM_OBJECT_TYPES:
        if obj_type.handle_object_if_matched(update):
            break


@persistent
def on_depsgraph_update(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph):
    """
    Called on every update to depsgraph.
    :param scene: Current scene.
    :param depsgraph: Updated depsgraph.
    """
    if scene.wow_scene.type != WoWSceneTypes.WMO.name or DepsgraphLock().status:
        return

    with DepsgraphLock():

        for update in depsgraph.updates:
            if isinstance(update.id, bpy.types.Object):
                handle_object_update(update)
            elif isinstance(update.id, bpy.types.Collection):
                handle_collection_update(scene, update)
            elif isinstance(update.id, bpy.types.Material):
                handle_material_update(update)

        MessageStack().invoke_message_box(icon='ERROR')


def register():
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
