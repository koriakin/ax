from envy.util import extr, extrs, bflmask
from envy.deco.expr.const import ExprConst
from envy.deco.expr.logop import ExprSext
from envy.deco.expr.cmp import ExprEq
from envy.deco import DecodeError
from envy.isa import Isa, IsaReg, IsaSplitReg, IsaMem, ISA_MEM_RO, IsaExec


class Vp2MacroIsa(Isa):
    def __init__(self):
        self.cacc = IsaReg('cacc', bflmask(32))
        self.cmd = IsaReg('cmd', 0x1fffc)
        self.lutidx = IsaReg('lutidx', bflmask(5))
        self.datahi = IsaReg('datahi', bflmask(8))
        self.dacc = IsaReg('dacc', bflmask(32))
        self.data = IsaReg('data', bflmask(32))
        self.csr = [self.cacc, self.cmd, self.lutidx, self.datahi]
        self.dsr = [self.dacc, self.data]
        self.r = [IsaReg('r{}'.format(idx), bflmask(32)) for idx in range(8)]
        self.g = [IsaReg('g{}'.format(idx), bflmask(32)) for idx in range(6)]
        self.p = [1] + [IsaReg('p{}'.format(idx), bflmask(1)) for idx in range(1, 4)]
        self.pred = IsaSplitReg('pred', [(idx, 1, self.p[idx]) for idx in range(4)])
        self.gpr = self.r + self.g + [None, self.pred]
        self.lut = IsaMem('lut', 32, bflmask(5), ISA_MEM_RO)
        self.submit = IsaExec('submit', (), (0x1fffc, bflmask(32), bflmask(8)))
        self.codemem = IsaMem('C', 64, 0x1ff, ISA_MEM_RO)

    def decode(self, name, block, pos):
        op = block.section.get(pos, 8)
        Vp2MacroOp(name, block, op)
        return pos + 8

isa = Vp2MacroIsa()


