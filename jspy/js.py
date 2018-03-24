"""Module containing basic JavaScript types and objects."""
from collections import namedtuple
import sys
import math
import ast
import re
from jspy import terminalsize

UNDEFINED = object()
EMPTY = object()
NORMAL = object()
BREAK = object()
CONTINUE = object()
RETURN = object()
THROW = object()

# Completion specification type as defined in [ECMA-262 8.9]
Completion = namedtuple('Completion', 'type value target')

EMPTY_COMPLETION = Completion(NORMAL, EMPTY, EMPTY)


def is_abrupt(completion):
    return completion.type is not NORMAL


def to_python(value):
    if isinstance(value, (Object, Function, NativeFunction)):
        return value.to_python()
    else:
        return value


class Object(object):
    """JavaScript Object as defined in [ECMA-262 8.6]."""

    def __init__(self, items=None):
        if items is None:
            items = {}
        self.d = items

    def __getitem__(self, name):
        return self.d[str(name)]

    def __setitem__(self, name, value):
        self.d[str(name)] = value

    def get(self, name):
        try:
            return self.d[str(name)]
        except KeyError:
            return UNDEFINED

    def get_binding_value(self, name):
        return self[name]

    def set_mutable_binding(self, name, value):
        self[name] = value

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.d)

    def __eq__(self, other):
        return self.d == other.d

    def to_python(self):
        result = {}
        for key, value in self.d.items():
            result[key] = to_python(value)
        return result


class Array(Object):
    """JavaScript Array as defined in [ECMA-262 15.4]."""
    max_repr_len = 23

    def __init__(self, items=None):
        if items is None:
            items = []
        self.items = []
        for i, item in enumerate(items):
            self.items.append(item)

    def __getitem__(self, name):
        if name == "length":
            return len(self.items)
        try:
            return self.items[int(name)]
        except KeyError:
            return UNDEFINED

    def __setitem__(self, name, value):
        while (int(name) >= len(self.items)):
            self.items.append(UNDEFINED)
        self.items[int(name)] = value

    def get(self, name):
        try:
            return self.items[name]
        except KeyError:
            return UNDEFINED

    def get_binding_value(self, name):
        return self[name]

    def set_mutable_binding(self, name, value):
        self[name] = value

    def __repr__(self):
        items = list(sorted((int(key), value) for key, value in self.items))
        max_key = items[-1][0] if len(items) > 0 else -1
        shown_items = [
            self.get(i) for i in range(0,
                                       min(max_key, self.max_repr_len) + 1)
        ]
        return 'Array(%r)' % shown_items

    def __str__(self):
        return '[%s]' % ', '.join(str(item) for item in self.items)

    def to_python(self):
        return [
            to_python(value)
            for key, value in sorted(self.items, key=lambda x: x[0])
        ]


class StringObject(Object):
    """JavaScript Array as defined in [ECMA-262 15.4]."""

    def __init__(self, value=""):

        self.value = value

    def __getitem__(self, name):
        if name == "length":
            return len(self.value)
        return self.value[int(name)]

    def __setitem__(self, name, value):
        #r'''(\"\"\"|\'\'\'|\"|\')((?<!\\)(\\\\)*\\\1|.)*?\1'''
        self.value = self.value[:int(name)] + value + self.value[1 + int(name):]
        #self.value[int(name)] = value

    def __add__(self, other):
        return StringObject(value=self.value + other)

    def __radd__(self, other):
        return other + self.value

    def get(self, name):
        try:
            return self.value[name]
        except KeyError:
            return UNDEFINED

    def get_binding_value(self, name):
        return self[name]

    def set_mutable_binding(self, name, value):
        self[name] = value

    def __repr__(self):
        return 'String(%r)' % self.value

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if (type(other) != str and type(other) != StringObject):
            return False
        if (type(other) == StringObject):
            return self.value == other.value
        if (type(other) == str):
            return self.value == other
        return False

    def to_python(self):
        return self.value


