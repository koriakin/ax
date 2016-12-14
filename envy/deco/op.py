from envy.util import bflmask


class Decop:
    outs = ()

    def __repr__(self):
        return str(self)

    def findvars(self, vars_):
        pass

    def findlivemasks(self, vars_):
        pass

    def fold(self, vars_, reason):
        return self

    def substvars(self, vars_):
        return self


class DecopExit(Decop):
    def __str__(self):
        return "exit"


class DecopRet(Decop):
    def __str__(self):
        return "return"


class DecopIRet(Decop):
    def __str__(self):
        return "iret"


class DecopExec(Decop):
    def __init__(self, spec, outs, ins):
        super().__init__()
        self.spec = spec
        self.outs = outs
        self.ins = ins
        assert len(ins) == len(spec.imask)

    def findvars(self, vars_):
        for in_ in self.ins:
            in_.findvars(vars_)

    def findlivemasks(self, vars_):
        for in_, mask in zip(self.ins, self.spec.imask):
            in_.findlivemasks(vars_, mask)

    def __str__(self):
        outs = ", ".join(map('{}'.format, self.outs)) + " = " if self.outs else ""
        return outs + self.spec.name + "(" + ", ".join(map('{}'.format, self.ins)) + ')'

    def fold(self, vars_, reason):
        return DecopExec(self.spec, self.outs, [in_.fold(vars_, reason).mask(mask) for in_, mask in zip(self.ins, self.spec.imask)])

    def substvars(self, vars_):
        ins = [in_.fold(vars_, FOLD_ALL).mask(mask) for in_, mask in zip(self.ins, self.spec.imask)]
        outs = [vars_.get(out, out) for out in self.outs]
        return DecopExec(self.spec, outs, ins)


class DecopLd(Decop):
    def __init__(self, space, sz, dst, addr):
        super().__init__()
        self.space = space
        self.sz = sz
        self.dst = dst
        self.addr = addr
        self.outs = [dst]

    def findvars(self, vars_):
        self.addr.findvars(vars_)

    def findlivemasks(self, vars_):
        self.addr.findlivemasks(vars_, self.space.amask)

    def __str__(self):
        return "{} = {}.{}[{}]".format(self.dst, self.space, self.sz, self.addr)

    def fold(self, vars_, reason):
        return DecopLd(self.space, self.sz, self.dst, self.addr.fold(vars_, reason).mask(self.space.amask))

    def substvars(self, vars_):
        return DecopLd(self.space, self.sz, vars_.get(self.dst, self.dst), self.addr.fold(vars_, FOLD_ALL).mask(self.space.amask))


class DecopSt(Decop):
    def __init__(self, space, sz, addr, src):
        super().__init__()
        self.space = space
        self.sz = sz
        self.addr = addr
        self.src = src

    def findvars(self, vars_):
        self.addr.findvars(vars_)
        self.src.findvars(vars_)

    def findlivemasks(self, vars_):
        self.addr.findlivemasks(vars_, self.space.amask)
        self.src.findlivemasks(vars_, bflmask(self.space.bsz * self.sz))

    def __str__(self):
        return "{}.{}[{}] = {}".format(self.space, self.sz, self.addr, self.src)

    def fold(self, vars_, reason):
        return DecopSt(self.space, self.sz, self.addr.fold(vars_, reason).mask(self.space.amask), self.src.fold(vars_, reason).mask(bflmask(self.space.bsz * self.sz)))

    def substvars(self, vars_):
        return self.fold(vars_, FOLD_ALL)


class DecopAssign(Decop):
    def __init__(self, dst, src):
        super().__init__()
        self.dst = dst
        self.src = src
        self.outs = [dst]

    def findvars(self, vars_):
        self.src.findvars(vars_)

    def findlivemasks(self, vars_):
        self.src.findlivemasks(vars_, self.dst.mask)

    def __str__(self):
        return "{} = {}".format(self.dst, self.src)

    def fold(self, vars_, reason):
        return DecopAssign(self.dst, self.src.fold(vars_, reason).mask(-1))

    def substvars(self, vars_):
        return DecopAssign(vars_.get(self.dst, self.dst), self.src.fold(vars_, FOLD_ALL).mask(-1))


class DecopWrite(Decop):
    def __init__(self, dst, src):
        super().__init__()
        self.dst = dst
        self.src = src

    def findvars(self, vars_):
        self.src.findvars(vars_)

    def findlivemasks(self, vars_):
        self.src.findlivemasks(vars_, self.dst.dmask)

    def __str__(self):
        return "{} = {}".format(self.dst, self.src)

    def fold(self, vars_, reason):
        return DecopWrite(self.dst, self.src.fold(vars_, reason).mask(self.dst.dmask))

    def substvars(self, vars_):
        return self.fold(vars_, FOLD_ALL)


class DecopJmp(Decop):
    def __init__(self, isa, addr):
        super().__init__()
        self.isa = isa
        self.addr = addr

    def findvars(self, vars_):
        self.addr.findvars(vars_)

    def findlivemasks(self, vars_):
        self.addr.findlivemasks(vars_, self.isa.codemem.amask)

    def __str__(self):
        return "JMP {}".format(self.addr)

    def fold(self, vars_, reason):
        return DecopJmp(self.isa, self.addr.fold(vars_, reason).mask(self.isa.codemem.amask))

    def substvars(self, vars_):
        return self.fold(vars_, FOLD_ALL)


