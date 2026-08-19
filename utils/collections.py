from .custom_object import CustomObject
from .bl_id_types_utils import match_id_name, BL_ID_NAME_TEMPLATE
from ..ui.message_stack import MessageStack

import bpy
import re
import os

from typing import Set, Sequence, Type
from pathlib import Path


def get_collection(model_collection: bpy.types.Collection
                   , col_name: str) -> bpy.types.Collection | None:
    """
    Get child collection matching provided name excluding Blender's copy index (.xxx).
    :param model_collection: Collection to search in.
    :param col_name: Name of child collection.
    :return: Collection if found, else None.
    """

    # check if parent collection exists
    if not model_collection:
        raise KeyError("get_collection() called with Null WoW Model Collection.")
    
    # attempt regular search
    if (col := model_collection.children.get(col_name)) is not None:
        return col

    # attempt regex search
    for col in model_collection.children:
        match = re.match(BL_ID_NAME_TEMPLATE, col.name)

        if match is None or match.group(1) != col_name:
            continue

        return col


def get_or_create_collection(model_collection: bpy.types.Collection
                             , col_name: str) -> bpy.types.Collection:
    """
    Get child collection matching provided name excluding Blender's copy index (.xxx) or create it.
    :param model_collection: Collection to search in. ('wow_wmo', 'wow_m2'...)
    :param col_name: Name of child collection.
    :return: Requested collection.
    """
    # check if model_collection exists
    if not model_collection:
        # print("Error : WoW Model collection doesn't exist.")
        raise KeyError("get_or_create_collection() called with Null WoW Model Collection.")
        # can't create it because we don't have the type (wmo/m2/adt)
        # This shouldn't fail if it is called with model_collection = get_current_wow_model_collection() if there is an active collection.

    col = get_collection(model_collection, col_name)

    if not col:
        col = bpy.data.collections.new(col_name)
        model_collection.children.link(col)

        col.color_tag = 'COLOR_05'
    
    return col


def obj_swap_collections(obj: bpy.types.Object, col_from: bpy.types.Collection, col_to: bpy.types.Collection):
    """
    Safely unlink an object from one collection and link to another.
    :param obj: Object to swap collection.
    :param col_from: Collection from which to unlink.
    :param col_to: Collection to which to link.
    """
    try:
        col_from.objects.unlink(obj)
    except RuntimeError as e:
        print(f"Error: exception occured while swapping object \"{obj.name}\" from collection \"{col_from.name}\" to"
              "collection \"{col_to.name}\".\n{e}")
    try:
        col_to.objects.link(obj)
    except RuntimeError as e:
        print(f"Error: exception occured while swapping object \"{obj.name}\" from collection \"{col_from.name}\" to"
              "collection \"{col_to.name}\".\n{e}")


def collection_swap_parent_collection(col: bpy.types.Collection
                                      , col_from: bpy.types.Collection
                                      , col_to: bpy.types.Collection):
    """
    Safely unlink a collection from one collection, and link to another.
    :param col: Collection to swap.
    :param col_from: Collection from which to unlink.
    :param col_to: Collection to which to link.
    """

    try:
        col_from.children.unlink(col)
    except RuntimeError:
        print(f"Error: exception occured while swapping parent of collection \"{col.name}\" from collection"
               "\"{col_from.name}\" to collection \"{col_to.name}\".\n{e}")

    try:
        col_to.children.link(col)
    except RuntimeError:
        print(f"Error: exception occured while swapping parent of collection \"{col.name}\" from collection"
               "\"{col_from.name}\" to collection \"{col_to.name}\".\n{e}")


def unlink_nested_collections(parent_col: bpy.types.Collection
                              , col: bpy.types.Collection) -> bool:
    """
    Unlinks all nested collections from col to wmo_col.
    :param parent_col: WMO collection to unlink irrelevant ones into.
    :param col: Collection to sanitize.
    :return True if had nested collections, else False.
    """

    has_children = bool(len(col.children))

    for child_col in col.children:
        collection_swap_parent_collection(child_col, col, parent_col)

    return has_children


