import py
from pypy.jit.metainterp import resoperation as rop
from pypy.jit.metainterp.history import AbstractDescr
from pypy.rpython.lltypesystem import lltype, llmemory

class FakeBox(object):
    def __init__(self, v):
        self.v = v

    def __eq__(self, other):
        if isinstance(other, str):
            return self.v == other
        return self.v == other.v

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.v)

    def __str__(self):
        return self.v

    def is_constant(self):
        return False

class FakeDescr(AbstractDescr):
    def __repr__(self):
        return 'descr'

    def _get_hash_(self):
        return id(self)

def test_arity_mixins():
    cases = [
        (0, rop.NullaryOp),
        (1, rop.UnaryOp),
        (2, rop.BinaryOp),
        (3, rop.TernaryOp),
        (9, rop.N_aryOp)
        ]

    def test_case(n, cls):
        obj = cls()
        obj.initarglist(range(n))
        assert obj.getarglist() == range(n)
        assert obj.numargs() == n
        for i in range(n):
            assert obj.getarg(i) == i
        py.test.raises(IndexError, obj.getarg, n+1)

    for n, cls in cases:
        test_case(n, cls)

def test_concrete_classes():
    cls = rop.opclasses[rop.rop.INT_ADD]
    assert issubclass(cls, rop.PlainResOp)
    assert issubclass(cls, rop.BinaryOp)
    assert cls.getopnum.im_func(cls) == rop.rop.INT_ADD

    cls = rop.opclasses[rop.rop.CALL_i]
    assert issubclass(cls, rop.ResOpWithDescr)
    assert issubclass(cls, rop.N_aryOp)
    assert cls.getopnum.im_func(cls) == rop.rop.CALL_i

    cls = rop.opclasses[rop.rop.GUARD_TRUE]
    assert issubclass(cls, rop.GuardResOp)
    assert issubclass(cls, rop.UnaryOp)
    assert cls.getopnum.im_func(cls) == rop.rop.GUARD_TRUE

def test_mixins_in_common_base():
    INT_ADD = rop.opclasses[rop.rop.INT_ADD]
    assert len(INT_ADD.__bases__) == 1
    BinaryPlainResOp = INT_ADD.__bases__[0]
    assert BinaryPlainResOp.__name__ == 'BinaryPlainResOpInt'
    assert BinaryPlainResOp.__bases__ == (rop.BinaryOp, rop.ResOpInt,
                                          rop.PlainResOp)
    INT_SUB = rop.opclasses[rop.rop.INT_SUB]
    assert INT_SUB.__bases__[0] is BinaryPlainResOp

def test_instantiate():
    from pypy.rpython.lltypesystem import lltype, llmemory
    
    op = rop.create_resop_2(rop.rop.INT_ADD, 15, FakeBox('a'), FakeBox('b'))
    assert op.getarglist() == [FakeBox('a'), FakeBox('b')]
    assert op.getint() == 15

    mydescr = AbstractDescr()
    op = rop.create_resop(rop.rop.CALL_f, 15.5, [FakeBox('a'),
                                           FakeBox('b')], descr=mydescr)
    assert op.getarglist() == [FakeBox('a'), FakeBox('b')]
    assert op.getfloat() == 15.5
    assert op.getdescr() is mydescr

    op = rop.create_resop(rop.rop.CALL_p, lltype.nullptr(llmemory.GCREF.TO),
                          [FakeBox('a'), FakeBox('b')], descr=mydescr)
    assert op.getarglist() == [FakeBox('a'), FakeBox('b')]
    assert not op.getref_base()
    assert op.getdescr() is mydescr    

def test_can_malloc():
    from pypy.rpython.lltypesystem import lltype, llmemory

    mydescr = AbstractDescr()
    p = lltype.malloc(llmemory.GCREF.TO)
    assert rop.create_resop_0(rop.rop.NEW, p).can_malloc()
    call = rop.create_resop(rop.rop.CALL_i, 3, [FakeBox('a'),
                                                FakeBox('b')], descr=mydescr)
    assert call.can_malloc()
    assert not rop.create_resop_2(rop.rop.INT_ADD, 3, FakeBox('a'),
                                  FakeBox('b')).can_malloc()

def test_repr():
    mydescr = FakeDescr()
    op = rop.create_resop_0(rop.rop.GUARD_NO_EXCEPTION, None, descr=mydescr)
    assert repr(op) == 'guard_no_exception(, descr=descr)'
    op = rop.create_resop_2(rop.rop.INT_ADD, 3, FakeBox("a"), FakeBox("b"))
    assert repr(op) == '3 = int_add(a, b)'
    # XXX more tests once we decide what we actually want to print

