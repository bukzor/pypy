from pypy.interpreter.mixedmodule import MixedModule

class Module(MixedModule):
    """Implementation module for SSL socket operations.
    See the socket module for documentation."""

    interpleveldefs = {
        'SSLError': 'interp_ssl.get_error(space).w_error',
        'SSLZeroReturnError': 'interp_ssl.get_error(space).w_ZeroReturnError',
        'SSLWantReadError': 'interp_ssl.get_error(space).w_WantReadError',
        'SSLWantWriteError': 'interp_ssl.get_error(space).w_WantWriteError',
        'SSLEOFError': 'interp_ssl.get_error(space).w_EOFError',
        'SSLSyscallError': 'interp_ssl.get_error(space).w_SyscallError',
        '_SSLSocket': 'interp_ssl.SSLSocket',
        '_SSLContext': 'interp_ssl.SSLContext',
        '_test_decode_cert': 'interp_ssl._test_decode_cert',
    }

    appleveldefs = {
    }

    @classmethod
    def buildloaders(cls):
        # init the SSL module
        from pypy.module._ssl.interp_ssl import constants, HAVE_OPENSSL_RAND

        for constant, value in constants.iteritems():
            Module.interpleveldefs[constant] = "space.wrap(%r)" % (value,)

        if HAVE_OPENSSL_RAND:
            Module.interpleveldefs['RAND_add'] = "interp_ssl.RAND_add"
            Module.interpleveldefs['RAND_bytes'] = "space.w_None"  # so far
            Module.interpleveldefs['RAND_pseudo_bytes'] = "space.w_None"  # so far
            Module.interpleveldefs['RAND_status'] = "interp_ssl.RAND_status"
            Module.interpleveldefs['RAND_egd'] = "interp_ssl.RAND_egd"

        super(Module, cls).buildloaders()

    def startup(self, space):
        from rpython.rlib.ropenssl import init_ssl
        init_ssl()
        if space.config.objspace.usemodules.thread:
            from pypy.module._ssl.thread_lock import setup_ssl_threads
            setup_ssl_threads()