def create_wmo_model_collection(scene: bpy.types.Scene,
                                 filepath: str, wowpath: str)-> bpy.types.Collection:
    # col = bpy.data.collections.new(os.path.basename(wowpath)) # filename (+ extension?)
    filename = ''
    if wowpath:
        filename = Path(wowpath).stem
    else:
        filename = Path(filepath).stem

    col = bpy.data.collections.new(filename) # filename only without extension
    col.wow_wmo.enabled = True

    def filepath_wmo(filepath):
        filepath = filepath.lower()
        filepath = Path(filepath)
        filepath_parts = filepath.parts

        try: 
            world_index = filepath_parts.index('world')
        except ValueError:
            return 'World directory not found in the filepath'
        
        return str(Path(*filepath_parts[world_index:-1]))

    col.wow_wmo.dir_path = filepath_wmo(filepath)

    scene.collection.children.link(col)
    # set the collection as active
    layer_collection = bpy.context.view_layer.layer_collection.children[col.name]
    bpy.context.view_layer.active_layer_collection = layer_collection

    print("Created new WMO model Collection:" + col.name)
    return col

""""
def create_wow_model_collection(scene: bpy.types.Scene
                                 , id_prop: str) -> bpy.types.Collection | None:
    Create a WoW model collection.
    :param scene: Current scene.
    :param id_prop: Identifier of the collection property for the given model type.
    :return: Model (M2/WMO/ADT) collection

    col = bpy.data.collections.new(id_prop) # just name it 'wow_wmo' ?
    getattr(col, id_prop).enabled = True

    # scene.collection = col
    bpy.context.scene.collection.children.link(col)
    layer_collection = bpy.context.view_layer.layer_collection.children[col.name]
    bpy.context.view_layer.active_layer_collection = layer_collection

    print("Created new WoW model Collection:" + col.name)
    return col
"""

def get_current_wow_model_collection(scene: bpy.types.Scene
                                     , id_prop: str) -> bpy.types.Collection | None:
    """
    Gets currently active model collection.
    :param scene: Current scene.
    :param id_prop: Identifier of the collection property for the given model type.
    :return: Model (M2/WMO/ADT) collection if found, else None.
    """

    # check if there is an active collection at all
    # don't print or it will spam when using it in panels
    if not bpy.context.collection:
        # print("Error: Couldn't find current WoW model collection: there is no active collection at all.")
        return None
        # return create_wow_model_collection(scene, id_prop)

    act_col: bpy.types.Collection = bpy.context.collection
    # print("active collection : " + act_col.name)

    # check if the collection is a model collection itself
    if act_col.name in scene.collection.children:
        if getattr(act_col, id_prop).enabled:
            return act_col
        # print("Error: Couldn't find current WoW model collection: Active collection is not enabled to be a WoW "
        #       "Collection.")
        return None
        # return create_wow_model_collection(scene, id_prop)

    # check if the collection is a child of some existing collections.
    for col in scene.collection.children:
        # double check if this fix is right and I udnerstood it correctly
        if getattr(col, id_prop).enabled and act_col in col.children_recursive:
            return col

    # print("Error : Failed to find a WoW Model Collection.")
    return None
    # return create_wow_model_collection(scene, id_prop)


