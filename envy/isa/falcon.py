from envy.util import bflmask, sext
from envy.isa import Isa, IsaReg, IsaVisibleReg, IsaSplitReg, IsaSubReg, IsaMem, ISA_MEM_RO, ISA_MEM_RW, ISA_MEM_IO, IsaExec
from envy.deco.expr.const import ExprConst
from envy.deco.expr.logop import ExprSext
from envy.deco.expr.cmp import ExprEq, ExprLt
from envy.deco import DecodeError


class FalconIsa(Isa):
    def __init__(self, version):
        self.r = [IsaReg('r{}'.format(idx), bflmask(32)) for idx in range(16)]
        self.rh = [IsaSubReg(self.r[idx], 0, 16) for idx in range(16)]
        self.rb = [IsaSubReg(self.r[idx], 0, 8) for idx in range(16)]
        self.rs = [self.rb, self.rh, self.r]
        self.sp = IsaReg('sp', bflmask(32) & ~3)
        self.iv0 = IsaVisibleReg('iv0', bflmask(32))
        self.iv1 = IsaVisibleReg('iv1', bflmask(32))
        self.tv = IsaVisibleReg('tv', bflmask(32))
        flags = []
        self.cf = IsaReg('cf', 1)
        self.of = IsaReg('of', 1)
        self.sf = IsaReg('sf', 1)
        self.zf = IsaReg('zf', 1)
        for idx in range(8):
            flags.append((idx, 1, IsaReg('p{}'.format(idx), 1)))
        flags.append((8, 1, self.cf))
        flags.append((9, 1, self.of))
        flags.append((10, 1, self.sf))
        flags.append((11, 1, self.zf))
        flags.append((16, 1, IsaVisibleReg('ie0', 1)))
        flags.append((17, 1, IsaVisibleReg('ie1', 1)))
        flags.append((20, 1, IsaReg('is0', 1)))
        flags.append((21, 1, IsaReg('is1', 1)))
        flags.append((24, 1, IsaVisibleReg('ta', 1)))
        self.flags = IsaSplitReg('flags', flags)
        self.xtargets = IsaReg('xtargets', 0x7707)
        self.xdbase = IsaReg('xdbase', bflmask(32))
        self.xcbase = IsaReg('xdbase', bflmask(32))
        self.version = version
        self.sr = [
            self.iv0, self.iv1, None, self.tv,
            self.sp, None, self.xcbase, self.xdbase,  # XXX PC
            self.flags, None, None, self.xtargets,  # XXX crypto crap
            None, None, None, None,  # XXX tstatus
        ]
        self.data = IsaMem('D', 8, bflmask(32), ISA_MEM_RW)
        self.iowr = IsaExec('iowr', [], [bflmask(32), bflmask(32)])
        self.iowrs = IsaExec('iowrs', [], [bflmask(32), bflmask(32)])
        self.iord = IsaExec('iord', [bflmask(32)], [bflmask(32)])
        self.sleep = IsaExec('sleep', [], [1])
        self.xcwait = IsaExec('xcwait', [], [])
        self.xdwait = IsaExec('xdwait', [], [])
        self.xcld = IsaExec('xcld', [], [bflmask(3), bflmask(32), bflmask(32), bflmask(16), bflmask(3)])
        self.xdld = IsaExec('xdld', [], [bflmask(3), bflmask(32), bflmask(32), bflmask(16), bflmask(3)])
        self.xdst = IsaExec('xdst', [], [bflmask(3), bflmask(32), bflmask(32), bflmask(16), bflmask(3)])
        if version < 4:
            self.codemem = IsaMem('C', 8, bflmask(16), ISA_MEM_RO)
        else:
            self.codemem = IsaMem('C', 8, bflmask(24), ISA_MEM_RO)
        self.stackptr = self.sp
        self.stackmem = self.data

    def decode(self, name, block, pos):
        return FalconOp(self, name, block, pos).pos


