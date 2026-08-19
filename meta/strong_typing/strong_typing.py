from functools import wraps
from types import FunctionType
from typeguard import typechecked
from enum import IntEnum
from typing import Dict, List, Optional


def strong_typed(original_method=None, *, check_release=False):
    """ Imposes strong typing assertions on a function call in both Debug and Release (optional).
    When enabled in Debug does not have a runtime cost."""

    def _decorate(method):
        if method.__dict__.get("_strong_typed") is not None:
            raise AssertionError(f"Method {method.__name__} is already using a different strong typing rule.")

        @wraps(method)
        def wrapped(*args, **kwargs):
            return method(*args, **kwargs)

        wrapped.__dict__["_strong_typed"] = check_release

        return wrapped

    if original_method:
        return _decorate(original_method)

    return _decorate


def _inspect_types_internal(method):
    @typechecked(always=True)
    @wraps(method)
    def wrapped(*args, **kwargs):
        return method(*args, **kwargs)

    return wrapped


class StrongTypingPolicy(IntEnum):
    """ Sets weak parameters for the StrongTyped metaclass"""
    _UNDEFINED = 0
    MANUAL = 1
    AUTO = 2


class StrongTypingPragmas(IntEnum):
    """ Lists all available pragmas controlling the StrongTyped metaclass"""
    TYPING_POLICY = 0


def singleton(class_):
    instances = {}

    def getinstance(*args, **kwargs):
        if class_ not in instances:
            instances[class_] = class_(*args, **kwargs)
        return instances[class_]

    return getinstance


@singleton
class StrongTypingPragma:
    _pragmas: Dict[StrongTypingPragmas, List[IntEnum]] = {}

    def push(self, pragma: StrongTypingPragmas, value: IntEnum):
        self._pragmas.setdefault(pragma, []).append(value)

    def pop(self, pragma: StrongTypingPragmas):
        pragma_stack = self._pragmas.get(pragma)

        if not pragma_stack:
            raise RuntimeError("Nothing to pop for selected pragma type.")

        pragma_stack.pop()

    def get(self, pragma: StrongTypingPragmas) -> Optional[IntEnum]:
        pragma_stack = self._pragmas.get(pragma)

        if not pragma_stack:
            return None

        return pragma_stack[-1]


class StrongTyped(type):
    _typecheck_policy: StrongTypingPolicy = StrongTypingPolicy._UNDEFINED

    def __new__(mcs, classname, bases, cls_dict):
        # wrap every method in debug with strong type assertions

        # resolve pragma parameters
        typing_policy = StrongTypingPragma().get(StrongTypingPragmas.TYPING_POLICY)

        # resolve explicit pragma policy overrides
        if typing_policy_ov := cls_dict.get("_typecheck_policy"):
            typing_policy = typing_policy_ov

        # resolve metaclass policy overrides
        if mcs._typecheck_policy != StrongTypingPolicy._UNDEFINED:
            typing_policy = mcs._typecheck_policy

        if typing_policy is None:
            raise RuntimeError(f"StrongTyping Error: typing policy for class {classname} id undefined.")

        new_cls_dict = {}
        for attr_name, attribute in cls_dict.items():
            if isinstance(attribute, FunctionType):
                if (check_release := attribute.__dict__.get("_strong_typed")) is not None:
                    if attribute.__annotations__:
                        if typing_policy == StrongTypingPolicy.AUTO:
                            print(f"StrongTyping Warning: redundant use of decorator given automatic typing policy"
                                  f" on method <{attr_name}> in class <{classname}>")

                        if __debug__ or check_release:
                            attribute = _inspect_types_internal(attribute)
                        else:
                            # remove decorators to avoid call overhead if type checking is not performed
                            attribute = attribute.__wrapped__
                    else:
                        print(f"StrongTyping Warning: redundant use of decorator"
                              f" on method <{attr_name}> without typing annonations in class <{classname}>")

                elif typing_policy == StrongTypingPolicy.AUTO and attribute.__annotations__:
                    attribute = _inspect_types_internal(attribute)

            new_cls_dict[attr_name] = attribute

        return type.__new__(mcs, classname, bases, new_cls_dict)


class StrongTypedAuto(StrongTyped):
    _typecheck_policy = StrongTypingPolicy.AUTO


class StrongTypedManual(StrongTyped):
    _typecheck_policy = StrongTypingPolicy.MANUAL


# tests
if __name__ == '__main__':
    class MyClass(metaclass=StrongTyped):
        _typecheck_policy = StrongTypingPolicy.MANUAL

        @strong_typed
        def test(self, test: int) -> float:
            return test

        @strong_typed(check_release=True)
        def test1(self):
            pass


    class MyClass1(metaclass=StrongTyped):
        _typecheck_policy = StrongTypingPolicy.AUTO

        def test(self, test: int) -> float:
            return test

        @strong_typed(check_release=True)
        def test1(self):
            pass


    StrongTypingPragma().push(StrongTypingPragmas.TYPING_POLICY, StrongTypingPolicy.AUTO)


    class MyClass2(metaclass=StrongTyped):
        def test(self, test: int) -> float:
            return test

        @strong_typed(check_release=True)
        def test1(self):
            pass


    StrongTypingPragma().pop(StrongTypingPragmas.TYPING_POLICY)

    # manual
    try:
        MyClass().test(1.0)
    except TypeError:
        print("Passed.")

    # auto
    try:
        MyClass1().test(1.0)
    except TypeError:
        print("Passed.")

    # pragma
    try:
        MyClass2().test(1.0)
    except TypeError:
        print("Passed.")