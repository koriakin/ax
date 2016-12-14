from collections import Counter
from envy.util import bflmask
from envy.isa import IsaSubReg

FOLD_BIGOR = 'bigor'
FOLD_SUM = 'sum'
FOLD_TOP = 'top'
FOLD_OTHER = 'other'
FOLD_ALL = 'all'


class Var:
    def __init__(self, name, mask):
        self.name = name
        self.mask = mask

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    def __format__(self, conv):
        return self.name


class TempVar(Var):
    pass


class InVar(Var):
    pass


class ParmVar(Var):
    def __init__(self, name, reg):
        super().__init__(name, reg.mask)
        self.reg = reg

    def __lt__(self, other):
        return self.reg.name < other.reg.name


class Block:
    def __init__(self, name, isa, section, start, limit):
        self.name = name
        self.isa = isa
        self.section = section
        self.start = start
        self.inregs = {}
        self.ops = []
        self.regs = {}
        self.finalop = None
        self.outregs = None
        self.outs = None
        self.vars = {}
        self.locals = set()
        pos = self.start
        while self.finalop is None and pos != limit:
            if limit is not None and pos > limit:
                raise DecodeError("Block limit in the middle of instruction")
            pos = self.isa.decode('{}_{:x}'.format(self.name, pos - self.start), self, pos)
        self.end = pos
        if self.finalop is None:
            self.outregs = [self.regs]
            self.outs = [limit]
        self.outs = [out if out != ... else self.end for out in self.outs]
        self.clean()

    def clean(self):
        livevars = Counter()
        for regs in self.outregs:
            for reg in regs:
                if isinstance(regs[reg], Var):
                    livevars[regs[reg]] += 2
        if self.finalop is not None:
            self.finalop.findvars(livevars)
        newops = []
        for op in reversed(list(self.ops)):
            if isinstance(op, DecopAssign) and op.dst not in livevars:
                continue
            if isinstance(op, DecopLd) and op.dst not in livevars and op.space.mode != ISA_MEM_IO:
                continue
            if isinstance(op, DecopExec):
                newouts = [out if out in livevars else None for out in op.outs]
                op = DecopExec(op.spec, newouts, op.ins)
            op.findvars(livevars)
            newops.append(op)
        self.ops = reversed(newops)
        newinregs = {}
        for reg in self.inregs:
            if self.inregs[reg] in livevars:
                newinregs[reg] = self.inregs[reg]
        self.inregs = newinregs
        singlevars = {var for var in livevars if livevars[var] == 1}
        subst = {}
        newops = []
        for op in self.ops:
            op = op.fold(subst, FOLD_ALL)
            #if isinstance(op, DecopAssign) and op.dst in singlevars:
            if isinstance(op, DecopAssign):
                subst[op.dst] = op.src
            newops.append(op)
        self.ops = newops
        if self.finalop is not None:
            self.finalop = self.finalop.fold(subst, FOLD_ALL)

    @classmethod
    def encap(cls, val):
        if isinstance(val, Var):
            return ExprVar(val)
        elif isinstance(val, int):
            return ExprConst(val)
        else:
            assert 0

    def get_reg(self, reg):
        assert self.finalop is None
        if isinstance(reg, (IsaReg, IsaVisibleReg)):
            if reg in self.regs:
                return self.encap(self.regs[reg])
            elif reg not in self.inregs:
                val = InVar(self.name + '_in_' + reg.name, reg.mask)
                self.locals.add(val)
                self.inregs[reg] = val
                return self.encap(val)
            else:
                return self.encap(self.inregs[reg])
        elif isinstance(reg, IsaSplitReg):
            res = ExprConst(0)
            for start, len_, field in reg.fields:
                if isinstance(field, int):
                    res |= field << start
                else:
                    res |= self.get_reg(field) << start
            return res
        elif isinstance(reg, IsaSubReg):
            res = self.get_reg(reg.reg)
            res >>= reg.start
            res &= bflmask(reg.len_)
            return res
        else:
            raise DecodeError("unk reg")

    def make_temp(self, expr, name, mask=-1):
        assert self.finalop is None
        expr = expr & mask
        if isinstance(expr, ExprVar):
            return expr.var
        if isinstance(expr, ExprConst):
            return expr.val
        expr = expr.fold(self.vars, FOLD_TOP)
        expr = expr & mask
        if isinstance(expr, ExprVar):
            return expr.var
        if isinstance(expr, ExprConst):
            return expr.val
        var = TempVar(name, expr.bmask)
        self.locals.add(var)
        self.ops.append(DecopAssign(var, expr))
        self.vars[var] = expr
        return var

    def set_reg(self, reg, expr, name):
        assert self.finalop is None
        if isinstance(reg, (IsaReg, IsaVisibleReg)):
            val = self.make_temp(expr, name, reg.dmask)
            if reg in self.inregs and reg not in self.regs and self.inregs[reg] == val:
                pass
            elif reg in self.regs and self.regs[reg] == val:
                pass
            else:
                if isinstance(reg, IsaVisibleReg):
                    self.ops.append(DecopWrite(reg, self.encap(val)))
                self.regs[reg] = val
        elif isinstance(reg, IsaSplitReg):
            for start, len_, field in reg.fields:
                if isinstance(field, int):
                    pass
                else:
                    self.set_reg(field, expr >> start & bflmask(len_), name + '_' + field.name)
        elif isinstance(reg, IsaSubReg):
            mask = bflmask(reg.len_) << reg.start
            res = (self.get_reg(reg.reg) & ~mask) | (expr << reg.start & mask)
            self.set_reg(reg.reg, res, name)
        else:
            raise DecodeError("unk reg")

    def emit_exec(self, name, spec, ins):
        assert self.finalop is None
        #ins = [self.make_temp(in_, name + '_in{}'.format(idx), mask) for (idx, (in_, mask)) in enumerate(zip(ins, spec.imask))]
        outs = [TempVar(name + '_out{}'.format(idx), mask) for idx, mask in enumerate(spec.omask)]
        for out in outs:
            self.locals.add(out)
        #self.ops.append(DecopExec(spec, outs, list(map(self.encap, ins))))
        self.ops.append(DecopExec(spec, outs, ins))
        return [self.encap(out) for out in outs]

    def emit_ld(self, name, space, sz, addr):
        #addr = self.make_temp(addr, name + '_addr', space.amask)
        res = TempVar(name + '_data', bflmask(space.bsz * sz))
        self.locals.add(res)
        #self.ops.append(DecopLd(space, sz, res, self.encap(addr)))
        self.ops.append(DecopLd(space, sz, res, addr))
        return self.encap(res)

    def emit_st(self, name, space, sz, addr, src):
        #addr = self.make_temp(addr, name + '_addr', space.amask)
        #src = self.make_temp(src, name + '_data', bflmask(space.bsz * sz))
        #self.ops.append(DecopSt(space, sz, self.encap(addr), self.encap(src)))
        self.ops.append(DecopSt(space, sz, addr, src))

    def emit_jmp(self, name, addr):
        #addr = self.make_temp(addr, name + '_addr', self.isa.camask)
        #self.finalop = DecopJmp(self.isa, self.encap(addr))
        self.finalop = DecopJmp(self.isa, addr)
        self.outs = [addr.val if isinstance(addr, ExprConst) else None]
        self.outregs = [self.regs]

    def emit_bra(self, name, pred, addr):
        #addr = self.make_temp(addr, name + '_addr', self.isa.camask)
        #pred = self.make_temp(pred, name + '_pred', 1)
        #self.finalop = DecopBra(self.isa, self.encap(pred), self.encap(addr))
        self.finalop = DecopBra(self.isa, pred, addr)
        self.outs = [addr.val if isinstance(addr, ExprConst) else None, ...]
        self.outregs = [self.regs, self.regs]

    def emit_call(self, name, addr):
        #addr = self.make_temp(addr, name + '_addr', self.isa.camask)
        #self.finalop = DecopCall(self.isa, self.encap(addr))
        self.finalop = DecopCall(self.isa, addr)
        self.outs = [...]
        self.outregs = [self.regs]

    def emit_exit(self):
        self.finalop = DecopExit()
        self.outs = [None]
        self.outregs = [self.regs]

    def emit_ret(self):
        self.finalop = DecopRet()
        self.outs = [None]
        self.outregs = [self.regs]

    def emit_iret(self):
        self.finalop = DecopIRet()
        self.outs = [None]
        self.outregs = [self.regs]

    def print(self):
        print("    {}:".format(self.name))
        for reg, var in self.inregs.items():
            print("        IN {} {:#x}".format(reg, var))
        for op in self.ops:
            print("        OP {}".format(op))
        if self.finalop:
            print("        FINALOP {}".format(self.finalop))
            for regs, out in zip(self.outregs, self.outs):
                if isinstance(out, int):
                    print("        OUT -> {:#x}".format(out))
                else:
                    print("        OUT -> {}".format(out))
                for reg, var in regs.items():
                    print("            OUT {} {:#x}".format(reg, var))
        else:
            for reg, var in self.regs.items():
                print("        OUT {} {:#x}".format(reg, var))

from envy.deco.expr.var import ExprVar
from envy.deco.expr.const import ExprConst
from envy.deco.op import DecopAssign, DecopExec, DecopLd, DecopSt, DecopCall, DecopJmp, DecopExit, DecopRet, DecopWrite, DecopBra, DecopIRet
from envy.deco import DecodeError
from envy.isa import ISA_MEM_IO, IsaReg, IsaVisibleReg, IsaSplitReg
