from ..utils.misc import singleton

from typing import List, Tuple

import bpy


@singleton
class MessageStack:
    """ Used to display messages from handlers. """

    _message: List[Tuple[str, str]] = []

    def push_message(self, *,  msg: str = '', icon: str = 'INFO'):
        """
        Push message to the stack.
        :param msg: Message text.
        :param icon: Message icon.
        """
        self._message.append((msg, icon))

    @staticmethod
    def _draw(self, context):
        for msg, icon in MessageStack()._message:
            self.layout.label(text=msg, icon=icon)

    def invoke_message_box(self, title: str = 'WoW Blender Studio', icon: str = 'INFO'):
        """
        Invoke popup message box window displaying current message stack. Also clears the stack.
        :param title: Title of the message box.
        :param icon: Icon of the message box.
        """

        if not self._message:
            return

        bpy.context.window_manager.popup_menu(self._draw, title=title, icon=icon)
        self._message.clear()


