import pypy.module.cppyy.capi as capi

from pypy.interpreter.error import OperationError
from pypy.interpreter.gateway import ObjSpace, interp2app
from pypy.interpreter.typedef import TypeDef
from pypy.interpreter.baseobjspace import Wrappable

from pypy.rpython.lltypesystem import rffi, lltype

from pypy.rlib.libffi import CDLL
from pypy.rlib import jit, debug

from pypy.module.cppyy import converter, executor


NULL_VOIDP = lltype.nullptr(rffi.VOIDP.TO)

def load_lib(space, name):
    cdll = CDLL(name)
    return W_CPPLibrary(space, cdll)
load_lib.unwrap_spec = [ObjSpace, str]

class State(object):
    def __init__(self, space):
        self.cpptype_cache = {}

def type_byname(space, name):
    state = space.fromcache(State)
    try:
        return state.cpptype_cache[name]
    except KeyError:
        pass

    handle = capi.c_get_typehandle(name)
    if handle:
        cpptype = W_CPPType(space, name, handle)
        state.cpptype_cache[name] = cpptype
        cpptype._find_methods()
        cpptype._find_data_members()
        return cpptype

    raise OperationError(space.w_TypeError, space.wrap(str("no such C++ class %s" % name)))
type_byname.unwrap_spec = [ObjSpace, str]


class W_CPPLibrary(Wrappable):
    _immutable_ = True
    def __init__(self, space, cdll):
        self.cdll = cdll
        self.space = space

W_CPPLibrary.typedef = TypeDef(
    'CPPLibrary',
)

@jit.purefunction
def get_methptr_getter(handle, method_index):
    return capi.c_get_methptr_getter(handle, method_index)


class CPPMethod(object):
    """ A concrete function after overloading has been resolved """
    _immutable_ = True
    _immutable_fields_ = ["arg_types[*]", "arg_converters[*]"]
    
    def __init__(self, cpptype, method_index, result_type, arg_types):
        self.cpptype = cpptype
        self.space = cpptype.space
        self.method_index = method_index
        self.arg_types = arg_types
        self.executor = executor.get_executor(self.space, result_type)
        self.arg_converters = None
        # <hack>
        self.hack_call = arg_types == ['int'] and result_type == 'int'
        # </hack>

    def call(self, cppthis, args_w):
        if self.executor is None:
            raise OperationError(self.space.w_TypeError, self.space.wrap("return type not handled"))

        if self.hack_call:
            try:
                return self.do_hack_call(cppthis, args_w)
            except NotImplementedError:
                pass

        args = self.prepare_arguments(args_w)
        try:
            return self.executor.execute(self.space, self, cppthis, len(args_w), args)
        finally:
            self.free_arguments(args)

    INT_2_INT_FNPTR = lltype.Ptr(lltype.FuncType([rffi.VOIDP, rffi.INT],
                                                 rffi.INT))
    def do_hack_call(self, cppthis, args_w):
        # hack: only for methods 'int m(int)'
        space = self.space
        if len(args_w) != 1:
            raise OperationError(space.w_TypeError, space.wrap("wrong number of args"))
        arg = space.c_int_w(args_w[0])
        methgetter = get_methptr_getter(self.cpptype.handle,
                                        self.method_index)
        if not methgetter:
            raise NotImplementedError
        funcptr = methgetter(cppthis)
        funcptr = rffi.cast(self.INT_2_INT_FNPTR, funcptr)
        result = funcptr(cppthis, arg)
        return space.wrap(rffi.cast(lltype.Signed, result))

    def _build_converters(self):
        self.arg_converters = [converter.get_converter(self.space, arg_type)
                                   for arg_type in self.arg_types]

    @jit.unroll_safe
    def prepare_arguments(self, args_w):
        space = self.space
        if len(args_w) != len(self.arg_types):
            raise OperationError(space.w_TypeError, space.wrap("wrong number of args"))
        if self.arg_converters is None:
            self._build_converters()
        args = lltype.malloc(rffi.CArray(rffi.VOIDP), len(args_w), flavor='raw')
        for i in range(len(args_w)):
            conv = self.arg_converters[i]
            w_arg = args_w[i]
            try:
                 arg = conv.convert_argument(space, w_arg)
            except:
                # fun :-(
                for j in range(i):
                    conv = self.arg_converters[j]
                    conv.free_argument(args[j])
                lltype.free(args, flavor='raw')
                raise
            args[i] = arg
        return args

    def free_arguments(self, args):
        for i in range(len(self.arg_types)):
            conv = self.arg_converters[i]
            conv.free_argument(args[i])
        lltype.free(args, flavor='raw')

    def __repr__(self):
        return "CPPFunction(%s, %s, %r, %s)" % (
            self.cpptype, self.method_index, self.executor, self.arg_types)