class Function(object):
    """Function object as defined in [ECMA-262 15.3].

    Algorithm for creating Function objects is in [ECMA-262 13.2]."""

    def __init__(self, parameters, body, scope):
        self.parameters = parameters
        self.body = body
        self.scope = scope
        self.horizontal = None
        self.declared_vars = []  #body.get_declared_vars()

    def call(self, this, args, scope=None):
        """Internal [[Call]] method of Function object.

        See [ECMA-262 13.2.1] for a basic algorithm."""
        if (not (scope == None)):
            #print("SCOPEPEPEP")
            self.horizontal = scope
            function_context = self.prepare_function_context(args)
            result = self.body.eval(function_context)
            if result.type is RETURN:
                return result.value
            else:
                # No return statement in function
                return UNDEFINED
        else:
            #print("SCOPEPEPEP 2")
            function_context = self.prepare_function_context(args)
            result = self.body.eval(function_context)
            if result.type is RETURN:
                return result.value
            else:
                # No return statement in function
                return UNDEFINED

    def prepare_function_context(self, args):
        local_vars_dict = dict(
            (name, UNDEFINED) for name in self.declared_vars)
        local_vars_dict.update(self.prepare_args_dict(args))
        return ExecutionContext(
            local_vars_dict, parent=self.scope, horizontal=self.horizontal)

    def prepare_args_dict(self, args):
        result = {'arguments': args}
        for name in self.parameters:
            result[name] = UNDEFINED
        for name, value in zip(self.parameters, args):
            result[name] = value
        return result

    def __repr__(self):
        return 'Function( scope=%r)' % (self.scope)

    def to_python(self):
        raise ValueError('Can\'t convert JavaScript function to Python')


class NativeFunction(object):
    """Function implemented in Python, callable from JavaScript code."""

    def __init__(self, f):
        self.f = f

    def call(self, this, args, scope=None):
        return self.f(this, args)

    def __repr__(self):
        return 'NativeFunction(f=%r)' % (self.f)

    def to_python(self):
        return self.f


class StaticNativeFunction(object):
    """Function implemented in Python, callable from JavaScript code."""

    def __init__(self, f):
        self.f = f

    def call(self, this, args, scope=None):
        return self.f(*args)

    def __repr__(self):
        return 'NativeFunction(f=%r)' % (self.f)

    def to_python(self):
        return self.f


class Console(Object):
    """Global `console` object, behaving similar to Firebug's one."""

    def __init__(self, out=None):
        self.out = out if out is not None else sys.stdout
        self.d = {
            'log': NativeFunction(self.log),
            'size': NativeFunction(self.size)
        }

    def log(self, this, args):
        self.out.write(' '.join(str(arg) for arg in args))
        self.out.write('\n')

    def size(self, this, args):
        try:
            tsize = terminalsize.get_terminal_size()
            print(tsize)
            return Object(items={"columns": tsize[0], "rows": tsize[1]})
        except Exception:
            return UNDEFINED


class Math(Object):
    """Global `Math` object, behaving similar to JS one."""

    def __init__(self):
        self.d = {
            'E': math.e,
            'PI': math.pi,
            'abs': NativeFunction(self.abs),
            'acos': NativeFunction(self.acos),
            'acosh': NativeFunction(self.acosh),
            'asin': NativeFunction(self.asin),
            'asinh': NativeFunction(self.asinh),
            'atan': StaticNativeFunction(math.atan),
            'atanh': StaticNativeFunction(math.atanh),
            'atan2': StaticNativeFunction(math.atan2),
            'cbrt': NativeFunction(self.cbrt),
            'ceil': StaticNativeFunction(math.ceil),
            'cos': StaticNativeFunction(math.cos),
            'cosh': StaticNativeFunction(math.cosh),
            'exp': StaticNativeFunction(math.exp),
            'pow': NativeFunction(self.pow),
            'sin': StaticNativeFunction(math.sin)
        }

    def abs(self, this, args):
        return abs(*args)

    def acos(self, this, args):
        return math.acos(*args)

    def acosh(self, this, args):
        return math.acosh(*args)

    def asin(self, this, args):
        return math.asin(*args)

    def asinh(self, this, args):
        return math.asinh(*args)

    def cbrt(self, this, args):
        return pow(args[0], 1.0 / 3)

    def pow(self, this, args):
        if args[0] == 0 and args[1] < 0:
            return float("inf")
        return pow(args[0], args[1])