class FalconOp:
    def __init__(self, isa, name, block, pos):
        self.isa = isa
        self.name = name
        self.block = block
        self.pos = pos
        self.origpos = pos
        op = op0 = self.get_byte()
        if op < 0xc0:
            size = op >> 6
            op = op & 0x3f
            if op < 0x30:
                subop = op & 0xf
                op >>= 4
                if op == 0 and self.isa.version < 5:
                    op1 = self.get_byte()
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.r[op1 >> 4]
                    imm = self.get_imm(0, 0)
                    if subop == 0:
                        block.emit_st(self.name, self.isa.data, 1 << size, block.get_reg(reg2) + (imm << size), block.get_reg(reg1))
                    else:
                        raise DecodeError('sized low {:x}/{:x}'.format(op, subop))
                elif op == 0 and self.isa.version >= 5:
                    reg0 = isa.r[subop]
                    imm = self.get_fimm(size + 1)
                    block.set_reg(reg0, ExprConst(imm), self.name)
                elif op == 1 or (op == 2 and self.isa.version < 5):
                    op1 = self.get_byte()
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.rs[size][op1 >> 4]
                    imm = self.get_imm(op == 2, 0)
                    if subop in [0, 1, 2, 3]:
                        self.emit_add(size, reg1, block.get_reg(reg2), ExprConst(imm), subop)
                    elif subop in [4, 5, 7, 0xc, 0xd] and op == 1:
                        self.emit_shift(size, reg1, block.get_reg(reg2), ExprConst(imm), subop)
                    elif subop == 8 and op == 1:
                        reg2 = self.isa.r[op1 >> 4]
                        res = block.emit_ld(self.name, self.isa.data, 1 << size, block.get_reg(reg2) + (imm << size))
                        block.set_reg(reg1, res, self.name)
                    else:
                        raise DecodeError('sized low {:x}/{:x}'.format(op, subop))
                elif op == 2 and self.isa.version >= 5:
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.rs[size][op1 >> 4]
                    # XXX st, st[sp], cmpu, cmps, cmp
                    raise DecodeError('sized low {:x}/{:x}'.format(op, subop))
                else:
                    raise DecodeError('sized low {:x}/{:x}'.format(op, subop))
            else:
                if op in [0x30, 0x31]:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    reg2 = self.isa.rs[size][op1 >> 4]
                    imm = self.get_imm(op & 1, 0)
                    if subop == 1:
                        block.emit_st(self.name, self.isa.data, 1 << size, block.get_reg(self.isa.sp) + (imm << size), block.get_reg(reg2))
                    elif subop == 6 and self.isa.version >= 3:
                        self.emit_add(size, None, block.get_reg(reg2), ExprConst(imm), 2)
                    else:
                        # XXX st, cmpu, cmps
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op == 0x34:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    reg2 = self.isa.rs[size][op1 >> 4]
                    imm = self.get_imm(0, 0)
                    if subop == 0:
                        res = block.emit_ld(self.name, self.isa.data, 1 << size, block.get_reg(self.isa.sp) + (imm << size))
                        block.set_reg(reg2, res, self.name)
                    else:
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op in [0x36, 0x37]:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    reg2 = self.isa.rs[size][op1 >> 4]
                    imm = self.get_imm(op & 1, 0)
                    if subop in [0, 1, 2, 3]:
                        self.emit_add(size, reg2, self.block.get_reg(reg2), ExprConst(imm), subop)
                    elif subop in [4, 5, 7, 0xc, 0xd] and op == 0x36:
                        self.emit_shift(size, reg2, self.block.get_reg(reg2), ExprConst(imm), subop)
                    else:
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op == 0x38 and self.isa.version < 5:
                    op1 = self.get_byte()
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.rs[size][op1 >> 4]
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    if subop == 6 and self.isa.version >= 3:
                        self.emit_add(size, None, block.get_reg(reg2), block.get_reg(reg1), 2)
                    else:
                        # XXX st, st[sp], cmpu, cmps
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op == 0x39:
                    op1 = self.get_byte()
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.rs[size][op1 >> 4]
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    if subop == 0:
                        self.emit_not(size, reg1, block.get_reg(reg2))
                    else:
                        # XXX neg, mov/movf, hwswap
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op == 0x3b:
                    op1 = self.get_byte()
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.rs[size][op1 >> 4]
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    if subop in [0, 1, 2, 3]:
                        self.emit_add(size, reg2, block.get_reg(reg2), block.get_reg(reg1), subop)
                    elif subop in [4, 5, 7, 0xc, 0xd]:
                        self.emit_shift(size, reg2, block.get_reg(reg2), block.get_reg(reg1), subop)
                    else:
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op == 0x3c:
                    op1 = self.get_byte()
                    reg1 = self.isa.rs[size][op1 & 0xf]
                    reg2 = self.isa.rs[size][op1 >> 4]
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    reg3 = self.isa.rs[size][op2 >> 4]
                    if subop in [0, 1, 2, 3]:
                        self.emit_add(size, reg3, block.get_reg(reg2), block.get_reg(reg1), subop)
                    elif subop in [4, 5, 7, 0xc, 0xd]:
                        self.emit_shift(size, reg3, block.get_reg(reg2), block.get_reg(reg1), subop)
                    else:
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                elif op == 0x3d:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    reg2 = self.isa.rs[size][op1 >> 4]
                    if subop == 4:
                        block.set_reg(reg2, ExprConst(0), self.name)
                    else:
                        # XXX not, neg, mov/movf, hswap, setf
                        raise DecodeError('sized high {:x}/{:x}'.format(op, subop))
                else:
                    # XXX 32, 33, 35, 38[v5], 3a, 3e, 3f
                    raise DecodeError('sized high {:x}'.format(op))
        else:
            if op < 0xf0:
                subop = op & 0xf
                op >>= 4
                if op in [0xc, 0xe]:
                    op1 = self.get_byte()
                    reg1 = self.isa.r[op1 & 0xf]
                    reg2 = self.isa.r[op1 >> 4]
                    imm = self.get_imm(op == 0xe, subop == 1)
                    if subop in [3, 7] and self.isa.version >= 3:
                        self.emit_extr(reg1, block.get_reg(reg2), imm, subop)
                    elif subop in [4, 5, 6]:
                        self.emit_logop(reg1, block.get_reg(reg2), imm, subop)
                    elif subop == 0xf:
                        self.emit_iord(reg1, block.get_reg(reg2) + imm * 4)
                    else:
                        # XXX other
                        raise DecodeError('unsized low {:x}/{:x}'.format(op, subop))
                elif op == 0xd and self.isa.version < 5:
                    op1 = self.get_byte()
                    reg1 = self.isa.r[op1 & 0xf]
                    reg2 = self.isa.r[op1 >> 4]
                    imm = self.get_imm(0, 0)
                    block.emit_exec(self.name, self.isa.iowr, [block.get_reg(reg2) + imm * 4, block.get_reg(reg1)])
                else:
                    # XXX 0xd[old], 0xd[v5]
                    raise DecodeError('unsized low {:x}/{:x}'.format(op, subop))
            else:
                if op in [0xf0, 0xf1]:
                    op1 = self.get_byte()
                    reg2 = self.isa.r[op1 >> 4]
                    subop = op1 & 0xf
                    imm = self.get_imm(op & 1, subop in [1, 7])
                    if subop == 0:
                        block.set_reg(reg2, isa.mulu(block.get_reg(reg2), imm), self.name)
                    elif subop == 1:
                        block.set_reg(reg2, isa.muls(block.get_reg(reg2), imm), self.name)
                    #elif subop == 2 and op == 0xf0:
                    #    block.set_reg(reg2, ExprSext(block.get_reg(reg2), imm & 0x1f), self.name)
                    elif subop == 3:
                        block.set_reg(reg2, block.get_reg(reg2) & 0xffff | imm << 16, self.name)
                    elif subop in [4, 5, 6]:
                        self.emit_logop(reg2, block.get_reg(reg2), imm, subop)
                    elif subop == 7:
                        block.set_reg(reg2, ExprConst(imm), self.name)
                    elif subop == 0xc and op == 0xf0:
                        self.emit_xbit(reg2, block.get_reg(self.isa.flags), imm)
                    else:
                        # XXX 2, 9-11
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op in [0xf4, 0xf5]:
                    op1 = self.get_byte()
                    subop = op1 & 0x3f
                    imm = self.get_imm(op & 1, subop < 0x20 or subop == 0x30)
                    if subop < 0x20:
                        target = ExprConst(imm + self.origpos)
                        if subop == 0xe:
                            block.emit_jmp(self.name, target)
                        else:
                            if subop in range(0x00, 0x0c):
                                pred = block.get_reg(self.isa.flags.fields[subop][2])
                            elif subop in range(0x0c, 0x0e):
                                pred = block.get_reg(self.isa.cf) | block.get_reg(self.isa.zf)
                                if subop == 0xc:
                                    pred = pred ^ 1
                            elif subop in range(0x10, 0x1c):
                                pred = block.get_reg(self.isa.flags.fields[subop - 0x10][2]) ^ 1
                            elif subop in range(0x1c, 0x20):
                                pred = block.get_reg(self.isa.sf) ^ block.get_reg(self.isa.of)
                                if subop in [0x1c, 0x1d]:
                                    pred |= block.get_reg(self.isa.zf)
                                if subop in [0x1c, 0x1f]:
                                    pred ^= 1
                            else:
                                raise DecodeError('bra pred {}'.format(subop))
                            block.emit_bra(self.name, pred, target)
                    elif subop == 0x20:
                        block.emit_jmp(self.name, ExprConst(imm))
                    elif subop == 0x21:
                        block.emit_call(self.name, ExprConst(imm))
                    elif subop == 0x28 and op == 0xf4:
                        block.emit_exec(self.name, self.isa.sleep, [block.get_reg(self.isa.flags) >> (imm & 0x1f)])
                    elif subop == 0x30:
                        block.set_reg(isa.sp, block.get_reg(isa.sp) + imm, self.name)
                    elif subop == 0x31 and op == 0xf4:
                        block.set_reg(isa.flags, block.get_reg(isa.flags) | 1 << imm, self.name)
                    elif subop == 0x32 and op == 0xf4:
                        block.set_reg(isa.flags, block.get_reg(isa.flags) & ~(1 << imm), self.name)
                    elif subop == 0x33 and op == 0xf4:
                        block.set_reg(isa.flags, block.get_reg(isa.flags) ^ 1 << imm, self.name)
                    else:
                        # XXX 3c
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xf8:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    if subop == 0:
                        block.emit_ret()
                    elif subop == 1:
                        block.emit_iret()
                    elif subop == 2:
                        block.emit_exit()
                    elif subop == 3:
                        block.emit_exec(self.name, self.isa.xdwait, [])
                    elif subop == 7:
                        block.emit_exec(self.name, self.isa.xcwait, [])
                    else:
                        # XXX iret, f8/6, trap
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xf9:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    reg2 = isa.r[op1 >> 4]
                    if subop == 0:
                        block.set_reg(isa.sp, block.get_reg(isa.sp) - 4, self.name)
                        block.emit_st(self.name, self.isa.data, 4, block.get_reg(isa.sp), block.get_reg(reg2))
                    elif subop == 5:
                        block.emit_call(self.name, block.get_reg(reg2))
                    else:
                        # XXX add[sp], mpush, bra, itlb, bset, bclr, btgl
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xfa:
                    op1 = self.get_byte()
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    reg1 = isa.r[op1 & 0xf]
                    reg2 = isa.r[op1 >> 4]
                    if subop == 0:
                        block.emit_exec(self.name, self.isa.iowr, [block.get_reg(reg2), block.get_reg(reg1)])
                    elif subop == 1:
                        block.emit_exec(self.name, self.isa.iowrs, [block.get_reg(reg2), block.get_reg(reg1)])
                    elif subop in [4, 5, 6]:
                        if subop == 4:
                            pshift = 0
                            spec = self.isa.xcld
                            base = self.isa.xcbase
                        elif subop == 5:
                            pshift = 8
                            spec = self.isa.xdld
                            base = self.isa.xdbase
                        elif subop == 6:
                            pshift = 12
                            spec = self.isa.xdst
                            base = self.isa.xdbase
                        port = block.get_reg(self.isa.xtargets) >> pshift
                        base = block.get_reg(base)
                        offs = block.get_reg(reg2)
                        p2 = block.get_reg(reg1)
                        addr = p2 & 0xffff
                        size = p2 >> 16
                        block.emit_exec(self.name, spec, [port, base, offs, addr, size])
                    else:
                        # XXX xcld, xdld. xdst, setp
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xfc:
                    op1 = self.get_byte()
                    subop = op1 & 0xf
                    reg2 = isa.r[op1 >> 4]
                    if subop == 0:
                        tmp = block.emit_ld(self.name, self.isa.data, 4, block.get_reg(isa.sp))
                        block.set_reg(isa.sp, block.get_reg(isa.sp) + 4, self.name + '_sp')
                        block.set_reg(reg2, tmp, self.name)
                    else:
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xfd:
                    op1 = self.get_byte()
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    reg1 = isa.r[op1 & 0xf]
                    reg2 = isa.r[op1 >> 4]
                    if subop in [0, 1]:
                        self.emit_mul(reg2, block.get_reg(reg2), block.get_reg(reg1), subop)
                    elif subop in [4, 5, 6]:
                        self.emit_logop(reg2, block.get_reg(reg2), block.get_reg(reg1), subop)
                    else:
                        # XXX sext, bit*
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xfe:
                    op1 = self.get_byte()
                    op2 = self.get_byte()
                    reg1 = self.isa.r[op1 & 0xf]
                    reg2 = self.isa.r[op1 >> 4]
                    subop = op2 & 0xf
                    if subop == 0:
                        sr = isa.sr[op1 & 0xf]
                        if sr is None:
                            raise DecodeError('mov to $sr{}'.format(op1 & 0xf))
                        block.set_reg(sr, block.get_reg(reg2), self.name)
                    elif subop == 1:
                        sr = isa.sr[op1 >> 4]
                        if sr is None:
                            raise DecodeError('mov from $sr{}'.format(op1 >> 4))
                        block.set_reg(reg1, block.get_reg(sr), self.name)
                    else:
                        # XXX ptlb, vtlb, xbit
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                elif op == 0xff:
                    op1 = self.get_byte()
                    reg1 = self.isa.r[op1 & 0xf]
                    reg2 = self.isa.r[op1 >> 4]
                    op2 = self.get_byte()
                    subop = op2 & 0xf
                    reg3 = self.isa.r[op2 >> 4]
                    if subop in [0, 1]:
                        self.emit_mul(reg3, block.get_reg(reg2), block.get_reg(reg1), subop)
                    elif subop in [4, 5, 6]:
                        self.emit_logop(reg3, block.get_reg(reg2), block.get_reg(reg1), subop)
                    elif subop == 0xf:
                        self.emit_iord(reg3, block.get_reg(reg2) + block.get_reg(reg1) * 4)
                    else:
                        # XXX sext, extr*, xbit, div/mod, 0xe
                        raise DecodeError('unsized high {:x}/{:x}'.format(op, subop))
                else:
                    # XXX f2, f6, f7, fb
                    raise DecodeError('unsized high {:x}'.format(op))

    def get_byte(self):
        res = self.block.section.get(self.pos, 1)
        self.pos += 1
        return res

    def get_imm(self, sz, sign):
        if sz == 0:
            res = self.block.section.get(self.pos, 1)
            self.pos += 1
            if sign:
                res = sext(res, 7)
        else:
            res = self.block.section.get(self.pos, 2)
            self.pos += 2
            if sign:
                res = sext(res, 15)
        return res

    def get_fimm(self, bnum):
        res = self.block.section.get(self, pos, bnum)
        self.pos += bnum
        return res

    def emit_add(self, size, dst, src1, src2, subop):
        size = 8 << size
        s2 = src2
        if subop in [1, 3]:
            s2 += self.isa.cf
        if subop in [2, 3]:
            s2 = -src2
        res = src1 + s2
        if dst is not None:
            self.block.set_reg(dst, res, self.name)
        self.block.set_reg(self.isa.cf, res >> size, self.name + '_cf')
        sign = self.block.encap(self.block.make_temp(res >> (size - 1), self.name + '_sign', 1))
        self.block.set_reg(self.isa.of, sign ^ ExprLt(ExprSext(src1, size - 1), ExprSext(-s2, size - 1)), self.name + '_of')
        self.block.set_reg(self.isa.sf, sign, self.name + '_sf')
        if subop == 2:
            self.block.set_reg(self.isa.zf, ExprEq(src1, src2), self.name + '_zf')
        else:
            self.block.set_reg(self.isa.zf, ExprEq(res & bflmask(size), 0), self.name + '_zf')

    def emit_shift(self, size, dst, src1, src2, subop):
        shcnt = src2 & bflmask(size + 3)
        size = 8 << size
        if subop in [4, 0xc]:
            res = src1 << shcnt
            if subop == 0xc:
                res |= self.block.get_reg(self.isa.cf) << (shcnt - 1)
            cf = res >> size
        else:
            cf = src1 >> (shcnt - 1)
            if subop == 7:
                src1 = ExprSext(src1, size - 1)
            elif subop == 0xd:
                src1 |= self.block.get_reg(self.isa.cf) << size
            res = src1 >> shcnt
        self.block.set_reg(dst, res, self.name)
        self.block.set_reg(self.isa.cf, cf, self.name + '_cf')
        if self.isa.version != 0:
            self.block.set_reg(self.isa.of, ExprConst(0), self.name + '_of')
            self.block.set_reg(self.isa.sf, res >> (size - 1), self.name + '_sf')
            self.block.set_reg(self.isa.zf, ExprEq(res, 0), self.name + '_zf')

    def emit_logop(self, dst, src1, src2, subop):
        if subop == 4:
            res = src1 & src2
        elif subop == 5:
            res = src1 | src2
        elif subop == 6:
            res = src1 ^ src2
        self.block.set_reg(dst, res, self.name)
        if self.isa.version != 0:
            self.block.set_reg(self.isa.cf, ExprConst(0), self.name + '_cf')
            self.block.set_reg(self.isa.of, ExprConst(0), self.name + '_of')
            self.block.set_reg(self.isa.sf, res >> 31, self.name + '_sf')
            self.block.set_reg(self.isa.zf, ExprEq(res, 0), self.name + '_zf')

    def emit_extr(self, dst, src1, src2, subop):
        low = src2 & 0x1f
        size = (src2 >> 5 & 0x1f) + 1
        res = src1 >> low & ((ExprConst(1) << size) - 1)
        if subop == 3:
            # XXX doesn't match hw if low+size > 0x20
            res = ExprSext(res, size - 1)
        self.block.set_reg(dst, res, self.name)
        self.block.set_reg(self.isa.sf, res >> 31, self.name + '_sf')
        self.block.set_reg(self.isa.zf, ExprEq(res, 0), self.name + '_zf')

    def emit_xbit(self, dst, src1, src2):
        if self.isa.version == 0:
            res = self.block.get_reg(dst) & ~1 | src1 >> src2 & 1
            self.block.set_reg(dst, res, self.name)
        else:
            res = src1 >> src2 & 1
            self.block.set_reg(dst, res, self.name)
            self.block.set_reg(self.isa.sf, res >> 31, self.name + '_sf')
            self.block.set_reg(self.isa.zf, ExprEq(res, 0), self.name + '_zf')

    def emit_iord(self, dst, addr):
        res, = self.block.emit_exec(self.name, self.isa.iord, [addr])
        self.block.set_reg(dst, res, self.name)

    def emit_not(self, size, dst, src):
        size = 8 << size
        res = src ^ bflmask(size)
        self.block.set_reg(dst, res, self.name)
        self.block.set_reg(self.isa.of, ExprConst(0), self.name + '_of')
        self.block.set_reg(self.isa.sf, res >> (size - 1), self.name + '_sf')
        self.block.set_reg(self.isa.zf, ExprEq(res, 0), self.name + '_zf')

    def emit_mul(self, dst, src1, src2, subop):
        if subop == 0:
            s1 = src1 & 0xffff
            s2 = src2 & 0xffff
        else:
            s1 = ExprSext(src1, 15)
            s2 = ExprSext(src2, 15)
        self.block.set_reg(dst, s1 * s2, self.name)
