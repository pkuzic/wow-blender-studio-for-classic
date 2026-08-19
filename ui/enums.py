from enum import Enum, auto


class WoWSceneTypes(Enum):
    """ Represents the type of WoW scene. """

    M2 = auto()
    """ Props, doodads, characters, etc. """

    WMO = auto()
    """ World Map Objects (big buildings, dungeons, cities, etc. """