class ReferenceError(RuntimeError):
    pass


class ExecutionContext(object):
    def __init__(self, env, parent=None, horizontal=None):
        assert isinstance(env, dict)
        self.env = env
        self.parent = parent
        self.horizontal = horizontal

    def __getitem__(self, name):
        try:
            return self.env[name]
        except KeyError:
            if self.parent is None and self.horizontal is None:
                return UNDEFINED
                #raise ReferenceError('Reference %r not found in %r' % (name, self))
            if not (self.horizontal is None) and (name in self.horizontal):
                return self.horizontal[name]
            return self.parent[name]

    def __setitem__(self, name, value):
        self.env[name] = value

    def __contains__(self, name):
        return name in self.env or (
            (self.parent is not None) and name in self.parent) or (
                (self.horizontal is not None) and name in self.horizontal)

    def get_binding_value(self, name):
        #print("GETTING",name)
        if name not in self.env:
            if not (self.horizontal is None) and (name in self.horizontal):
                return self.horizontal.get_binding_value(name)
            else:
                if not (self.parent is None) and (name in self.parent):
                    return self.parent.get_binding_value(name)
        #else:
        #print("GETTING (FOUND)",name)
        return self[name]

    def set_mutable_binding(self, name, value):
        if name not in self.env:
            if not (self.horizontal is None) and (name in self.horizontal):
                self.horizontal.set_mutable_binding(name, value)
            else:
                if not (self.parent is None) and (name in self.parent):
                    self.parent.set_mutable_binding(name, value)
                else:
                    if not (self.horizontal is None):
                        self.horizontal.set_mutable_binding(name, value)
                    else:
                        self.env[name] = value

        else:  #print("HAVE:",name,self.env[name])
            self.env[name] = value

    def get_this_reference(self):
        return self['this']

    def __repr__(self):
        return 'ExecutionContext(%r, parent=%r, horizontal=%r)' % (
            self.env, self.parent, self.horizontal)


class Reference(object):
    """JavaScript reference specification type as defined in [ECMA-262 8.7]."""

    def __init__(self, name, base):
        self.name = name
        self.base = base
        #print(base)

    def is_unresolvable(self):
        return self.base is UNDEFINED

    def has_primitive_base(self):
        return isinstance(self.base, (basestring, float, bool))

    def is_property(self):
        return isinstance(self.base, Object) or self.has_primitive_base()

    def get_value(self):
        if self.is_unresolvable():
            raise ReferenceError("%r is unresolvable" % self)
        return self.base.get_binding_value(self.name)

    def put_value(self, value):
        if self.is_unresolvable():
            raise ReferenceError("%r is unresolvable" % value)
        #print("BASE",self.base)
        #print("BASE H",self.base.horizontal)
        self.base.set_mutable_binding(self.name, value)

    def __repr__(self):
        return 'Reference(%r, %r)' % (self.name, self.base)


def get_value(obj):
    """Returns a value of `obj`, resolving a reference if needed.

    See [ECMA-262 8.7.1] for details."""
    if isinstance(obj, Reference):
        return obj.get_value()
    else:
        return obj


def put_value(obj, value):
    """Sets the value of `obj` reference to `value`.

    See [ECMA-262 8.7.2] for details."""
    if isinstance(obj, Reference):
        obj.put_value(value)
    else:
        raise ReferenceError(
            "Can't put a value of non-reference object %r" % obj)
