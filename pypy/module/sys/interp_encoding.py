import sys
from rpython.rlib import rlocale
from rpython.rlib.objectmodel import we_are_translated

def getdefaultencoding(space):
    """Return the current default string encoding used by the Unicode
implementation."""
    return space.wrap(space.sys.defaultencoding)

if sys.platform == "win32":
    base_encoding = "mbcs"
elif sys.platform == "darwin":
    base_encoding = "utf-8"
elif sys.platform == "linux2":
    base_encoding = "ascii"
else:
    base_encoding = None

def _getfilesystemencoding(space):
    encoding = base_encoding
    if rlocale.HAVE_LANGINFO and rlocale.CODESET:
        try:
            oldlocale = rlocale.setlocale(rlocale.LC_CTYPE, None)
            rlocale.setlocale(rlocale.LC_CTYPE, "")
            try:
                loc_codeset = rlocale.nl_langinfo(rlocale.CODESET)
                if loc_codeset:
                    codecmod = space.getbuiltinmodule('_codecs')
                    w_res = space.call_method(codecmod, 'lookup',
                                              space.wrap(loc_codeset))
                    if space.is_true(w_res):
                        w_name = space.getattr(w_res, space.wrap('name'))
                        encoding = space.str_w(w_name)
            finally:
                rlocale.setlocale(rlocale.LC_CTYPE, oldlocale)
        except rlocale.LocaleError:
            pass
    return encoding

def getfilesystemencoding(space):
    """Return the encoding used to convert Unicode filenames in
    operating system filenames.
    """
    if space.sys.filesystemencoding is None:
        return space.wrap(base_encoding)
    return space.wrap(space.sys.filesystemencoding)