class MockOpt(object):
    def __init__(self, replacements):
        self.d = replacements

    def get_value_replacement(self, v):
        if v in self.d:
            return FakeBox('rrr')
        return None

def test_copy_if_modified_by_optimization():
    mydescr = FakeDescr()
    op = rop.create_resop_0(rop.rop.GUARD_NO_EXCEPTION, None, descr=mydescr)
    assert op.copy_if_modified_by_optimization(MockOpt({})) is op
    op = rop.create_resop_1(rop.rop.INT_IS_ZERO, 1, FakeBox('a'))
    assert op.copy_if_modified_by_optimization(MockOpt({})) is op
    op2 = op.copy_if_modified_by_optimization(MockOpt(set([FakeBox('a')])))
    assert op2 is not op
    assert op2.getarg(0) == FakeBox('rrr')
    op = rop.create_resop_2(rop.rop.INT_ADD, 3, FakeBox("a"), FakeBox("b"))
    op2 = op.copy_if_modified_by_optimization(MockOpt(set([FakeBox('c')])))
    assert op2 is op
    op2 = op.copy_if_modified_by_optimization(MockOpt(set([FakeBox('b')])))
    assert op2 is not op
    assert op2._arg0 is op._arg0
    assert op2._arg1 != op._arg1
    assert op2.getint() == op.getint()
    op = rop.create_resop_3(rop.rop.STRSETITEM, None, FakeBox('a'),
                            FakeBox('b'), FakeBox('c'))
    op2 = op.copy_if_modified_by_optimization(MockOpt(set([FakeBox('b')])))
    assert op2 is not op
    op = rop.create_resop(rop.rop.CALL_i, 13, [FakeBox('a'), FakeBox('b'),
                            FakeBox('c')], descr=mydescr)
    op2 = op.copy_if_modified_by_optimization(MockOpt(set([FakeBox('aa')])))
    assert op2 is op
    op2 = op.copy_if_modified_by_optimization(MockOpt(set([FakeBox('b')])))
    assert op2 is not op
    assert op2.getarglist() == [FakeBox("a"), FakeBox("rrr"), FakeBox("c")]
    assert op2.getdescr() == mydescr

def test_copy_and_change():    
    op = rop.create_resop_1(rop.rop.INT_IS_ZERO, 1, FakeBox('a'))
    op2 = op.copy_and_change(rop.rop.INT_IS_TRUE)
    assert op2.opnum == rop.rop.INT_IS_TRUE
    assert op2.getarg(0) == FakeBox('a')
    op2 = op.copy_and_change(rop.rop.INT_IS_TRUE, FakeBox('b'))
    assert op2.opnum == rop.rop.INT_IS_TRUE
    assert op2.getarg(0) == FakeBox('b')
    assert op2 is not op
    op = rop.create_resop_2(rop.rop.INT_ADD, 3, FakeBox("a"), FakeBox("b"))
    op2 = op.copy_and_change(rop.rop.INT_SUB)
    assert op2.opnum == rop.rop.INT_SUB
    assert op2.getarglist() == [FakeBox("a"), FakeBox("b")]
    op2 = op.copy_and_change(rop.rop.INT_SUB, None, FakeBox("c"))
    assert op2.opnum == rop.rop.INT_SUB
    assert op2.getarglist() == [FakeBox("a"), FakeBox("c")]
    op = rop.create_resop_3(rop.rop.STRSETITEM, None, FakeBox('a'),
                            FakeBox('b'), FakeBox('c'))
    op2 = op.copy_and_change(rop.rop.UNICODESETITEM, None, FakeBox("c"))
    assert op2.opnum == rop.rop.UNICODESETITEM
    assert op2.getarglist() == [FakeBox("a"), FakeBox("c"), FakeBox("c")]    
    mydescr = FakeDescr()
    op = rop.create_resop(rop.rop.CALL_PURE_i, 13, [FakeBox('a'), FakeBox('b'),
                            FakeBox('c')], descr=mydescr)
    op2 = op.copy_and_change(rop.rop.CALL_i)
    assert op2.getarglist() == ['a', 'b', 'c']
    op2 = op.copy_and_change(rop.rop.CALL_i, [FakeBox('a')])
    assert op2.getarglist() == ['a']

def test_get_set_extra():
    op = rop.create_resop_2(rop.rop.INT_ADD, 3, FakeBox("a"), FakeBox("b"))
    op.set_extra("failargs", 2)
    assert op.get_extra("failargs") == 2

