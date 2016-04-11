#!/usr/bin/env python3

"""Experiments in execution of untrusted Python code."""

# pylint: disable=redefined-builtin,unidiomatic-typecheck,eval-used,exec-used

import ast
import code
import inspect
import sys
import types


if sys.version_info < (3, 4):
    raise RuntimeError("Python 3.4 or later is required")


_SAFE_BUILTINS = (
    "__build_class__", "ArithmeticError", "AssertionError", "AttributeError",
    "Ellipsis", "False", "FloatingPointError", "GeneratorExit", "IndexError",
    "InterruptedError", "KeyError", "LookupError", "NameError", "None",
    "NotImplemented", "NotImplementedError", "OverflowError", "StopIteration",
    "True", "TypeError", "UnboundLocalError", "UnicodeDecodeError",
    "UnicodeEncodeError", "UnicodeError", "UnicodeTranslateError",
    "ValueError", "ZeroDivisionError", "abs", "all", "any", "ascii", "bin",
    "bool", "bytes", "callable", "chr", "classmethod", "complex", "delattr",
    "dict", "divmod", "enumerate", "filter", "float", "format", "frozenset",
    "hasattr", "hash", "hex", "id", "int", "isinstance", "issubclass", "iter",
    "len", "list", "map", "max", "min", "next", "object", "oct", "ord", "pow",
    "property", "range", "repr", "reversed", "round", "set", "slice", "sorted",
    "staticmethod", "str", "sum", "super", "tuple", "zip"
)

_SAFE_MODULES = frozenset((
    "base64", "binascii", "bisect", "calendar", "cmath", "crypt", "datetime",
    "decimal", "enum", "errno", "fractions", "functools", "hashlib", "hmac",
    "ipaddress", "itertools", "math", "numbers", "queue", "re", "statistics",
    "textwrap", "unicodedata", "urllib.parse",
))

_UNSAFE_NAMES = frozenset((
    # Python 3.5 coroutine objects
    "cr_code", "cr_frame",
    # Frame objects
    "f_back", "f_builtins", "f_code", "f_locals", "f_globals",
    # Generator objects
    "gi_code", "gi_frame",
    # Traceback objects
    "tb_frame", "tb_next",
))


def _safe_dir(*args):
    names = (dir(*args) if args
             else inspect.currentframe().f_back.f_locals.keys())
    return [name for name in names if _check_name(name)]


def _safe_eval(source):
    if type(source) is str:
        return eval(safe_compile(source, "<script>", "eval"),
                    inspect.currentframe().f_back.f_globals,
                    inspect.currentframe().f_back.f_locals)
    raise TypeError("Can only eval() strings, not " + type(source).__name__)


def _safe_exec(source):
    if type(source) is str:
        exec(safe_compile(source, "<string>", "exec"),
             inspect.currentframe().f_back.f_globals,
             inspect.currentframe().f_back.f_locals)
        return
    raise TypeError("Can only exec() strings, not " + type(source).__name__)


def _safe_delattr(obj, name):
    if type(name) is str and _check_name(name):
        return delattr(obj, name)
    raise AttributeError("Not allowed to access private attributes")


def _safe_getattr(obj, name, *args):
    if type(name) is str and _check_name(name):
        return getattr(obj, name, *args)
    raise AttributeError("Not allowed to access private attributes")


def _safe_setattr(obj, name, value):
    if type(name) is str and _check_name(name):
        return setattr(obj, name, value)
    raise AttributeError("Not allowed to access private attributes")


def _check_name(name):
    return not (name.startswith("_") or name in _UNSAFE_NAMES)


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if type(name) is not str:
        raise TypeError("Invalid type passed as name to __import__")
    if (fromlist is not None and type(fromlist) is not tuple and
            type(fromlist) is not list):
        raise TypeError("Invalid type passed as fromlist to __import__")
    if type(level) is not int:
        raise TypeError("Invalid type passed as level to __import__")
    if globals is None or locals is None:
        raise ImportError("globals and locals must be passed to __import__")
    if fromlist:
        for fromitem in fromlist:
            if type(fromitem) is not str or not _check_name(fromitem):
                raise ImportError("Not allowed to access private attributes")
    if level != 0:
        raise ImportError("Only absolute imports are allowed")
    if name not in _SAFE_MODULES:
        raise ImportError("Only white-listed imports are allowed")
    namespace = inspect.currentframe().f_back.f_globals
    if name in namespace["__modules__"]:
        return namespace["__modules__"][name]
    module = _copy_module(__import__(name, globals, locals, fromlist, 0))
    namespace["__modules__"][name] = module
    return module


