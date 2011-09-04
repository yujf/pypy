from pypy.translator.tool.cbuild import ExternalCompilationInfo
from pypy.rpython.tool import rffi_platform

# On platforms with enough hardware registers and with gcc, we can
# (ab)use gcc to globally assign a register to a single global void*
# variable.  We use it with a double meaning:
#
# - when it is NULL upon return from a function, it means that an
#   exception occurred.  It allows the caller to quickly check for
#   exceptions.
#
# - in other cases, with --gcrootfinder=shadowstack, it points to
#   the top of the shadow stack.


# For now, only for x86-64.  Tries to use the register r15.
eci = ExternalCompilationInfo(
    post_include_bits=["""
register long pypy_r15 asm("r15");
#define PYPY_GET_SPECIAL_REG_NOMARK() ((void *)pypy_r15)
#define PYPY_SET_SPECIAL_REG_NOMARK(x) (pypy_r15 = (long)(x))
#define PYPY_GET_SPECIAL_REG_MARK() ((void *)(pypy_r15 & ~1))
#define PYPY_INCR_SPECIAL_REG_MARK(d) (pypy_r15 += (d))
#define PYPY_SPECIAL_REG_GETEXC() (pypy_r15 & 1)
#define PYPY_SPECIAL_REG_SETEXC(x) (pypy_r15 = (x) ? pypy_r15|1 : pypy_r15&~1)
"""],
    )

_test_eci = eci.merge(ExternalCompilationInfo(
    post_include_bits=["""
            void f(void) {
                pypy_r15 = 12345;
            }
    """]))

try:
    rffi_platform.verify_eci(_test_eci)
    register_number = 15      # r15
except rffi_platform.CompilationError:
    eci = None
    register_number = None
else:

    from pypy.rpython.lltypesystem import lltype, llmemory, rffi

    # use addr=load_from_reg() and store_into_reg(addr) to load and store
    # an Address out of the special register.  When running on top of Python,
    # the behavior is emulated.

    _value_reg = None
    _exc_marker = False

    def _pypy_get_special_reg_nomark():
        # this must not be called if _exc_marker is set
        assert _value_reg is not None
        assert not _exc_marker
        return _value_reg

    def _pypy_set_special_reg_nomark(addr):
        # this must not be called if _exc_marker is set
        global _value_reg
        assert not _exc_marker
        _value_reg = addr

    def _pypy_get_special_reg_mark():
        # this can be called if _exc_marker is set
        assert _value_reg is not None
        return _value_reg

    def _pypy_incr_special_reg_mark(delta):
        # this can be called if _exc_marker is set
        global _value_reg
        assert _value_reg is not None
        _value_reg += delta

    def _pypy_special_reg_getexc():
        return _exc_marker

    def _pypy_special_reg_setexc(flag):
        global _value_reg
        _exc_marker = flag

    load_from_reg_nomark = rffi.llexternal('PYPY_GET_SPECIAL_REG_NOMARK', [],
                                           llmemory.Address,
                                        _callable=_pypy_get_special_reg_nomark,
                                           compilation_info=eci,
                                           _nowrapper=True)

    store_into_reg_nomark = rffi.llexternal('PYPY_SET_SPECIAL_REG_NOMARK',
                                            [llmemory.Address],
                                            lltype.Void,
                                        _callable=_pypy_set_special_reg_nomark,
                                            compilation_info=eci,
                                            _nowrapper=True)

    load_from_reg_mark = rffi.llexternal('PYPY_GET_SPECIAL_REG_MARK', [],
                                         llmemory.Address,
                                         _callable=_pypy_get_special_reg_mark,
                                         compilation_info=eci,
                                         _nowrapper=True)

    incr_reg_mark = rffi.llexternal('PYPY_INCR_SPECIAL_REG_MARK',
                                    [lltype.Signed],
                                    lltype.Void,
                                    _callable=_pypy_incr_special_reg_mark,
                                    compilation_info=eci,
                                    _nowrapper=True)

    get_exception = rffi.llexternal('PYPY_SPECIAL_REG_GETEXC', [],
                                    lltype.Bool,
                                    _callable=_pypy_special_reg_getexc,
                                    compilation_info=eci,
                                    _nowrapper=True)

    set_exception = rffi.llexternal('PYPY_SPECIAL_REG_SETEXC', [lltype.Bool],
                                    lltype.Void,
                                    _callable=_pypy_special_reg_setexc,
                                    compilation_info=eci,
                                    _nowrapper=True)
