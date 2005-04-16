import py
from pypy.interpreter.gateway import app2interp_temp 
from pypy.interpreter.error import OperationError
from pypy.tool import pytestsupport
from inspect import isclass

rootdir = py.magic.autopath().dirpath()

#
# PyPy's command line extra options (these are added 
# to py.test's standard options) 
#
Option = py.test.Config.Option

#class Options: 
#    group = "pypy options" 
#    optionlist = 

option = py.test.Config.addoptions("pypy options", 
        Option('-O', '--objspace', action="store", default=None, 
               type="string", dest="objspacename", 
               help="object space to run tests on."),
        Option('--oldstyle', action="store_true",dest="oldstyle", default=False,
               help="enable oldstyle classes as default metaclass (std objspace only)"),
        Option('--allpypy', action="store_true",dest="allpypy", default=False, 
               help="run everything possible on top of PyPy."),
    )

def getobjspace(name=None, _spacecache={}): 
    """ helper for instantiating and caching space's for testing. 
    """ 
    if name is None: 
        name = option.objspacename 
        if name is None:
            name = py.std.os.environ.get('OBJSPACE', 'std')
    else:
        optionname = option.objspacename 
        if optionname is not None and optionname != name:
            return None
    try:
        return _spacecache[name]
    except KeyError:
        #py.magic.invoke(compile=True)
        module = __import__("pypy.objspace.%s" % name, None, None, ["Space"])
        try: 
            space = module.Space()
        except KeyboardInterrupt: 
            raise 
        except OperationError, e: 
            # we cannot easily convert w_KeyboardInterrupt to
            # KeyboardInterrupt so we have to jump through hoops 
            try: 
                if e.w_type.name == 'KeyboardInterrupt': 
                    raise KeyboardInterrupt 
            except AttributeError: 
                pass 
            if option.verbose:  
                import traceback 
                traceback.print_exc() 
            py.test.fail("fatal: cannot initialize objspace:  %r" %(module.Space,))
        _spacecache[name] = space
        if name == 'std' and option.oldstyle: 
            space.enable_old_style_classes_as_default_metaclass()
        if name != 'flow': # not sensible for flow objspace case
            space.setitem(space.builtin.w_dict, space.wrap('AssertionError'), 
                          pytestsupport.build_pytest_assertion(space))
            space.setitem(space.builtin.w_dict, space.wrap('raises'),
                          space.wrap(pytestsupport.app_raises))
            space.setitem(space.builtin.w_dict, space.wrap('skip'),
                          space.wrap(pytestsupport.app_skip))
            space.raises_w = pytestsupport.raises_w.__get__(space)
            space.eq_w = pytestsupport.eq_w.__get__(space) 
        return space

# 
# Interfacing/Integrating with py.test's collection process 
#

class Module(py.test.collect.Module): 
    """ we take care of collecting classes both at app level 
        and at interp-level (because we need to stick a space 
        at the class) ourselves. 
    """
    def funcnamefilter(self, name): 
        return name.startswith('test_') or name.startswith('app_test_')
    def classnamefilter(self, name): 
        return name.startswith('Test') or name.startswith('AppTest') 

    def setup(self): 
        # stick py.test raise in module globals
        self.obj.raises = py.test.raises 
        super(Module, self).setup() 
        #    if hasattr(mod, 'objspacename'): 
        #        mod.space = getttestobjspace(mod.objspacename)

    def join(self, name): 
        obj = getattr(self.obj, name) 
        if isclass(obj): 
            if name.startswith('AppTest'): 
                return AppClassCollector(name, parent=self) 
            else: 
                return IntClassCollector(name, parent=self) 
        elif hasattr(obj, 'func_code'): 
            if name.startswith('app_test_'): 
                assert not obj.func_code.co_flags & 32, \
                    "generator app level functions? you must be joking" 
                return AppTestFunction(name, parent=self) 
            elif obj.func_code.co_flags & 32: # generator function 
                return self.Generator(name, parent=self) 
            else: 
                return IntTestFunction(name, parent=self) 

def gettestobjspace(name=None):
    space = getobjspace(name)
    if space is None:
        py.test.skip('test requires object space %r' % (name,))
    return space


class PyPyTestFunction(py.test.Function):
    # All PyPy test items catch and display OperationErrors specially.

    def execute_appex(self, space, target, *args):
        try:
            target(*args)
        except OperationError, e:
            if e.match(space, space.w_KeyboardInterrupt): 
                raise KeyboardInterrupt 
            appexcinfo = pytestsupport.AppExceptionInfo(space, e) 
            if appexcinfo.traceback: 
                raise self.Failed(excinfo=pytestsupport.AppExceptionInfo(space, e))
            raise 

class IntTestFunction(PyPyTestFunction):
    def execute(self, target, *args):
        co = target.func_code
        if 'space' in co.co_varnames[:co.co_argcount]: 
            name = target.func_globals.get('objspacename', None) 
            space = gettestobjspace(name) 
            target(space, *args)  
        else:
            target(*args)

class AppTestFunction(PyPyTestFunction): 
    def execute(self, target, *args):
        assert not args 
        name = target.func_globals.get('objspacename', None) 
        space = gettestobjspace(name) 
        func = app2interp_temp(target)
        print "executing", func
        self.execute_appex(space, func, space)

class AppTestMethod(PyPyTestFunction): 
    def execute(self, target, *args): 
        assert not args 
        space = target.im_self.space 
        func = app2interp_temp(target.im_func) 
        self.execute_appex(space, func, space, space.w_None)

class IntClassCollector(py.test.collect.Class): 
    Function = IntTestFunction 

    def setup(self): 
        cls = self.obj 
        name = getattr(cls, 'objspacename', None) 
        if name is None: 
            m = __import__(cls.__module__, {}, {}, ["objspacename"])
            name = getattr(m, 'objspacename', None) 
        cls.space = gettestobjspace(name) 
        super(IntClassCollector, self).setup() 

class AppClassInstance(py.test.collect.Instance): 
    Function = AppTestMethod 

class AppClassCollector(IntClassCollector): 
    Instance = AppClassInstance 

