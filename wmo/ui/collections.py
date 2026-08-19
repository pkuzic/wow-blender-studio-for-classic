from ...utils.collections import SpecialCollection, obj_swap_collections, collection_swap_parent_collection, get_or_create_collection, get_current_wow_model_collection
from ...utils.bl_id_types_utils import match_id_name
from ...ui.message_stack import MessageStack
from .enums import SpecialCollections
from .custom_objects import WoWWMOGroup, WoWWMOLight, WoWWMOFog\
    , WoWWMOLiquid, WoWWMODoodad, WoWWMOCollision, WoWWMOPortal

from typing import Iterable
import bpy

def get_wmo_collection(scene: bpy.types.Scene,
                        collection_type: SpecialCollections) -> bpy.types.Collection | None:
    wow_model_collection = get_current_wow_model_collection(scene, 'wow_wmo')
    if wow_model_collection:
        return get_or_create_collection(wow_model_collection, collection_type.name)
    else:
        return None


def iter_wmo_groups(scene: bpy.types.Scene) -> bpy.types.Object:
    """ Iterate and return each Object in Indoor and Outdor group collections 
        How to use : 'for each in iter_wmo_groups(scene):
                        print(each)'
    """
    for each in get_wmo_collection(scene, SpecialCollections.Outdoor).objects:
        yield each
    
    for each in get_wmo_collection(scene, SpecialCollections.Indoor).objects:
        yield each

