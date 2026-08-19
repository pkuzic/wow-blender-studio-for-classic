import re


BL_ID_NAME_TEMPLATE = r'(.*)\.\d\d\d'
""" Template of ID data block names in Blender. E.g. name.001 and alike. """


def match_id_name(name: str, expected_name: str) -> bool:
    """
    Matches the name on an ID data-block omitting the possible .xxx duplicate prefix.
    :param name: Name to match.
    :param expected_name: Expected base of ID data block name.
    :return: True if matches, else False.
    """

    if name == expected_name:
        return True

    match = re.match(BL_ID_NAME_TEMPLATE, name)

    if match is None or match.group(1) != expected_name:
        return False

    return True