class DecopCall(Decop):
    def __init__(self, isa, addr):
        super().__init__()
        self.isa = isa
        self.addr = addr

    def findvars(self, vars_):
        self.addr.findvars(vars_)

    def findlivemasks(self, vars_):
        self.addr.findlivemasks(vars_, self.isa.codemem.amask)

    def __str__(self):
        return "{}() # UNBOUND".format(self.addr)

    def fold(self, vars_, reason):
        return DecopCall(self.isa, self.addr.fold(vars_, reason).mask(self.isa.codemem.amask))

    def substvars(self, vars_):
        return self.fold(vars_, FOLD_ALL)


class DecopNoretCall(Decop):
    def __init__(self, isa, addr, fsig, args):
        super().__init__()
        self.isa = isa
        self.addr = addr
        self.args = args
        self.fsig = fsig

    def findvars(self, vars_):
        self.addr.findvars(vars_)
        for reg in self.args:
            self.args[reg].findvars(vars_)

    def findlivemasks(self, vars_):
        self.addr.findlivemasks(vars_, self.isa.codemem.amask)
        for reg in self.args:
            self.args[reg].findlivemasks(vars_, self.fsig.args[reg][1])

    def __str__(self):
        args = "(" + ", ".join('{}={}'.format(self.fsig.args[reg][0], self.args[reg]) for reg in sorted(self.args)) + ')'
        if isinstance(self.fsig, Function):
            return self.fsig.name + args + ' # noreturn'
        else:
            return str(self.addr) + args + ' # noreturn'

    def fold(self, vars_, reason):
        args = {reg: self.args[reg].fold(vars_, reason).mask(self.fsig.args[reg][1]) for reg in self.args}
        return DecopNoretCall(self.isa, self.addr.fold(vars_, reason).mask(self.isa.codemem.amask), self.fsig, args)

    def substvars(self, vars_):
        return self.fold(vars_, FOLD_ALL)


class DecopRetCall(Decop):
    def __init__(self, isa, addr, fsig, rets, args):
        super().__init__()
        self.isa = isa
        self.addr = addr
        self.args = args
        self.fsig = fsig
        self.rets = rets
        self.outs = list(rets.values())

    def findvars(self, vars_):
        self.addr.findvars(vars_)
        for reg in self.args:
            self.args[reg].findvars(vars_)

    def findlivemasks(self, vars_):
        self.addr.findlivemasks(vars_, self.isa.codemem.amask)
        for reg in self.args:
            self.args[reg].findlivemasks(vars_, self.fsig.args[reg][1])

    def __str__(self):
        args = "(" + ", ".join('{}={}'.format(self.fsig.args[reg][0], self.args[reg]) for reg in sorted(self.args)) + ')'
        if self.rets:
            rets = ', '.join(str(out) for reg, out in sorted(self.rets.items())) + ' = '
            if len(self.rets) > 1:
                retsel = '[' + ', '.join(str(reg) for reg, out in sorted(self.rets.items())) + ']'
            else:
                retsel = ''
        else:
            rets = ''
            retsel = ''
        if isinstance(self.fsig, Function):
            return rets + self.fsig.name + args + retsel
        else:
            return rets + str(self.addr) + args + retsel

    def fold(self, vars_, reason):
        args = {reg: self.args[reg].fold(vars_, reason).mask(self.fsig.args[reg][1]) for reg in self.args}
        return DecopRetCall(self.isa, self.addr.fold(vars_, reason).mask(self.isa.codemem.amask), self.fsig, self.rets, args)

    def substvars(self, vars_):
        args = {reg: self.args[reg].fold(vars_, FOLD_ALL).mask(self.fsig.args[reg][1]) for reg in self.args}
        rets = {reg: vars_.get(out, out) for reg, out in self.rets.items()}
        return DecopRetCall(self.isa, self.addr.fold(vars_, FOLD_ALL).mask(self.isa.codemem.amask), self.fsig, rets, args)


class DecopBra(Decop):
    def __init__(self, isa, pred, addr):
        super().__init__()
        self.isa = isa
        self.pred = pred
        self.addr = addr

    def findvars(self, vars_):
        self.pred.findvars(vars_)
        self.addr.findvars(vars_)

    def findlivemasks(self, vars_):
        self.pred.findlivemasks(vars_, -1)
        self.addr.findlivemasks(vars_, self.isa.codemem.amask)

    def __str__(self):
        return "BRA {} {}".format(self.pred, self.addr)

    def fold(self, vars_, reason):
        return DecopBra(self.isa,
                        self.pred.fold(vars_, reason).mask(-1),
                        self.addr.fold(vars_, reason).mask(self.isa.codemem.amask))

    def substvars(self, vars_):
        return self.fold(vars_, FOLD_ALL)


from envy.deco.block import Var, FOLD_ALL
from envy.deco.func import Function
