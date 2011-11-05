import py
from pypy.objspace.std.tupleobject import W_TupleObject
from pypy.objspace.std.specialisedtupleobject import W_SpecialisedTupleObject,W_SpecialisedTupleObjectIntInt
from pypy.interpreter.error import OperationError
from pypy.conftest import gettestobjspace
#from pypy.objspace.std.test.test_tupleobject import AppTestW_TupleObject
from pypy.interpreter import gateway


class TestW_SpecialisedTupleObject():

    def setup_class(cls):
        cls.space = gettestobjspace(**{"objspace.std.withspecialisedtuple": True})

    def test_isspecialisedtupleobjectintint(self):
        w_tuple = self.space.newtuple([self.space.wrap(1), self.space.wrap(2)])
        assert isinstance(w_tuple, W_SpecialisedTupleObjectIntInt)
        
    def test_isnotspecialisedtupleobject(self):
        w_tuple = self.space.newtuple([self.space.wrap({})])
        assert not isinstance(w_tuple, W_SpecialisedTupleObject)
        
    def test_hash_against_normal_tuple(self):
        normalspace = gettestobjspace(**{"objspace.std.withspecialisedtuple": False})
        w_tuple = normalspace.newtuple([self.space.wrap(1), self.space.wrap(2)])

        specialisedspace = gettestobjspace(**{"objspace.std.withspecialisedtuple": True})
        w_specialisedtuple = specialisedspace.newtuple([self.space.wrap(1), self.space.wrap(2)])

        assert isinstance(w_specialisedtuple, W_SpecialisedTupleObject)
        assert isinstance(w_tuple, W_TupleObject)
        assert not normalspace.is_true(normalspace.eq(w_tuple, w_specialisedtuple))
        assert specialisedspace.is_true(specialisedspace.eq(w_tuple, w_specialisedtuple))
        assert specialisedspace.is_true(specialisedspace.eq(normalspace.hash(w_tuple), specialisedspace.hash(w_specialisedtuple)))

    def test_setitem(self):
        py.test.skip('skip for now, only needed for cpyext')
        w_specialisedtuple = self.space.newtuple([self.space.wrap(1)])
        w_specialisedtuple.setitem(0, self.space.wrap(5))
        list_w = w_specialisedtuple.tolist()
        assert len(list_w) == 1
        assert self.space.eq_w(list_w[0], self.space.wrap(5))        

class AppTestW_SpecialisedTupleObject(object):

    def setup_class(cls):
        cls.space = gettestobjspace(**{"objspace.std.withspecialisedtuple": True})
        def forbid_delegation(space, w_tuple):
            def delegation_forbidden():
                raise NotImplementedError
            w_tuple.tolist = delegation_forbidden
            return w_tuple
        cls.w_forbid_delegation = cls.space.wrap(gateway.interp2app(forbid_delegation))
            
        
    
    def w_isspecialised(self, obj):
       import __pypy__
       return "SpecialisedTuple" in __pypy__.internal_repr(obj)
        


    def test_specialisedtuple(self):
        assert self.isspecialised((42,43))
        
    def test_len(self):
        t = self.forbid_delegation((42,43))
        assert len(t) == 2

    def test_notspecialisedtuple(self):
        assert not self.isspecialised((42,43,44))
        
    def test_slicing_to_specialised(self):
        assert self.isspecialised((1, 2, 3)[0:2])   
        assert self.isspecialised((1, '2', 3)[0:5:2])

    def test_adding_to_specialised(self):
        assert self.isspecialised((1,)+(2,))

    def test_multiply_to_specialised(self):
        assert self.isspecialised((1,)*2)

    def test_slicing_from_specialised(self):
        assert (1,2,3)[0:2:1] == (1,2)

    def test_eq(self):
        a = self.forbid_delegation((1,2))
        b = (1,2)
        assert a == b
        
        c = (1,3,2)
        assert not a == c

    def test_hash(self):
        a = (1,2)
        b = (1,2)
        assert hash(a) == hash(b)

        c = (2,4)
        assert hash(a) != hash(c)

    def test_getitem(self):
        t = self.forbid_delegation((5,3))
        assert (t)[0] == 5
        assert (t)[1] == 3
        assert (t)[-1] == 3
        assert (t)[-2] == 5
        raises(IndexError, "t[2]")
        
        
        
        
        
        
