import os
import struct
import tempfile
import time

import bpy
from ..utils.misc import load_game_data
import importlib
from . import m2_scene
from ..pywowlib.m2_file import M2File, M2Versions
from ..ui.preferences import get_project_preferences


def _remove_quietly(path):
    # cache cleanup only: a file that was never extracted (e.g. an .anim missing from the archives) is fine
    try:
        os.remove(path)
    except OSError:
        pass

def _find_loose_texture(local_dir, name, cache_dir):
    """Path of an existing .png/.blp for the texture `name` (a WoW path) near the model, or None."""
    rel = name.replace('\\', os.sep).replace('/', os.sep)
    stem_rel = os.path.splitext(rel)[0]
    stem_base = os.path.basename(stem_rel)
    roots = [(local_dir, stem_rel), (local_dir, stem_base)]
    if cache_dir:
        roots.append((cache_dir, stem_rel))
    for root, stem in roots:
        for ext in ('.png', '.blp', '.PNG', '.BLP'):
            cand = os.path.join(root, stem + ext)
            if os.path.isfile(cand):
                return cand
    return None


def _blp_to_png(blp_path, out_dir):
    """Decode a BLP2 with the add-on's decoder and save it as PNG into out_dir. Returns the png path or None."""
    try:
        from ..utils import blp_decode
        with open(blp_path, 'rb') as f:
            rgba = blp_decode.decode(f.read(), 4096)
        h, w = rgba.shape[0], rgba.shape[1]
        os.makedirs(out_dir, exist_ok=True)
        png = os.path.join(out_dir, os.path.splitext(os.path.basename(blp_path))[0] + '.png')
        img = bpy.data.images.new('_wbs_blp_tmp', w, h, alpha=True)
        try:
            # BLP rows are top-down, Blender's are bottom-up
            img.pixels.foreach_set((rgba[::-1].astype('float32') / 255.0).ravel())
            img.filepath_raw = png
            img.file_format = 'PNG'
            img.save()
        finally:
            bpy.data.images.remove(img)
        return png
    except Exception as e:
        print("\nWarning: could not convert \"{}\" ({}): using a placeholder image.".format(blp_path, e))
        return None


def _local_texture_map(local_dir, textures, cache_dir):
    """Texture name -> '<something>.blp' path whose .png sibling exists (what the scene builder expects).
    Textures that cannot be found are left out: the scene builder then makes a placeholder image named after them."""
    result = {}
    out_dir = cache_dir if cache_dir else os.path.join(tempfile.gettempdir(), 'wbs_textures')
    for name in textures:
        if not isinstance(name, str) or not name:
            continue
        found = _find_loose_texture(local_dir, name, cache_dir)
        if not found:
            continue
        stem = os.path.splitext(found)[0]
        if found.lower().endswith('.blp'):
            if os.path.isfile(stem + '.png'):
                result[name] = stem + '.blp'
                continue
            png = _blp_to_png(found, out_dir)
            if png:
                result[name] = os.path.splitext(png)[0] + '.blp'
            continue
        result[name] = stem + '.blp'
    return result

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
        
    elif is_local_file:
        # No WoW client: everything comes from the folder the .m2 lives in (no archives, no DBC).
        print("\nNo WoW client loaded - importing the loose .m2 with the files next to it.")
        dependencies = m2_file.find_model_dependencies()
        local_dir = os.path.dirname(os.path.abspath(filepath))

        m2_file.texture_path_map = _local_texture_map(local_dir, dependencies.textures,
                                                      project_preferences.cache_dir_path)

        anim_filepaths = {}
        for key, identifier in dependencies.anims.items():
            anim_filepaths[key] = os.path.join(local_dir, os.path.split(identifier)[-1])

        # <= TBC: skins are embedded in the .m2; WotLK (v264): <stem>NN.skin next to the file
        skin_filepaths = [os.path.join(local_dir, os.path.split(s)[-1]) for s in dependencies.skins
                          if isinstance(s, str)]

    else:
        raise FileNotFoundError('Error: the WoW client is not loaded (set the WoW path of the project in the '
                                'add-on preferences) - cannot import a model from the game archives.')

    m2_file.read_additional_files(skin_filepaths, anim_filepaths)
    m2_file.root.assign_bone_names()

    if not is_local_file:
        for key, identifier in dependencies.anims.items():
            _remove_quietly(os.path.join(extract_dir, identifier))

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

    if dbc_textures and game_data and game_data.files:
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
        f.seek(4)
        m2_version = struct.unpack('I', f.read(4))[0]
        f.seek(68)
        n_skins = struct.unpack('I', f.read(4))[0]
    if m2_version < 264:
        n_skins = 0     # <= TBC: skin profiles are embedded in the .m2 (and 0x44 is the vertex array there)

    skin_paths = ["{}{}.skin".format(filepath[:-3], str(i).zfill(2)) for i in range(n_skins)]
    extracted = game_data.extract_files(cache_dir, skin_paths)
    missing = [p for p, r in zip(skin_paths, extracted) if not r or not os.path.getsize(r)]
    if missing:
        _remove_quietly(root_path)
        for r in extracted:
            if r:
                _remove_quietly(r)
        raise FileNotFoundError("this is a WotLK-format model (v{}) but its skin file {} is not in the client, so "
                                "there is no geometry to import (the game cannot draw it either)"
                                .format(m2_version, os.path.basename(missing[0])))

    import_m2(version, root_path, is_local_file, time_import_method)

    # clean up unnecessary files and directories
    _remove_quietly(root_path)
    for skin_path in skin_paths:
        _remove_quietly(os.path.join(cache_dir, *skin_path.split('\\')))