import os
from pypy.interpreter.mixedmodule import MixedModule
from pypy.module.sys import initpath

lib_python = os.path.join(os.path.dirname(__file__),
                          '..', '..', '..', 'lib-python', '3')

class Module(MixedModule):
    interpleveldefs = {
        }

    appleveldefs = {
        }

    def install(self):
        """NOT_RPYTHON"""
        super(Module, self).install()
        space = self.space
        # "from importlib/_boostrap.py import *"
        # It's not a plain "import importlib._boostrap", because we
        # don't want to freeze importlib.__init__.
        ec = space.getexecutioncontext()
        with open(os.path.join(lib_python, 'importlib', '_bootstrap.py')) as fp:
            source = fp.read()
        pathname = "<frozen importlib._bootstrap>"
        code_w = ec.compiler.compile(source, pathname, 'exec', 0)
        w_dict = space.newdict()
        space.setitem(w_dict, space.wrap('__name__'), self.w_name)
        code_w.exec_code(space, self.w_dict, self.w_dict)

    def startup(self, space):
        """Copy our __import__ to builtins."""
        w_install = self.getdictvalue(space, '_install')
        space.call_function(w_install,
                            space.getbuiltinmodule('sys'),
                            space.getbuiltinmodule('_imp'))
        self.space.builtin.setdictvalue(space, '__import__',
                                        self.getdictvalue(space, '__import__'))
