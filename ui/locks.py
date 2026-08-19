from ..utils.misc import singleton


class _BaseLock:
    _update_lock: int

    def __enter__(self):
        self._update_lock += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._update_lock -= 1

    def push(self):
        """ Manually enter the locking scope. """
        self._update_lock += 1

    def pop(self):
        """ Manually exit the locking scope. """
        self._update_lock -= 1

    @property
    def status(self) -> bool:
        """
        Test if depsgraph handlers are locked now.
        :return: True if locked, else False.
        """
        return bool(self._update_lock)


@singleton
class DepsgraphLock(_BaseLock):
    """
    Locks all depsgraph handler operations. Ensures no automated UI takss are handled in enclosed code.
    """
    _update_lock: int = 0


@singleton
class UIPropUpdateLock(_BaseLock):
    """
    Locks all update() callback in bpy.props custom defined properties that support locking.
    """
    _update_lock: int = 0

