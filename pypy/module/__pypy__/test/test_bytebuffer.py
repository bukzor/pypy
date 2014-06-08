class AppTest(object):
    spaceconfig = dict(usemodules=['__pypy__'])

    def test_bytebuffer(self):
        from __pypy__ import bytebuffer
        b = bytebuffer(12)
        assert len(b) == 12
        b[3] = b'!'
        b[5] = b'?'
        assert b[2:7] == b'\x00!\x00?\x00'
        b[9:] = b'+-*'
        assert b[-1] == b'*'
        assert b[-2] == b'-'
        assert b[-3] == b'+'
        exc = raises(ValueError, "b[3] = b'abc'")
        assert str(exc.value) == "cannot modify size of memoryview object"
        exc = raises(ValueError, "b[3:5] = b'abc'")
        assert str(exc.value) == "cannot modify size of memoryview object"
        raises(NotImplementedError, "b[3:7:2] = b'abc'")

        b = bytebuffer(10)
        b[1:3] = b'xy'
        assert bytes(b) == b"\x00xy" + b"\x00" * 7
        # XXX: supported in 3.3
        raises(NotImplementedError, "b[4:8:2] = b'zw'")
        #b[4:8:2] = b'zw'
        #assert bytes(b) == b"\x00xy\x00z\x00w" + b"\x00" * 3