class SpecialCollection:
    """ Defines rules for handling updates to special collections. """

    __wbs_collection_name__: str
    """ Name of the special collection. """

    __wbs_root_collection_id_prop_name__: str
    """ Name of the property group of a root collection. E.g. wow_wmo or wow_m2"""

    __wbs_bl_object_types__: Set[str] = set()
    """ Set of Blender object types allowed to be part of the collection.
     (Used when no custom object type is defined. 
    """

    __wbs_custom_object_types__: Set[Type[CustomObject]] | None = None
    """ Optional set of custom object types restricted to the collection. """

    _required = { '__wbs_collection_name__', '__wbs_root_collection_id_prop_name__'}
    """ Required fields to override. """

    def __init_subclass__(cls, **kwargs):
        for requirement in cls._required:
            if not hasattr(cls, requirement):
                raise NotImplementedError(f'"{cls.__name__}" must override "{requirement}".')

        super().__init_subclass__(**kwargs)

    @classmethod
    def _get_root_collection(cls
                             , scene: bpy.types.Scene
                             , col: bpy.types.Collection) -> bpy.types.Collection | None:
        """
        Gets parent WoW collection (recursive) if existing, or None.
        :param scene: Current scene.
        :param col: Collection to search the parent for.
        :return: WMO parent collection or None if not found.
        """

        for scene_col in scene.collection.children:
            if not getattr(scene_col, cls.__wbs_root_collection_id_prop_name__).enabled:
                continue

            for child_col in scene_col.children_recursive:
                if child_col == col:
                    return scene_col

    @classmethod
    def verify_root_collection_integrity(cls
                                         , root_col: bpy.types.Collection
                                         , special_collection_ts: Sequence[Type['SpecialCollection']]):
        """
        Verifies presence of all special collections within a model collection.
        :param root_col: Root model collection.
        :param special_collection_ts: Special collections to ensure.
        """

        n_special_cols = len(special_collection_ts)
        status = [False] * n_special_cols
        status_counter = 0

        # search for matching collections
        for child_col in root_col.children:
            for i, special_col_t in enumerate(special_collection_ts):
                if match_id_name(child_col.name, special_col_t.__wbs_collection_name__):
                    status[i] = True
                    status_counter += 1
                    break

            if status_counter == n_special_cols:
                break

        # check if we found everything
        if status_counter == n_special_cols:
            return

        for i, s in enumerate(status):
            if not s:
                special_collection_ts[i].create_collection(root_col)

    @classmethod
    def handle_collection_if_matched(cls
                                     , scene: bpy.types.Scene
                                     , update: bpy.types.DepsgraphUpdate
                                     , special_collection_ts: Sequence[Type['SpecialCollection']]) -> bool:
        """
        Handle update to collection of matches the provided depsgraph update.
        :param scene: Current scene.
        :param update: Depsgraph update.
        :param special_collection_ts: Available collection types.
        :return: True if handled, else False.
        """
        collection: bpy.types.Collection = update.id.original

        # test if collection matches the criteria of a special collection
        if not match_id_name(collection.name, cls.__wbs_collection_name__):
            return False

        # test if collection is within a root collection
        root_col = cls._get_root_collection(scene, collection)

        if root_col is None:
            return False

        cls.verify_root_collection_integrity(root_col, special_collection_ts)

        for obj in collection.objects:
            # handle custom object types
            if cls.__wbs_custom_object_types__ is not None:
                if not any(c_obj.match(obj) for c_obj in cls.__wbs_custom_object_types__):
                    obj_swap_collections(obj, collection, root_col)
                    MessageStack().push_message(msg=f'Object "{obj.name}" removed from special collection '
                                                    f'"{cls.__wbs_collection_name__}" due to not matching '
                                                    f'with required custom object types.', icon='ERROR')

            # handle normal object types
            elif obj.type not in cls.__wbs_bl_object_types__:
                obj_swap_collections(obj, collection, root_col)
                MessageStack().push_message(msg=f'Object "{obj.name}" removed from special collection '
                                                f'"{cls.__wbs_collection_name__}". Objects of type \'{obj.type}\' '
                                                f'are not allowed.', icon='ERROR')

        # handle nested collections
        if unlink_nested_collections(root_col, collection):
            MessageStack().push_message(msg=f'This collection cannot have nested collections.', icon='ERROR')

        return True

    @classmethod
    def create_collection(cls
                          , parent_col: bpy.types.Collection):
        """
        Creates a special collection in a parent collection.
        :param parent_col: Parent collection.
        """
        col = bpy.data.collections.new(name=cls.__wbs_collection_name__)
        col.color_tag = 'COLOR_02'
        parent_col.children.link(col)




