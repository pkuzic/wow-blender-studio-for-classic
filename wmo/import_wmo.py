import bpy
import time
import os
import struct
import timeit

from ..utils.misc import load_game_data
from ..utils.collections import get_current_wow_model_collection, create_wmo_model_collection, SpecialCollection
from .wmo_scene import BlenderWMOScene

from ..pywowlib import WoWVersionManager
from ..pywowlib.wmo_file import WMOFile

from ..ui.preferences import get_project_preferences
from .ui.handlers import DepsgraphLock
from .ui.collections import WMO_SPECIAL_COLLECTION_TYPES, DoodadSetsCollection


def import_wmo_to_blender_scene(filepath: str, client_version: int, wowfilepath: str = ''):
    """ Read and import WoW WMO object to Blender scene"""

    start_time = time.time()

    WoWVersionManager().set_client_version(client_version)

    print("\nImporting WMO")

    project_preferences = get_project_preferences()
    game_data = load_game_data()

    if not bpy.wow_game_data.files:
        raise Exception("WoW game data is not loaded. Check settings.")
    
    if not project_preferences.cache_dir_path:
        raise Exception("Cache directory is not set, textures might not work. Check settings.")

    with DepsgraphLock():
        wmo = WMOFile(client_version, filepath=filepath)
        # wmo.read()
        execution_time  = timeit.timeit(lambda: wmo.read(), number=1)
        ms_time = execution_time * 1000
        print(f"Pywowlib WMO read time : {ms_time:.4f} ms")

        wmo_scene = BlenderWMOScene(wmo=wmo, prefs=project_preferences)

        # set wmo model collection
        wow_model_collection = get_current_wow_model_collection(bpy.context.scene, 'wow_wmo')
        if not wow_model_collection:
            wow_model_collection = create_wmo_model_collection(bpy.context.scene, filepath, wowfilepath)
        SpecialCollection.verify_root_collection_integrity(wow_model_collection, WMO_SPECIAL_COLLECTION_TYPES)
        DoodadSetsCollection.verify_doodad_sets_collection_integrity(bpy.context.scene, wow_model_collection)

        # extract textures to cache folder
        game_data.extract_textures_as_png(project_preferences.cache_dir_path, wmo.motx.get_all_strings())


        # load all WMO components
        wmo_scene.load_materials()
        wmo_scene.load_lights()
        wmo_scene.load_properties()
        wmo_scene.load_fogs()
        wmo_scene.load_groups()
        wmo_scene.load_portals()
        wmo_scene.load_portal_relations()
        wmo_scene.load_doodads()

    # update visibility
    bpy.context.scene.wow_visibility = bpy.context.scene.wow_visibility

    print("\nDone importing WMO. \nTotal import time: ",
          time.strftime("%M minutes %S seconds.\a", time.gmtime(time.time() - start_time)))


def import_wmo_to_blender_scene_gamedata(filepath: str, client_version: int):

    filepath = filepath.replace('/', '\\')

    game_data = load_game_data()

    if not game_data or not game_data.files:
        raise FileNotFoundError("Game data is not loaded.")

    project_preferences = get_project_preferences()
    cache_dir = project_preferences.cache_dir_path

    game_data.extract_file(cache_dir, filepath)

    if os.name != 'nt':
        filepath = filepath.lower()
        root_path = os.path.join(cache_dir, filepath.replace('\\', '/'))
    else:
        root_path = os.path.join(cache_dir, filepath)

    with open(root_path, 'rb') as f:
        f.seek(24)
        n_groups = struct.unpack('I', f.read(4))[0]

    group_paths = ["{}_{}.wmo".format(filepath[:-4], str(i).zfill(3)) for i in range(n_groups)]

    game_data.extract_files(cache_dir, group_paths)

    import_wmo_to_blender_scene(root_path, client_version, filepath)

    # clean up unnecessary files and directories
    os.remove(root_path)
    for group_path in group_paths:
        os.remove(os.path.join(cache_dir, *group_path.split('\\')))