class CPPFunction(CPPMethod):
    def call(self, cppthis, args_w):
        if self.executor is None:
            raise OperationError(self.space.w_TypeError, self.space.wrap("return type not handled"))

        assert not cppthis
        args = self.prepare_arguments(args_w)
        try:
            return self.executor.execute(self.space, self, NULL_VOIDP,
                                         len(args_w), args)
        finally:
            self.free_arguments(args)
 

class CPPConstructor(CPPMethod):
    def call(self, cppthis, args_w):
        assert not cppthis
        newthis = capi.c_allocate(self.cpptype.handle)
        try:
            CPPMethod.call(self, newthis, args_w)
        except Exception, e:
            capi.c_deallocate(self.cpptype.handle, newthis)
            raise
        return W_CPPInstance(self.space, self.cpptype, newthis)


class W_CPPOverload(Wrappable):
    _immutable_ = True
    _immutable_fields_ = ["functions[*]"]
    def __init__(self, space, func_name, functions):
        self.space = space
        self.func_name = func_name
        self.functions = debug.make_sure_not_resized(functions)

    def is_static(self):
        return self.space.wrap(isinstance(self.functions[0], CPPFunction))

    def get_returntype(self):
        try:
            return self.space.wrap(self.functions[0].executor.cpptype.name)
        except AttributeError:
            return None

    @jit.unroll_safe
    def call(self, cppthis, args_w):
        space = self.space
        errmsg = 'None of the overloads matched:'
        for i in range(len(self.functions)):
            cppyyfunc = self.functions[i]
            try:
                return cppyyfunc.call(cppthis, args_w)
            except OperationError, e:
                if not e.match(space, space.w_TypeError):
                    raise
                errmsg += '\n\t'+str(e)
            except KeyError:
                pass

        raise OperationError(space.w_TypeError, space.wrap(errmsg))

    def __repr__(self):
        return "W_CPPOverload(%s, %s)" % (self.func_name, self.functions)

W_CPPOverload.typedef = TypeDef(
    'CPPOverload',
    is_static = interp2app(W_CPPOverload.is_static, unwrap_spec=['self']),
    get_returntype = interp2app(W_CPPOverload.get_returntype, unwrap_spec=['self']),
)


class W_CPPDataMember(Wrappable):
    _immutable_fields_ = ["converter", "offset"]
    def __init__(self, space, cpptype, offset):
        self.space = space
        self.converter = converter.get_converter(self.space, cpptype)
        self.offset = offset

    def __get__(self, args_w):
        return self.converter.from_memory(self.space, args_w[0], self.offset)

    def __set__(self, args_w):
        self.converter.to_memory(self.space, args_w[0], args_w[1], self.offset)
        return None

W_CPPDataMember.typedef = TypeDef(
    'CPPDataMember',
    __get__ = interp2app(W_CPPDataMember.__get__, unwrap_spec=['self', 'args_w']),
    __set__ = interp2app(W_CPPDataMember.__set__, unwrap_spec=['self', 'args_w']),
)


