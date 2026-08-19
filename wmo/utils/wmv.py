from typing import Union

from ...ui.preferences import get_project_preferences


def wmv_get_last_wmo() -> Union[None, str]:
    """Get the path of last WMO model from WoWModelViewer or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.wmv_path:

        lines = open(project_preferences.wmv_path).readlines()

        for line in reversed(lines):
            if 'Loading WMO' in line:
                return line[22:].rstrip("\n")


def wmv_get_last_m2() -> Union[None, str]:
    """Get the path of last M2 model from WoWModelViewer or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.wmv_path:

        lines = open(project_preferences.wmv_path).readlines()

        for line in reversed(lines):
            if 'Loading model:' in line:
                return line[25:].split(",", 1)[0].rstrip("\n")


def wmv_get_last_texture() -> Union[None, str]:
    """Get the path of last texture from WoWModelViewer or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.wmv_path:

        lines = open(project_preferences.wmv_path).readlines()

        for line in reversed(lines):
            if 'Loading texture' in line:
                return line[27:].rstrip("\n")
            
def wow_export_get_last_texture() -> Union[None,str]:
    """Get the path of last texture from WoWExport or similar log."""
    project_preferences = get_project_preferences()
    if project_preferences.wow_export_path:
        lines = open(project_preferences.wow_export_path).readlines()

        for line in reversed(lines):
            if 'Previewing texture file' in line:
                return line[35:].split(",", 1)[0].rstrip("\n")
                            
def wow_export_get_last_m2() -> Union[None, str]:
    """Get the path of last M2 model from WoWExport or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.wow_export_path:

        lines = open(project_preferences.wow_export_path).readlines()

        for line in reversed(lines):
            if 'Previewing model' in line:
                return line[28:].split(",", 1)[0].rstrip("\n")
            
def noggit_red_get_last_m2() -> Union[None, str]:
    """Get the path of last M2 model from Noggit Red or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.noggit_red_path:

        lines = open(project_preferences.noggit_red_path).readlines()

        for line in reversed(lines):
            if 'Loaded  file' in line and 'm2' in line:
                start = line.find("'") + 1
                end = line.find(".m2") + 3
                return line[start:end]               

def noggit_red_get_last_wmo() -> Union[None, str]:
    """Get the path of last WMO model from Noggit Red or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.noggit_red_path:

        lines = open(project_preferences.noggit_red_path).readlines()

        for line in reversed(lines):
            if 'Loaded  file' in line and 'wmo' in line:
                start = line.find("'") + 1
                end = line.find(".wmo") + 4
                return line[start:end]    
            
def wow_export_get_last_wmo() -> Union[None, str]:
    """Get the path of last WMO model from WoWExport or similar log."""

    project_preferences = get_project_preferences()
    if project_preferences.wow_export_path:

        lines = open(project_preferences.wow_export_path).readlines()

        for line in reversed(lines):
            if 'Previewing model' in line:
                return line[28:].split(",", 1)[0].rstrip("\n")