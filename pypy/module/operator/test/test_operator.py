# -*- coding: utf-8 -*-

class AppTestOperator:
    def test_equality(self):
        import operator
        assert operator.eq == operator.__eq__

    def test_getters_are_not_regular_functions(self):
        import operator
        class A(object):
            getx = operator.attrgetter('x')
            get3 = operator.itemgetter(3)
        a = A()
        a.x = 5
        assert a.getx(a) == 5
        assert a.get3("foobar") == "b"
        assert a.getx(*(a,)) == 5

    def test_getter_multiple_gest(self):
        import operator

        class A(object):
            pass

        a = A()
        a.x = 'X'
        a.y = 'Y'
        a.z = 'Z'

        assert operator.attrgetter('x','z','y')(a) == ('X', 'Z', 'Y')
        raises(TypeError, operator.attrgetter, ('x', (), 'y'))

        data = list(map(str, range(20)))
        assert operator.itemgetter(2,10,5)(data) == ('2', '10', '5')
        raises(TypeError, operator.itemgetter(2, 'x', 5), data)

    def test_attrgetter(self):
        import operator
        raises(TypeError, operator.attrgetter, 2)

    def test_dotted_attrgetter(self):
        from operator import attrgetter
        class A:
            pass
        a = A()
        a.name = "hello"
        a.child = A()
        a.child.name = "world"
        assert attrgetter("child.name")(a) == "world"

    def test_concat(self):
        class Seq1:
            def __init__(self, lst):
                self.lst = lst
            def __len__(self):
                return len(self.lst)
            def __getitem__(self, i):
                return self.lst[i]
            def __add__(self, other):
                return self.lst + other.lst
            def __mul__(self, other):
                return self.lst * other
            def __rmul__(self, other):
                return other * self.lst

        class Seq2(object):
            def __init__(self, lst):
                self.lst = lst
            def __len__(self):
                return len(self.lst)
            def __getitem__(self, i):
                return self.lst[i]
            def __add__(self, other):
                return self.lst + other.lst
            def __mul__(self, other):
                return self.lst * other
            def __rmul__(self, other):
                return other * self.lst

        import operator

        raises(TypeError, operator.concat)
        raises(TypeError, operator.concat, None, None)
        assert operator.concat('py', 'thon') == 'python'
        assert operator.concat([1, 2], [3, 4]) == [1, 2, 3, 4]
        assert operator.concat(Seq1([5, 6]), Seq1([7])) == [5, 6, 7]
        assert operator.concat(Seq2([5, 6]), Seq2([7])) == [5, 6, 7]
        raises(TypeError, operator.concat, 13, 29)

    def test_mul(self):
        class Seq1:
            def __init__(self, lst):
                self.lst = lst
            def __len__(self):
                return len(self.lst)
            def __getitem__(self, i):
                return self.lst[i]
            def __add__(self, other):
                return self.lst + other.lst
            def __mul__(self, other):
                return self.lst * other
            def __rmul__(self, other):
                return other * self.lst

        class Seq2(object):
            def __init__(self, lst):
                self.lst = lst
            def __len__(self):
                return len(self.lst)
            def __getitem__(self, i):
                return self.lst[i]
            def __add__(self, other):
                return self.lst + other.lst
            def __mul__(self, other):
                return self.lst * other
            def __rmul__(self, other):
                return other * self.lst

        import operator

        a = list(range(3))
        raises(TypeError, operator.mul)
        raises(TypeError, operator.mul, a, None)
        assert operator.mul(a, 2) == a+a
        assert operator.mul(a, 1) == a
        assert operator.mul(a, 0) == []
        a = (1, 2, 3)
        assert operator.mul(a, 2) == a+a
        assert operator.mul(a, 1) == a
        assert operator.mul(a, 0) == ()
        a = '123'
        assert operator.mul(a, 2) == a+a
        assert operator.mul(a, 1) == a
        assert operator.mul(a, 0) == ''
        a = Seq1([4, 5, 6])
        assert operator.mul(a, 2) == [4, 5, 6, 4, 5, 6]
        assert operator.mul(a, 1) == [4, 5, 6]
        assert operator.mul(a, 0) == []
        a = Seq2([4, 5, 6])
        assert operator.mul(a, 2) == [4, 5, 6, 4, 5, 6]
        assert operator.mul(a, 1) == [4, 5, 6]
        assert operator.mul(a, 0) == []

    def test_iadd(self):
        import operator

        list = []
        assert operator.iadd(list, [1, 2]) is list
        assert list == [1, 2]

    def test_imul(self):
        import operator

        class X(object):
            def __index__(self):
                return 5

        a = list(range(3))
        raises(TypeError, operator.imul)
        raises(TypeError, operator.imul, a, None)
        raises(TypeError, operator.imul, a, [])
        assert operator.imul(a, 2) is a
        assert a == [0, 1, 2, 0, 1, 2]
        assert operator.imul(a, 1) is a
        assert a == [0, 1, 2, 0, 1, 2]

    def test_methodcaller(self):
        from operator import methodcaller
        class X(object):
            def method(self, arg1=2, arg2=3):
                return arg1, arg2
        x = X()
        assert methodcaller("method")(x) == (2, 3)
        assert methodcaller("method", 4)(x) == (4, 3)
        assert methodcaller("method", 4, 5)(x) == (4, 5)
        assert methodcaller("method", 4, arg2=42)(x) == (4, 42)

    def test_index(self):
        import operator
        assert operator.index(42) == 42
        assert operator.__index__(42) == 42
        raises(TypeError, operator.index, "abc")
        exc = raises(TypeError, operator.index, "abc")
        assert str(exc.value) == "'str' object cannot be interpreted as an integer"

    def test_indexOf(self):
        import operator
        raises(TypeError, operator.indexOf)
        raises(TypeError, operator.indexOf, None, None)
        assert operator.indexOf([4, 3, 2, 1], 3) == 1
        raises(ValueError, operator.indexOf, [4, 3, 2, 1], 0)

    def test_compare_digest(self):
        import operator

        # Testing input type exception handling
        a, b = 100, 200
        raises(TypeError, operator._compare_digest, a, b)
        a, b = 100, b"foobar"
        raises(TypeError, operator._compare_digest, a, b)
        a, b = b"foobar", 200
        raises(TypeError, operator._compare_digest, a, b)
        a, b = u"foobar", b"foobar"
        raises(TypeError, operator._compare_digest, a, b)
        a, b = b"foobar", u"foobar"
        raises(TypeError, operator._compare_digest, a, b)

        # Testing bytes of different lengths
        a, b = b"foobar", b"foo"
        assert not operator._compare_digest(a, b)
        a, b = b"\xde\xad\xbe\xef", b"\xde\xad"
        assert not operator._compare_digest(a, b)

        # Testing bytes of same lengths, different values
        a, b = b"foobar", b"foobaz"
        assert not operator._compare_digest(a, b)
        a, b = b"\xde\xad\xbe\xef", b"\xab\xad\x1d\xea"
        assert not operator._compare_digest(a, b)

        # Testing bytes of same lengths, same values
        a, b = b"foobar", b"foobar"
        assert operator._compare_digest(a, b)
        a, b = b"\xde\xad\xbe\xef", b"\xde\xad\xbe\xef"
        assert operator._compare_digest(a, b)

        # Testing bytearrays of same lengths, same values
        a, b = bytearray(b"foobar"), bytearray(b"foobar")
        assert operator._compare_digest(a, b)

        # Testing bytearrays of diffeent lengths
        a, b = bytearray(b"foobar"), bytearray(b"foo")
        assert not operator._compare_digest(a, b)

        # Testing bytearrays of same lengths, different values
        a, b = bytearray(b"foobar"), bytearray(b"foobaz")
        assert not operator._compare_digest(a, b)

        # Testing byte and bytearray of same lengths, same values
        a, b = bytearray(b"foobar"), b"foobar"
        assert operator._compare_digest(a, b)
        assert operator._compare_digest(b, a)

        # Testing byte bytearray of diffeent lengths
        a, b = bytearray(b"foobar"), b"foo"
        assert not operator._compare_digest(a, b)
        assert not operator._compare_digest(b, a)

        # Testing byte and bytearray of same lengths, different values
        a, b = bytearray(b"foobar"), b"foobaz"
        assert not operator._compare_digest(a, b)
        assert not operator._compare_digest(b, a)

        # Testing str of same lengths
        a, b = "foobar", "foobar"
        assert operator._compare_digest(a, b)

        # Testing str of diffeent lengths
        a, b = "foo", "foobar"
        assert not operator._compare_digest(a, b)

        # Testing bytes of same lengths, different values
        a, b = "foobar", "foobaz"
        assert not operator._compare_digest(a, b)

        # Testing error cases
        a, b = u"foobar", b"foobar"
        raises(TypeError, operator._compare_digest, a, b)
        a, b = b"foobar", u"foobar"
        raises(TypeError, operator._compare_digest, a, b)
        a, b = b"foobar", 1
        raises(TypeError, operator._compare_digest, a, b)
        a, b = 100, 200
        raises(TypeError, operator._compare_digest, a, b)
        a, b = "fooä", "fooä"
        raises(TypeError, operator._compare_digest, a, b)

        # subclasses are supported by ignore __eq__
        class mystr(str):
            def __eq__(self, other):
                return False

        a, b = mystr("foobar"), mystr("foobar")
        assert operator._compare_digest(a, b)
        a, b = mystr("foobar"), "foobar"
        assert operator._compare_digest(a, b)
        a, b = mystr("foobar"), mystr("foobaz")
        assert not operator._compare_digest(a, b)

        class mybytes(bytes):
            def __eq__(self, other):
                return False

        a, b = mybytes(b"foobar"), mybytes(b"foobar")
        assert operator._compare_digest(a, b)
        a, b = mybytes(b"foobar"), b"foobar"
        assert operator._compare_digest(a, b)
        a, b = mybytes(b"foobar"), mybytes(b"foobaz")
        assert not operator._compare_digest(a, b)

    def test_compare_digest_unicode(self):
        import operator
        assert operator._compare_digest(u'asd', u'asd')
        assert not operator._compare_digest(u'asd', u'qwe')
        raises(TypeError, operator._compare_digest, u'asd', b'qwe')