class W_CPPType(Wrappable):
    _immutable_fields_ = ["name", "handle"]
    def __init__(self, space, name, handle):
        self.space = space
        self.name = name
        self.handle = handle
        self.methods = {}
        # Do not call "self._find_methods()" here, so that a distinction can
        #  be made between testing for existence (i.e. existence in the cache
        #  of classes) and actual use. Point being that a class can use itself,
        #  e.g. as a return type or an argument to one of its methods.

        self.data_members = {}
        # Idem self.methods: a type could hold itself by pointer.
    
    def _find_methods(self):
        num_methods = capi.c_num_methods(self.handle)
        args_temp = {}
        for i in range(num_methods):
            method_name = capi.charp2str_free(capi.c_method_name(self.handle, i))
            cppfunction = self._make_cppfunction(i)
            overload = args_temp.setdefault(method_name, [])
            overload.append(cppfunction)
        for name, functions in args_temp.iteritems():
            overload = W_CPPOverload(self.space, name, functions[:])
            self.methods[name] = overload

    def _make_cppfunction(self, method_index):
        result_type = capi.charp2str_free(capi.c_method_result_type(self.handle, method_index))
        num_args = capi.c_method_num_args(self.handle, method_index)
        argtypes = []
        for i in range(num_args):
            argtype = capi.charp2str_free(capi.c_method_arg_type(self.handle, method_index, i))
            argtypes.append(argtype)
        if capi.c_is_constructor(self.handle, method_index):
            cls = CPPConstructor
        elif capi.c_is_static(self.handle, method_index):
            cls = CPPFunction
        else:
            cls = CPPMethod
        return cls(self, method_index, result_type, argtypes)

    def _find_data_members(self):
        num_data_members = capi.c_num_data_members(self.handle)
        for i in range(num_data_members):
            data_member_name = capi.charp2str_free(capi.c_data_member_name(self.handle, i))
            cpptype = capi.charp2str_free(capi.c_data_member_type(self.handle, i))
            offset = capi.c_data_member_offset(self.handle, i)
            data_member = W_CPPDataMember(self.space, cpptype, offset)
            self.data_members[data_member_name] = data_member

    def get_method_names(self):
        return self.space.newlist([self.space.wrap(name) for name in self.methods])

    @jit.purefunction
    def get_overload(self, name):
        return self.methods[name]

    def get_data_member_names(self):
        return self.space.newlist([self.space.wrap(name) for name in self.data_members])

    @jit.purefunction
    def get_data_member(self, name):
        return self.data_members[name]

    def invoke(self, name, args_w):
        overload = self.get_overload(name)
        return overload.call(NULL_VOIDP, args_w)

    def construct(self, args_w):
        overload = self.get_overload(self.name)
        return overload.call(NULL_VOIDP, args_w)

W_CPPType.typedef = TypeDef(
    'CPPType',
    get_method_names = interp2app(W_CPPType.get_method_names, unwrap_spec=['self']),
    get_overload = interp2app(W_CPPType.get_overload, unwrap_spec=['self', str]),
    get_data_member_names = interp2app(W_CPPType.get_data_member_names, unwrap_spec=['self']),
    get_data_member = interp2app(W_CPPType.get_data_member, unwrap_spec=['self', str]),
    invoke = interp2app(W_CPPType.invoke, unwrap_spec=['self', str, 'args_w']),
    construct = interp2app(W_CPPType.construct, unwrap_spec=['self', 'args_w']),
)


class W_CPPInstance(Wrappable):
    def __init__(self, space, cppclass, rawobject):
        self.space = space
        self.cppclass = cppclass
        self.rawobject = rawobject

    def _nullcheck(self):
        if not self.rawobject:
            raise OperationError(self.space.w_ReferenceError, self.space.wrap("trying to access a NULL pointer"))

    def invoke(self, method_name, args_w):
        self._nullcheck()
        cppclass = jit.hint(self.cppclass, promote=True)
        overload = cppclass.get_overload(method_name)
        return overload.call(self.rawobject, args_w)

    def destruct(self):
        capi.c_destruct(self.cppclass.handle, self.rawobject)
        self.rawobject = NULL_VOIDP

W_CPPInstance.typedef = TypeDef(
    'CPPInstance',
    invoke = interp2app(W_CPPInstance.invoke, unwrap_spec=['self', str, 'args_w']),
    destruct = interp2app(W_CPPInstance.destruct, unwrap_spec=['self']),
)