def get_wmo_groups_list(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    groups_list = []

    for each in iter_wmo_groups(scene):
        groups_list.append(each)

    return groups_list

class _WMOCollection:
    """ Base class for all WMO collections. """
    __wbs_root_collection_id_prop_name__ = 'wow_wmo'


class _GroupCollection(_WMOCollection):
    """ Base class for WMO group collections. """
    __wbs_bl_object_types__ = {'MESH'}
    __wbs_custom_object_types__ = {WoWWMOGroup}


class OutdoorGroupCollection(_GroupCollection, SpecialCollection):
    """ Collection of objects marked as outdoor group. Accepts any MESH objects
        except for those matching other types.
    """
    __wbs_collection_name__ = SpecialCollections.Outdoor.name


class IndoorGroupCollection(_GroupCollection, SpecialCollection):
    """ Collection of objects marked as indoor group. Accepts any MESH objects
        except for those matching other types.
    """
    __wbs_collection_name__ = SpecialCollections.Indoor.name


class LightCollection(_WMOCollection, SpecialCollection):
    """ Collection of objects marked as lights. Only accepts lights created through an operator."""
    __wbs_collection_name__ = SpecialCollections.Lights.name
    __wbs_bl_object_types__ = {'LIGHT'}
    __wbs_custom_object_types__ = {WoWWMOLight}


class CollisionCollection(_WMOCollection, SpecialCollection):
    """ Collection of objects marked as collision. Accepts any MESH objects
        except for those matching other types.
    """
    __wbs_collection_name__ = SpecialCollections.Collision.name
    __wbs_bl_object_types__ = {'MESH'}
    __wbs_custom_object_types__ = {WoWWMOCollision}


class FogCollection(_WMOCollection, SpecialCollection):
    """ Collection of objects marked as fogs. Only accepts fogs created through an operator. """
    __wbs_collection_name__ =  SpecialCollections.Fogs.name
    __wbs_bl_object_types__ = {'MESH'}
    __wbs_custom_object_types__ = {WoWWMOFog}


class LiquidCollection(_WMOCollection, SpecialCollection):
    """ Collection of objects marked as liquids. Only accepts liquids created through an operator. """
    __wbs_collection_name__ = SpecialCollections.Liquids.name
    __wbs_bl_object_types__ = {'MESH'}
    __wbs_custom_object_types__ = {WoWWMOLiquid}


class PortalCollection(_WMOCollection, SpecialCollection):
    """ Collection of objects marked as portals. Accepts any MESH objects
        except for those matching other types.
    """
    __wbs_collection_name__ = SpecialCollections.Portals.name
    __wbs_bl_object_types__ = {'MESH'}
    __wbs_custom_object_types__ = {WoWWMOPortal}


class DoodadSetsCollection(_WMOCollection, SpecialCollection):
    """ Collection of collections representing doodad sets. Does not accept any objects.
        Child collections accept objects marked as doodads (created by operators).
    """
    __wbs_collection_name__ = SpecialCollections.Doodads.name
    __wbs_bl_object_types__ = {'MESH'}
    __wbs_custom_object_types__ = {WoWWMODoodad}

    @classmethod
    def is_doodad_set_collection(cls
                                 , scene: bpy.types.Scene
                                 , col: bpy.types.Collection) -> bool:
        """
        Identify if a collection is a doodad set collection (child collection of special collection Doodads)
        :param scene: Current scene.
        :param col: Collection to test.
        :return: True if is doodad set collection, else False.
        """
        for scene_col_child in scene.collection.children:
            # check if we are inside the WMO collection
            if getattr(scene_col_child, cls.__wbs_root_collection_id_prop_name__).enabled:
                for wmo_col_child in scene_col_child.children:
                    if match_id_name(wmo_col_child.name, cls.__wbs_collection_name__) \
                      and col.name in wmo_col_child.children:
                        return True

        return False

    @classmethod
    def verify_doodad_sets_collection_integrity(cls
                                                , scene: bpy.types.Scene
                                                , root_col: bpy.types.Collection):

        if root_col is None:
            return False

        for child_col in root_col.children:
                if match_id_name(child_col.name, DoodadSetsCollection.__wbs_collection_name__):
                    default_global_coll = None

                    for col in child_col.children:
                        if col.name.startswith("Set_$DefaultGlobal"):
                            default_global_coll = col
                            break
                    if not default_global_coll:
                        default_global_coll = bpy.data.collections.new("Set_$DefaultGlobal")
                        child_col.children.link(default_global_coll)
                        default_global_coll.color_tag = 'COLOR_04'

    @classmethod
    def handle_collection_if_matched(cls
                                     , scene: bpy.types.Scene
                                     , update: bpy.types.DepsgraphUpdate
                                     , special_collection_ts: Iterable['SpecialCollection']) -> bool:

        collection: bpy.types.Collection = update.id.original

        # test if collection is within a root collection
        root_col = cls._get_root_collection(scene, collection)

        if root_col is None:
            return False

        cls.verify_root_collection_integrity(root_col, special_collection_ts)
        cls.verify_doodad_sets_collection_integrity(scene, root_col)

        # doodad sets collection of collections
        if match_id_name(collection.name, cls.__wbs_collection_name__):
            # make sure it has no object linked to it directly
            if len(collection.objects):
                for obj in collection.objects:
                    obj_swap_collections(obj, collection, root_col)

                MessageStack().push_message(msg=f'Collection "{collection.name}" can only contain child collections.')

        # doodads set individual collection
        elif cls.is_doodad_set_collection(scene, collection):
            # make sure no collection is linked to it directly
            if len(collection.children):
                for child_col in collection.children:
                    collection_swap_parent_collection(child_col, collection, root_col)
                    child_col.color_tag = 'COLOR_04'

                MessageStack().push_message(msg=f'Collection "{collection.name}" cannot contain child collections.')

            for obj in collection.objects:
                # handle custom object types (doodads)
                if cls.__wbs_custom_object_types__ is not None \
                        and not any(c_obj.match(obj) for c_obj in cls.__wbs_custom_object_types__):
                    obj_swap_collections(obj, collection, root_col)
                    MessageStack().push_message(msg=f'Object "{obj.name}" removed from special collection '
                                                    f'"{cls.__wbs_collection_name__}" due to not matching '
                                                    f'with any custom object type.', icon='ERROR')
        else:
            return False

        return True


WMO_SPECIAL_COLLECTION_TYPES = (
    OutdoorGroupCollection,
    IndoorGroupCollection,
    FogCollection,
    PortalCollection,
    LiquidCollection,
    LightCollection,
    CollisionCollection,
    DoodadSetsCollection
)