def test_hashes_eq():
    arg1 = rop.create_resop_1(rop.rop.FLOAT_NEG, 12.5, rop.BoxFloat(3.5))
    op = rop.create_resop_2(rop.rop.FLOAT_ADD, 13.5, rop.ConstFloat(3.0),
                            arg1)
    ope = rop.create_resop_2(rop.rop.FLOAT_ADD, 13.5, rop.ConstFloat(3.0),
                             arg1)
    op1 = rop.create_resop_2(rop.rop.FLOAT_ADD, 13.5, rop.ConstFloat(3.0),
                            rop.ConstFloat(1.0))
    op2 = rop.create_resop_2(rop.rop.FLOAT_ADD, 13.5, rop.ConstFloat(2.0),
                            arg1)
    op3 = rop.create_resop_2(rop.rop.FLOAT_ADD, 13.2, rop.ConstFloat(3.0),
                            arg1)
    assert op1._get_hash_() != op._get_hash_()
    assert op2._get_hash_() != op._get_hash_()
    assert op3._get_hash_() != op._get_hash_()
    assert not op1.eq(op)
    assert not op.eq(op1)
    assert not op2.eq(op)
    assert not op3.eq(op)
    assert ope._get_hash_() == op._get_hash_()
    assert ope.eq(op)

    op = rop.create_resop_0(rop.rop.FORCE_TOKEN, 13)
    op1 = rop.create_resop_0(rop.rop.FORCE_TOKEN, 15)
    assert op._get_hash_() != op1._get_hash_()
    assert not op.eq(op1)
    S = lltype.GcStruct('S')
    s = lltype.malloc(S)
    nonnull_ref = lltype.cast_opaque_ptr(llmemory.GCREF, s)
    nullref = lltype.nullptr(llmemory.GCREF.TO)
    op = rop.create_resop_1(rop.rop.NEWSTR, nullref, rop.BoxInt(5))
    op1 = rop.create_resop_1(rop.rop.NEWSTR, nonnull_ref, rop.BoxInt(5))
    assert op._get_hash_() != op1._get_hash_()
    assert not op.eq(op1)
    op = rop.create_resop_1(rop.rop.NEWSTR, nullref, rop.BoxInt(5))
    op1 = rop.create_resop_1(rop.rop.NEWSTR, nullref, rop.BoxInt(15))
    assert op._get_hash_() != op1._get_hash_()
    assert not op.eq(op1)

    descr = FakeDescr()
    descr2 = FakeDescr()
    op = rop.create_resop(rop.rop.CALL_i, 12, [rop.BoxInt(0), rop.BoxFloat(2.0),
                                               rop.BoxPtr(nullref)], descr)
    op1 = rop.create_resop(rop.rop.CALL_i, 12, [rop.BoxInt(0),
                                                rop.BoxFloat(2.0),
                                                rop.BoxPtr(nullref)], descr2)
    op2 = rop.create_resop(rop.rop.CALL_i, 12, [rop.BoxInt(0),
                                                rop.BoxFloat(2.5),
                                                rop.BoxPtr(nullref)], descr)
    op3 = rop.create_resop(rop.rop.CALL_i, 15, [rop.BoxInt(0),
                                                rop.BoxFloat(2.0),
                                                rop.BoxPtr(nullref)], descr)
    op4 = rop.create_resop(rop.rop.CALL_i, 12, [rop.BoxInt(0),
                                                rop.BoxFloat(2.0),
                                                rop.BoxPtr(nonnull_ref)], descr)
    assert op1._get_hash_() != op._get_hash_()
    assert op2._get_hash_() != op._get_hash_()
    assert op3._get_hash_() != op._get_hash_()
    assert op4._get_hash_() != op._get_hash_()
    assert not op.eq(op1)
    assert not op.eq(op2)
    assert not op.eq(op3)
    assert not op.eq(op4)

    # class StrangeDescr(AbstractDescr):
    #     def _get_hash_(self):
    #         return 13

    # descr = StrangeDescr()
    # op1 = rop.create_resop(rop.rop.CALL_i, 12, [rop.BoxInt(0),
    #                                             rop.BoxFloat(2.0),
    #                                            rop.BoxPtr(nullref)], descr)
    # op2 = rop.create_resop(rop.rop.CALL_i, 12, [rop.BoxInt(0),
    #                                             rop.BoxFloat(2.0),
    #                                            rop.BoxPtr(nullref)], descr)
    # assert op1._get_hash_() == op2._get_hash_()
    # assert not op1.eq(op2)