def safe_compile(untrusted_source, filename, mode):
    """
    Compile the given untrusted source string, and perform static code
    analysis to determine if it should be safe to execute. Returns
    the compiled abstract syntax tree object.
    """
    tree = compile(untrusted_source, filename, mode, ast.PyCF_ONLY_AST)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not _check_name(node.id):
            raise SyntaxError(
                "Access to private name {!r} is not allowed at line {}".
                format(node.id, node.lineno))
        elif isinstance(node, ast.Attribute) and not _check_name(node.attr):
            raise SyntaxError(
                "Access to private attribute {!r} is not allowed at line {}".
                format(node.attr, node.lineno))
    return compile(tree, filename, mode)


def _copy_module(module, include=None, exclude=None):
    copied = types.ModuleType(module.__name__)
    copied.__package__ = getattr(module, "__package__", None)
    for name, value in module.__dict__.items():
        if (name.startswith("_") or (exclude is not None and name in exclude) or
                (include is not None and name not in include)):
            continue
        type_ = type(value)
        if value is None or type_ in (bool, bytes, float, int, str):
            setattr(copied, name, value)
        elif type_ in (types.FunctionType, types.LambdaType,
                       types.BuiltinFunctionType):
            def func_proxy(func):
                """Return a proxy for the given function."""
                # pylint: disable=unnecessary-lambda
                return lambda *args, **kwargs: func(*args, **kwargs)
            setattr(copied, name, func_proxy(value))
        elif type_ is type and value is not type:
            try:
                proxy = types.new_class(name, bases=(value,))
                proxy.mro = lambda: []
                setattr(copied, name, types.new_class(name, bases=(proxy,)))
            except TypeError:
                pass
    return copied


def safe_namespace(additional=None):
    """
    Create a new namespace containing only builtins and other objects which
    are deemed to be 'safe'. 'additional' can be a dictionary of additional
    items to put into the namespace.
    """
    namespace = {
        "__builtins__": dict(
            (name, getattr(__builtins__, name)) for name in _SAFE_BUILTINS),
        "__name__": "__script__",
        "__modules__": {},
    }
    namespace["__builtins__"].update(
        __import__=_safe_import,
        dir=_safe_dir,
        eval=_safe_eval,
        exec=_safe_exec,
        getattr=_safe_getattr,
        setattr=_safe_setattr,
        delattr=_safe_delattr,
    )
    if additional:
        namespace.update(additional)
    return namespace


def safe_exec(untrusted_source, additional=None):
    """
    Execute the given untrusted code in a new namespace.
    Returns the namespace so results can be extracted from it as necessary.
    """
    namespace = safe_namespace(additional)
    exec(safe_compile(untrusted_source, "<script>", "exec"), namespace)
    return namespace


def safe_eval(untrusted_source, additional=None):
    """
    Evaluates the given untrusted expression in a new namespace and
    returns its result.
    """
    return eval(safe_compile(untrusted_source, "<script>", "eval"),
                safe_namespace(additional))


class SafeInteractiveConsole(code.InteractiveConsole):
    """A safe version of code.InteractiveConsole."""

    def __init__(self, additional=None):
        super().__init__(locals=safe_namespace(additional))
        compiler = self.compile
        pass_code = compile("pass", "", "exec").co_code
        def safe_compiler(source, filename, symbol):
            """Compile and verify the code."""
            compiled = compiler(source, filename, symbol)
            if compiled is not None and compiled.co_code != pass_code:
                safe_compile(source, filename, symbol)
            return compiled
        self.compile = safe_compiler


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "-i":
        SafeInteractiveConsole(additional={"print": print}).interact()
    else:
        safe_exec(sys.stdin.read())
