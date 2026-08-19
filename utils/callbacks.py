import bpy
from functools import partial
from typing import Protocol
from time import time

from ..third_party.boltons.funcutils import wraps
from ..utils.misc import show_message_box
from ..ui.locks import UIPropUpdateLock


def parametrized(dec):
    def layer(*args, **kwargs):
        def repl(f):
            return dec(f, *args, **kwargs)
        return repl
    return layer


@parametrized
def delay_execution(func, delay_sec=1.0):

    lock = False
    def timer(*args, **kwargs):
        nonlocal lock
        lock = False

        func(*args, **kwargs)

    @wraps(func)
    def wrapped(*args, **kwargs):
        nonlocal lock

        if not lock:
            lock = True
            bpy.app.timers.register(partial(timer, *args, **kwargs), first_interval=delay_sec)

    return wrapped


@parametrized
def on_release(func, delay_sec=1.5):

    exec_time = time()

    def timer(*args, **kwargs):
        nonlocal exec_time
        if not abs(exec_time - time()) < delay_sec:
            func(*args, **kwargs)

    @wraps(func)
    def wrapped(*args, **kwargs):
        nonlocal exec_time
        exec_time = time()

        bpy.app.timers.register(partial(timer, *args, **kwargs), first_interval=max(1.0, delay_sec))

    return wrapped


def no_recurse(func):
    """
    Decorator to block the function's ability to indirectly call itself recursively.
    :param func: Any func.
    :return: Wrapped func.
    """
    func.__no_recurse_lock = False

    @wraps(func)
    def wrapped(*args, **kwargs):
        if func.__no_recurse_lock:
            return

        func.__no_recurse_lock = True
        func(*args, **kwargs)
        func.__no_recurse_lock = False

    return wrapped


class StringFilterProtocol(Protocol):
    """
    Protocol the filters for string_property_validator must implement.
    """
    def __call__(self, string: str) -> None | str: ...


@no_recurse
def string_property_validator(self: bpy.types.PropertyGroup
                              , context: bpy.types.Context
                              , *
                              , name: str
                              , str_filter: StringFilterProtocol
                              , lockable: bool = True):

    if lockable and UIPropUpdateLock().status:
        return

    cur_value = getattr(self, name)

    filtered = str_filter(cur_value)

    if filtered is None:
        return

    setattr(self, name, filtered)


def string_filter_internal_dir(string: str) -> None | str:
    """
    Validate and attempt to fix the string that is supposed to represent internal WoW dir.
    :param string: Any string.
    :return: Fixed string or None if string was valid.
    """

    if not string:
        return None

    slashes_fixed = False
    if '/' in string:
        string = string.replace('/', '\\')
        slashes_fixed = True

    if any(char == '.' for char in string):
        show_message_box("Path must not contain '.' characters.", "Error", 'ERROR')
        return ""
    
    if any(char == ':' for char in string):
        print("Path must not contain ':' characters. Path was probably added on import from a full disk filepath.")
        return ""
    
    # TODO: some characters like \ / : * ? " < > | are not valid path characters in windows
    if any(char in ('*', '?', '"', '<', '>', '|') for char in string):
        show_message_box("""Path must not contain * ? " < > | characters.""", "Error", 'ERROR')
        return ""

    try:
        string.encode('ascii')
    except UnicodeError:
        show_message_box("Path must only use latin characters.", "Error", 'ERROR')
        return ""

    backslash_count = 0
    for char in string:
        if char == '\\':
            backslash_count += 1
        else:
            backslash_count = 0

        if backslash_count > 1:
            show_message_box("Invalid path (multiple consecutive path separators)", "Error", 'ERROR')
            return ""

    if slashes_fixed:
        return string



