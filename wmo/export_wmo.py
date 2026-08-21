from ..pywowlib import WoWVersionManager
from ..pywowlib.wmo_file import WMOFile
from ..third_party.tqdm import tqdm
from .wmo_scene import BlenderWMOScene
from .classic_lint import ClassicLint
from ..ui.preferences import get_project_preferences

import bpy
import time
from pathlib import Path


def export_wmo_from_blender_scene(filepath, client_version, export_selected, export_method):
    """ Export WoW WMO object from Blender scene to files """

    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except:
        pass

    start_time = time.time()

    WoWVersionManager().set_client_version(client_version)
    ClassicLint.reset(client_version)

    wmo = WMOFile(client_version, filepath)
    wmo.export = export_method != 'PARTIAL'
    bl_scene = BlenderWMOScene(wmo, get_project_preferences())

    bl_scene.build_references(export_selected, export_method)

    # readable abort on broken portal links + warn on portals outside the Portals collection
    ClassicLint.pre_checks(bl_scene)

    bl_scene.save_materials()
    bl_scene.save_doodad_sets()
    bl_scene.save_lights()
    bl_scene.save_fogs()
    bl_scene.prepare_groups()
    bl_scene.save_portals()
    bl_scene.save_groups()
    bl_scene.save_root_header()

    # Classic (1.12) lint: sealed interiors, side=0 relations, uncovered openings.
    # Raises before anything is written, so a failed export leaves no file behind.
    ClassicLint.post_checks(bl_scene)

    # create directory if it doesn't exist, for the new quick save
    file = Path(filepath)
    file.parent.mkdir(parents=True, exist_ok=True)

    for _ in tqdm(range(1), desc='Writing WMO files', ascii=True):
        wmo.write()

    for line in ClassicLint.report_lines():
        print("[classic-lint] " + line)

    print("\nExport finished successfully. Saved WMO to " + filepath +
          "\nTotal export time: ", time.strftime("%M minutes %S seconds\a", time.gmtime(time.time() - start_time)))
