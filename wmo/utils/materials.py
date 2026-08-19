import bpy
import os
from ...pywowlib.blp import BLP2PNG
from typing import Dict

from ...utils.misc import load_game_data

# old: read from extracted cache images
def load_texture_file(textures : dict, filepath : str, texture_dir : str) -> bpy.types.Image:
    new_filename = os.path.splitext(filepath)[0] + '.png'

    if os.name != 'nt':
        new_filename = new_filename.replace('\\', '/')

    texture = textures.get(filepath)

    # if image is not loaded, do it
    if not texture:
        tex_img = bpy.data.images.load(os.path.join(texture_dir, new_filename))
        tex_img.wow_wmo_texture.path = filepath
        tex_img.name = os.path.basename(new_filename)
        texture = tex_img

        textures[filepath] = texture

    return texture


def load_texture(textures : dict, filepath : str, texture_dir : str) -> bpy.types.Image:
    """ Load texture image from game data and add it to the blender scene """
    new_filename = os.path.splitext(filepath)[0] + '.png'

    if os.name != 'nt':
        new_filename = new_filename.replace('\\', '/')

    texture = textures.get(filepath)

    if not texture:
        # try getting it from cache first ?
        save_path = os.path.join(texture_dir, new_filename)

        # check file exists in the directory
        if os.path.isfile(save_path):
            # pretty much load_texture_file()
            tex_img = bpy.data.images.load(os.path.join(texture_dir, new_filename))
            texture = tex_img

        else:
            # if not, load from game data and save it to directory.
            game_data = load_game_data()

            result = game_data.read_file(filepath, "", 'blp', True)

            if result is None:
                print("\nFailed to load texture: <<{}>> from gamedata.".format(filepath))
                return None

            tex_img: bpy.types.Image = BLP2PNG().create_image(result[0])

            # save it to the cache folder
            tex_img.save(filepath= save_path)
            tex_img.filepath = save_path
    
            texture = tex_img
        
        filepath = filepath.replace('/', '\\')
        texture.wow_wmo_texture.path = filepath
        texture.wow_m2_texture.path = filepath
        texture.name = os.path.basename(new_filename)

        textures[filepath] = texture

    return texture


def add_ghost_material() -> bpy.types.Material:
    """ Add ghost material """

    mat = bpy.data.materials.get("WowMaterial_ghost")
    if not mat:
        mat = bpy.data.materials.new("WowMaterial_ghost")
        mat.blend_method = 'BLEND'
        mat.use_nodes = True
        mat.node_tree.nodes.remove(mat.node_tree.nodes.get('Principled BSDF'))
        material_output = mat.node_tree.nodes.get('Material Output')
        transparent = mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
        mat.node_tree.links.new(material_output.inputs[0], transparent.outputs[0])
        mat.node_tree.nodes["Transparent BSDF"].inputs[0].default_value = (0.38, 0.89, 0.37, 1)

    return mat
