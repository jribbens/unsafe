unsafe - Experiments in execution of untrusted Python code
==========================================================

This is a little experiment to see to what extent, if any, it is possible to
run untrusted Python (or at least Python-like) code under Python 3 while
successfully preventing it from escaping the sandbox it's put inside.

Python used to have an `rexec` module which tried to do something similar, but
with the advent of new-style classes in Python 2.2 it was abandoned as being
too complex and unworkable. However, in Python 2.6 the `ast` module was added,
which may provide a way to make restricted execution workable again by
detecting if the code is trying to access any 'private' variables or attributes
(i.e. those with names beginning with `_`) and refusing to run it if so.

So, the challenge is to see if you can write a script that will successfully
break out of the sandbox when passed to `unsafe.safe_eval()` or
`unsafe.safe_exec()`. Note that 'denial of service' does not count - it is
trivially easy to either hang forever or to use up all the memory that the
operating system will allow.

**Do not use this code for any purpose in the real world.**


Interface
---------

The script will execute Python code passed to it on `stdin` - i.e. you can run
things with a command like `./unsafe.py <script.py`. There is also a REPL mode
you can enter with `./unsafe.py -i`, which is useful for trying things out.

The public code interfaces are `safe_exec(untrusted_source, additional=None)`
and `safe_eval(untrusted_source, additional=None)`. If `additional` is provided
then it should be a dictionary of extra items to add to the namespace that the
untrusted code is executed within.

`safe_exec` returns the namespace, so that results can be extracted from it,
and `safe_eval` of course returns the value of the expression - but callers
must bear in mind that the values returned might be cleverly constructed
objects with malicious methods (e.g. subclasses of `str` with `__eq__`
overridden).


Namespace
---------

The namespace provided to untrusted code is of course restricted. I have
provided access to nearly all of Python's standard builtins, but some things
such as `type`, `vars`, `globals`, etc are blocked. `import` is allowed,
but only of a restricted subset of white-listed standard library modules.
