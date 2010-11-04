import py
import sys
from pypy.conftest import gettestobjspace

class AppTestWarnings:
    def setup_class(cls):
        space = gettestobjspace(usemodules=('_warnings',))
        cls.space = space

    def test_defaults(self):
        import _warnings
        assert _warnings.once_registry == {}
        assert _warnings.default_action == 'default'
        assert "PendingDeprecationWarning" in str(_warnings.filters)

    def test_warn(self):
        import _warnings
        _warnings.warn("some message", DeprecationWarning)
        _warnings.warn("some message", Warning)

    def test_warn_explicit(self):
        import _warnings
        _warnings.warn_explicit("some message", DeprecationWarning,
                                "<string>", 1, module_globals=globals())
        _warnings.warn_explicit("some message", Warning,
                                "<string>", 1, module_globals=globals())

    def test_default_action(self):
        import warnings, _warnings
        warnings.defaultaction = 'ignore'
        warnings.resetwarnings()
        with warnings.catch_warnings(record=True) as w:
            __warningregistry__ = {}
            _warnings.warn_explicit("message", UserWarning, "<test>", 44,
                                    registry={})
            assert len(w) == 0
        warnings.defaultaction = 'default'