class Vp2MacroOp:
    def __init__(self, name, block, op):
        self.opcode = op
        self.name = name
        self.block = block

        self.pred = extr(op, 0, 2)
        self.pnot = extr(op, 2, 1)
        self.exit = extr(op, 3, 1)
        self.submit = extr(op, 4, 1)

        self.cbfstart = extr(op, 5, 5)
        self.cbfend = extr(op, 10, 5)
        self.cshift = extr(op, 15, 5)
        self.cshdir = extr(op, 20, 1)
        self.cimm6 = extr(op, 15, 6)
        self.csrc2 = extr(op, 21, 2)
        self.cimm8 = extr(op, 15, 8)
        self.cimm18 = extrs(op, 5, 18)
        self.csrc1 = extr(op, 23, 4)
        self.cdst = extr(op, 27, 2)
        self.cop = extr(op, 29, 2)

        self.pdst = extr(op, 31, 2)

        self.dbfstart = extr(op, 33, 5)
        self.dbfend = extr(op, 38, 5)
        self.dshift = extr(op, 43, 5)
        self.dshdir = extr(op, 48, 1)
        self.dimm6 = extr(op, 43, 6)
        self.dimm16 = extr(op, 33, 16)
        self.c2den = extr(op, 49, 1)
        self.ddstskip = extr(op, 49, 1)
        self.dsub = extr(op, 49, 1)
        self.dlogop = extr(op, 49, 2)
        self.dsrc2 = extr(op, 50, 2)
        self.dhi2 = extr(op, 50, 1)
        self.dhi = extr(op, 51, 1)
        self.dsrc1 = extr(op, 52, 4)
        self.dimm23 = extrs(op, 33, 23)
        self.drdst = extr(op, 56, 4)
        self.ddst = extr(op, 60, 1)
        self.dop = extr(op, 61, 3)

        self.luttmp = None

        self.decode()

    def get_gpr(self, idx):
        if isa.gpr[idx] is None:
            if self.luttmp is None:
                self.luttmp = self.block.emit_ld(self.name, isa.lut, 1, self.block.get_reg(isa.lutidx))
            return self.luttmp
        else:
            return self.block.get_reg(isa.gpr[idx])

    def get_csrc1(self):
        return self.get_gpr(self.csrc1)

    def get_csrc2(self):
        if self.csrc2 == 0:
            return ExprConst(0)
        elif self.csrc2 == 1:
            return self.block.get_reg(isa.cacc)
        elif self.csrc2 == 2:
            return self.block.get_reg(isa.dacc)
        elif self.csrc2 == 3:
            return self.get_csrc1()
        else:
            assert 0

    def get_dsrc1(self):
        return self.get_gpr(self.dsrc1)

    def get_dsrc2(self):
        if self.dsrc2 == 0:
            return ExprConst(0)
        elif self.dsrc2 == 1:
            return self.block.get_reg(isa.cacc)
        elif self.dsrc2 == 2:
            return self.block.get_reg(isa.dacc)
        elif self.dsrc2 == 3:
            return self.get_dsrc1()
        else:
            assert 0

    def decode(self):
        if self.pred or self.pnot:
            # XXX
            raise DecodeError('predicate')
        if self.submit:
            cmd = self.block.get_reg(isa.cmd)
            data = self.block.get_reg(isa.data)
            datahi = self.block.get_reg(isa.datahi)
            self.block.emit_exec(self.name, isa.submit, [cmd, data, datahi])
            # XXX auto-increment

        if self.cbfend >= self.cbfstart:
            cbfmask = (2 << self.cbfend) - (1 << self.cbfstart)
        else:
            cbfmask = 0

        pres = ExprConst(0)
        if self.cop == CINSRT_R:
            if self.cshdir == 0:
                ssrc = self.get_csrc1() << self.cshift
            else:
                ssrc = self.get_csrc1() >> self.cshift
            tmp = ssrc & cbfmask
            c2d = cres = tmp | (self.get_csrc2() & ~cbfmask)
            pres = ExprEq(tmp, 0)
        elif self.cop == CINSRT_I:
            c2d = cres = (self.get_csrc2() & ~cbfmask) | (self.cimm6 << self.cbfstart & cbfmask)
        elif self.cop == CMOV_I:
            c2d = cres = ExprConst(self.cimm18)
        elif self.cop == CEXTRADD8:
            c2d = (self.get_csrc1() & cbfmask) >> self.cbfstart
            cres = ((c2d + self.cimm8) & 0xff) | (c2d & ~0xff)
        else:
            assert 0

        if self.dbfend >= self.dbfstart:
            dbfmask = (2 << self.dbfend) - (1 << self.dbfstart)
        else:
            dbfmask = 0

        ddst_skip = False
        if self.dop == DINSRT_R:
            if self.dshdir == 0:
                ssrc = self.get_dsrc1() << self.dshift
            else:
                ssrc = ExprSext(self.get_dsrc1(), 31) >> self.dshift
            tmp = ssrc & dbfmask
            dres = tmp | (self.get_dsrc2() & ~dbfmask)
            if self.c2den:
                dres = (c2d & cbfmask) | (dres & ~cbfmask)
            pres = ExprEq(tmp, 0)
        elif self.dop == DINSRT_I:
            dres = (self.get_dsrc2() & ~dbfmask) | (self.dimm6 << self.dbfstart & dbfmask)
            if self.c2den:
                dres = (c2d & cbfmask) | (dres & ~cbfmask)
        elif self.dop == DMOV_I:
            dres = ExprConst(self.dimm23)
        elif self.dop == DADD16_I:
            src1 = (self.get_dsrc1() >> (self.dhi * 16)) & 0xffff
            sum_ = (src1 + self.dimm16) & 0xffff
            dres = (self.get_dsrc1() & ~(0xffff << 16 * self.dhi)) | (sum_ << (16 * self.dhi))
            pres = sum_ >> 15 & 1
            ddst_skip = self.ddstskip
        elif self.dop == DLOGOP16_I:
            src = self.get_dsrc1()
            if self.dhi:
                src = src >> 16
            src = src & 0xffff
            if self.dlogop == 0:
                res = ExprConst(self.dimm16)
            elif self.dlogop == 1:
                res = src & self.dimm16
            elif self.dlogop == 2:
                res = src | self.dimm16
            elif self.dlogop == 3:
                res = src ^ self.dimm16
            if self.dhi:
                dres = (self.get_dsrc1() & ~0xffff0000) | (res << 16)
            else:
                dres = (self.get_dsrc1() & ~0xffff) | res
            pres = ExprEq(res, 0)
        elif self.dop == DSHIFT_R:
            shift = self.get_csrc1() & 0x1f
            if self.dshdir == 0:
                dres = self.get_dsrc1() << shift
            else:
                dres = ExprSext(self.get_dsrc1(), 31) >> shift
        elif self.dop == DSEXT:
            bfstart = max(self.dbfstart, self.dshift)
            if self.dbfend >= bfstart:
                dbfmask = (2 << self.dbfend) - (1 << bfstart)
            else:
                dbfmask = 0
            pres = self.get_dsrc2() >> self.dshift & 1
            dres = (self.get_dsrc2() & ~dbfmask) | (ExprSext(self.get_dsrc2(), self.dshift) & dbfmask)
        elif self.dop == DADD16_R:
            src1 = (self.get_dsrc1() >> (self.dhi * 16)) & 0xffff
            src2 = (self.get_csrc1() >> (self.dhi2 * 16)) & 0xffff
            if self.dsub == 0:
                sum_ = (src1 + src2) & 0xffff
            else:
                sum_ = (src2 - src2) & 0xffff
            dres = (self.get_dsrc1() & ~(0xffff << 16 * self.dhi)) | (sum_ << (16 * self.dhi))
            pres = sum_ >> 15 & 1
        else:
            assert 0

        self.block.set_reg(isa.csr[self.cdst], cres, self.name + '_cres')
        dres = self.block.encap(self.block.make_temp(dres, self.name + '_dres', bflmask(32)))
        if not ddst_skip:
            self.block.set_reg(isa.dsr[self.ddst], dres, self.name + '_dres_dsr')
        if self.drdst != 14:
            self.block.set_reg(isa.gpr[self.drdst], dres, self.name + '_dres_gpr')
        if self.pdst:
            self.block.set_reg(isa.p[self.pdst], pres, self.name + '_pres')

        if self.exit:
            self.block.emit_exit()

CINSRT_R = 0
CINSRT_I = 1
CMOV_I = 2
CEXTRADD8 = 3

DINSRT_R = 0
DINSRT_I = 1
DMOV_I = 2
DADD16_I = 3
DLOGOP16_I = 4
DSHIFT_R = 5
DSEXT = 6
DADD16_R = 7
