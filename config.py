# The add-on's module name = its FOLDER name, which Blender uses as the key in preferences.addons. It is normally
# 'io_scene_wmo' (release zip), but a GitHub "Code > Download ZIP" install is named e.g.
# 'wow-blender-studio-for-classic-main' - so derive it instead of hard-coding it.
ADDON_MODULE_NAME: str = __package__.split('.')[0]
""" Name of the addon module (typically the name of the root folder. """

