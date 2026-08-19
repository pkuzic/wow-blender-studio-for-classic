import os
import struct
import time

import bpy
from ..utils.misc import load_game_data
import importlib
from . import m2_scene
from ..pywowlib.m2_file import M2File, M2Versions
from ..ui.preferences import get_project_preferences


def import_m2(version, filepath, is_local_file, time_import_method):

    start_time = time.time()

    # get global variables
    project_preferences = get_project_preferences()

    try:
        game_data = load_game_data()

    except UserWarning:
        game_data = None

    m2_file = M2File(version, filepath=filepath)
    m2 = m2_file.root
    m2.filepath = filepath  # TODO: HACK
    
    extract_dir = os.path.dirname(filepath) if is_local_file else project_preferences.cache_dir_path

    if not extract_dir:
        raise Exception('Error: cache directory is not specified. Check addon settings.')

    if game_data and game_data.files:

        # extract and read skel
        # skel_fdid = m2_file.find_main_skel()

        # while skel_fdid:
        #     skel_path = game_data.extract_file(extract_dir, skel_fdid, 'skel')
        #     skel_fdid = m2_file.read_skel(skel_path)

        # m2_file.process_skels()

        print("\n\nExtracting M2 required files into cache folder")

        dependencies = m2_file.find_model_dependencies()

        # extract textures, always into cache folder
        m2_file.texture_path_map = game_data.extract_textures_as_png(project_preferences.cache_dir_path, dependencies.textures)

        # extract anims
        anim_filepaths = {}
        for key, identifier in dependencies.anims.items():
            #For importing m2 through import (folder)
            if is_local_file:
                    
                    full_path = os.path.join(extract_dir, os.path.split(identifier)[-1])

                    if os.path.exists(full_path):
                        anim_filepaths[key] = full_path
                    else:
                        anim_filepaths[key] = os.path.split(identifier)[-1]
                        print("\n.anim not found at:", full_path, '\n')
            #For importing thorugh WMV/WoW.Export...               
            else:
                try:
                    anim_filepaths[key] = game_data.extract_file(extract_dir, identifier, 'anim')
                except:
                        anim_filepaths[key] = os.path.split(identifier)[-1]
                        print("\n Failed to extract anim from game data:", identifier)

        # extract skins and everything else
        if is_local_file:
            skin_filepaths = dependencies.skins
        else:
            skin_filepaths = game_data.extract_files(extract_dir, dependencies.skins, 'skin')

        if version >= M2Versions.WOD:
            game_data.extract_files(extract_dir, dependencies.bones, 'bone', True)
            game_data.extract_files(extract_dir, dependencies.lod_skins, 'skin', True)
        
    else:
        raise NotImplementedError('Error: Importing without gamedata loaded is not yet implemented.')

    m2_file.read_additional_files(skin_filepaths, anim_filepaths)
    m2_file.root.assign_bone_names()

    if not is_local_file:
        for key, identifier in dependencies.anims.items():
            os.remove(os.path.join(extract_dir, identifier))

    print("\n\n### Importing M2 model ###")

    importlib.reload(m2_scene)
    bl_m2 = m2_scene.BlenderM2Scene(m2_file, project_preferences)

    cache_dir = project_preferences.cache_dir_path
    end_index = filepath.find(cache_dir) + len(cache_dir)
    m2_filepath = filepath[end_index:]
    
    if not is_local_file:
        bpy.context.scene.wow_scene.game_path = m2_filepath
    else:
        normalized_path = os.path.normpath(filepath)
        path_parts = [part.lower() for part in normalized_path.split(os.sep)]
        wow_root_folders = ["character", "creature", "environments", "item", "spells", "world"]
        base_path_index = next((path_parts.index(cat) for cat in wow_root_folders if cat in path_parts), 0)
        
        bpy.context.scene.wow_scene.game_path = os.sep.join(path_parts[base_path_index:])
        
        print('Normalized path', normalized_path)
        print('path_parts', path_parts)
        print('base_path_index', base_path_index)

    #import cProfile
    #def profile_import_animations(instance):
        #cProfile.runctx('instance.load_animations()', globals(), locals(), sort='cumulative')
    #profile_import_animations(bl_m2)
        
    bl_m2.load_armature()
    bl_m2.load_animations()
    bl_m2.load_colors(time_import_method)
    bl_m2.load_transparency(time_import_method)
    dbc_textures = bl_m2.load_materials()
    bl_m2.load_geosets()
    bl_m2.load_texture_transforms()
    bl_m2.load_collision()
    bl_m2.load_attachments()
    bl_m2.load_lights()
    bl_m2.load_events()
    bl_m2.load_cameras(time_import_method)
    bl_m2.load_ribbons()
    bl_m2.load_particles(time_import_method)
    bl_m2.load_globalflags()

    if dbc_textures:
        bpy.ops.scene.wow_creature_load_textures(LoadAll=True) 

    print("\nDone importing M2. \nTotal import time: ",
          time.strftime("%M minutes %S seconds.", time.gmtime(time.time() - start_time)))

    bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully imported M2!", font_size=24, y_offset=67)   
        
    return m2_file


def import_m2_gamedata(version, filepath, is_local_file):


    game_data = load_game_data()

    if not game_data or not game_data.files:
        raise FileNotFoundError("Game data is not loaded.")

    addon_prefs = get_project_preferences()
    cache_dir = addon_prefs.cache_dir_path
    time_import_method = addon_prefs.time_import_method

    if time_import_method == 'Convert':
        bpy.context.scene.render.fps = 30
        bpy.context.scene.sync_mode = 'NONE'
    else:
        bpy.context.scene.render.fps = 1000
        bpy.context.scene.sync_mode = 'FRAME_DROP'

    game_data.extract_file(cache_dir, filepath)

    if os.name != 'nt':
        filepath = filepath.lower()
        root_path = os.path.join(cache_dir, filepath.replace('\\', '/'))
    else:
        root_path = os.path.join(cache_dir, filepath)

    with open(root_path, 'rb') as f:
        f.seek(68)
        n_skins = struct.unpack('I', f.read(4))[0]

    skin_paths = ["{}{}.skin".format(filepath[:-3], str(i).zfill(2)) for i in range(n_skins)]
    game_data.extract_files(cache_dir, skin_paths)

    import_m2(version, root_path, is_local_file, time_import_method)    

    # clean up unnecessary files and directories
    os.remove(root_path)
    for skin_path in skin_paths:
        os.remove(os.path.join(cache_dir, *skin_path.split('\\')))