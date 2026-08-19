# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8-80 compliant>


bl_info = {
    "name": "WoW Blender Studio",
    "author": "Skarn",
    "version": (1, 0, 3),
    "blender": (3, 4, 0),
    "description": "Import-Export WoW M2-WMO",
    "category": "Import-Export"
}

import os
import sys
import traceback
import bpy
import bpy.utils.previews
from bpy.props import StringProperty
from . import auto_load

PACKAGE_NAME = __package__

# include custom lib vendoring dir
parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'third_party')

sys.path.append(vendor_dir)

# load custom icons
ui_icons = {}
pcoll = None



def register():
    global pcoll
    global ui_icons

    pcoll = bpy.utils.previews.new()

    icons_dir = os.path.join(os.path.dirname(__file__), "icons")

    for file in os.listdir(icons_dir):
        pcoll.load(os.path.splitext(file)[0].upper(), os.path.join(icons_dir, file), 'IMAGE')

    for name, icon_file in pcoll.items():
        ui_icons[name] = icon_file.icon_id

    auto_load.init()

    try:
        auto_load.register()
        print("Registered WoW Blender Studio")

    except:
        traceback.print_exc()


def unregister():
    try:
        auto_load.unregister()
        print("Unregistered WoW Blender Studio")

    except:
        traceback.print_exc()

    global pcoll
    bpy.utils.previews.remove(pcoll)

    global ui_icons
    ui_icons = {}


if __name__ == "__main__":
    register()
