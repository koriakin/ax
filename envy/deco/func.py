from envy.deco.object import Object
from collections import Counter


class ConnectError(Exception):
    pass


class If:
    def __init__(self, block, join, outs):
        self.block = block
        self.join = join
        self.outs = outs

    def sprint(self, depth):
        self.block.sprint(depth, self.outs, self.join)


class Loop:
    def __init__(self, body):
        self.body = body

    def sprint(self, depth):
        print("    " * depth + "while True:")
        self.body.sprint(depth + 1)


class Goto:
    def __init__(self, block):
        self.block = block
        block.label = True

    def sprint(self, depth):
        print("    " * depth + "goto " + self.block.name)


class Continue:
    def sprint(self, depth):
        print("    " * depth + "continue")


class Break:
    def sprint(self, depth):
        print("    " * depth + "break")


class Seq(list):
    def sprint(self, depth):
        for x in self:
            x.sprint(depth)
        if not self:
            print("    " * depth + "pass")


def print_phi(depth, outregs, out):
    for reg in out.inregs:
        if isinstance(outregs[reg], int):
            print("    " * depth + "{} = {:#x}".format(out.inregs[reg], outregs[reg]))
        else:
            print("    " * depth + "{} = {}".format(out.inregs[reg], outregs[reg]))


class EntryBlock:
    def __init__(self, func, entry):
        self.func = func
        self.name = func.name + '_entry'
        self.outs = [entry]
        self.livevars = Counter()
        self.localdefs = {}
        self.outregs = [{reg: ParmVar(func.name + '_parm_' + reg.name, reg) for reg in entry.inregs}]
        self.loop = None
        self.join = None
        self.brk = None
        self.used = False
        for reg in entry.inregs:
            self.localdefs[self.outregs[0][reg]] = reg

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def get_out(self, idx, reg):
        if reg not in self.outregs[idx]:
            var = ParmVar(self.func.name + '_parm_' + reg.name, reg)
            self.outregs[idx][reg] = var
            self.localdefs[var] = reg
        return self.outregs[idx][reg]

    def mark_live_out(self, idx, reg, mask):
        if reg not in self.outregs[idx]:
            var = ParmVar(self.func.name + '_parm_' + reg.name, reg)
            self.outregs[idx][reg] = var
            self.localdefs[var] = reg
        else:
            var = self.outregs[idx][reg]
        self.livevars[var] |= mask & reg.mask

    def print(self):
        print("    {}:".format(self.name))
        for regs, out in zip(self.outregs, self.outs):
            if isinstance(out, int):
                print("        OUT -> {:#x}".format(out))
            else:
                print("        OUT -> {}".format(out))
            for reg, var in regs.items():
                print("            OUT {} {:#x}".format(reg, var))
        for var in self.livevars:
            print("        LIVE {} {:x}".format(var, self.livevars[var]))

    def sprint(self, depth):
        print_phi(depth, self.outregs[0], self.outs[0])


class FunBlock:
    def __init__(self, func, block):
        self.func = func
        self.name = block.name
        self.start = block.start
        self.end = block.end
        self.inregs = block.inregs.copy()
        self.ops = block.ops[:]
        self.finalop = block.finalop or DecopJmp(block.isa, ExprConst(block.end))
        self.outs = block.outs[:]
        self.ins = set()
        self.localdefs = {}
        self.livevars = Counter()
        self.outregs = [regs.copy() for regs in block.outregs]
        self.loop = None
        self.join = None
        self.brk = None
        self.used = False
        self.label = False
        for reg in self.inregs:
            self.localdefs[self.inregs[reg]] = reg
        for op in self.ops:
            for out in op.outs:
                self.localdefs[out] = op
        for out in self.finalop.outs:
            self.localdefs[out] = self.finalop

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def mark_live_var(self, var, mask):
        mask &= var.mask
        curmask = self.livevars[var]
        if curmask | mask == curmask:
            return
        self.livevars[var] |= mask
        def_ = self.localdefs[var]
        if isinstance(def_, DecopAssign):
            subvars = Counter()
            def_.src.findlivemasks(subvars, mask)
            for var in subvars:
                self.mark_live_var(var, subvars[var])
        elif isinstance(def_, Decop):
            pass
        elif def_ is not None:
            for block, idx in self.ins:
                block.mark_live_out(idx, def_, mask)

    def get_in(self, reg):
        if reg not in self.inregs:
            var = InVar(self.name + '_in_' + reg.name, reg.mask)
            self.localdefs[var] = reg
            self.inregs[reg] = var
        return self.inregs[reg]

    def get_out(self, idx, reg):
        if reg not in self.outregs[idx]:
            self.outregs[idx][reg] = self.get_in(reg)
        return self.outregs[idx][reg]

    def mark_live_out(self, idx, reg, mask):
        mask &= reg.mask
        if isinstance(self.finalop, DecopRetCall):
            self.finalop.fsig.want_reg(reg, mask)
        val = self.get_out(idx, reg)
        if not isinstance(val, int):
            self.mark_live_var(self.outregs[idx][reg], mask)

    def mark_live_roots(self):
        if isinstance(self.finalop, DecopRet):
            for reg in self.func.wanted_regs:
                self.mark_live_out(0, reg, self.func.wanted_regs[reg])
        subvars = Counter()
        for op in self.ops:
            if not isinstance(op, DecopAssign):
                op.findlivemasks(subvars)
        self.finalop.findlivemasks(subvars)
        for var in subvars:
            self.mark_live_var(var, subvars[var])

    def substvars(self, subst):
        self.ops = [op.substvars(subst) for op in self.ops]
        self.finalop = self.finalop.substvars(subst)
        for regs in self.outregs:
            for reg in list(regs):
                if regs[reg] in subst:
                    regs[reg] = subst[regs[reg]]
        for reg in list(self.inregs):
            if self.inregs[reg] in subst:
                del self.inregs[reg]
                for iblock, idx in self.ins:
                    if reg in iblock.outregs[idx]:
                        del iblock.outregs[idx][reg]
        for var in subst:
            if self.livevars[var]:
                mask = self.livevars[var]
                del self.livevars[var]
                if isinstance(subst[var], Var):
                    self.livevars[subst[var]] |= mask

    def print(self):
        print("    {}:".format(self.name))
        if self.loop:
            print("        LOOP {}".format(self.loop))
        if self.join:
            print("        JOIN {}".format(self.join))
        if self.brk:
            print("        BREAK {}".format(self.brk))
        for iblock, idx in self.ins:
            print("        IN FROM {}.{}".format(iblock, idx))
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
        for var in self.livevars:
            print("        LIVE {} {:x}".format(var, self.livevars[var]))

    def sprint(self, depth, outs=None, join=None):
        if self.label:
            print(self.name + ":")
        for op in self.ops:
            print("    " * depth + str(op))
        if outs is None:
            # simple block
            assert len(self.outs) == 1
            if self.outs[0] is None:
                if isinstance(self.finalop, DecopRet):
                    if self.func.retvals:
                        retvals = ' ' + ', '.join(["{}".format(self.outregs[0][reg]) for reg in sorted(self.func.retvals)])
                    else:
                        retvals = ''
                    print("    " * depth + "return" + retvals)
                else:
                    print("    " * depth + str(self.finalop))
            else:
                if not isinstance(self.finalop, DecopJmp):
                    print("    " * depth + str(self.finalop))
                print_phi(depth, self.outregs[0], self.outs[0])
        else:
            assert len(self.outs) == 2
            assert len(outs) == len(self.outs)
            for idx, ((sout, ju), regs, out) in enumerate(zip(outs, self.outregs, self.outs)):
                if idx == 0:
                    print("    " * depth + "if {}:".format(self.finalop.pred))
                else:
                    print("    " * depth + "else:")
                print_phi(depth + 1, regs, out)
                sout.sprint(depth + 1)


class Function(Object):
    def __init__(self, name, domain, start):
        super().__init__(domain.world)
        self.name = name
        self.domain = domain
        self.isa = domain.isa
        self.section = domain.find_section(self.isa.codemem, start)
        self.start = start
        self.error = None
        self.connected = False
        self.livecheck = False
        self.structure = None
        self.cblocks = None
        self.processed = False
        self.wanted_regs = Counter()
        self.callees = {}
        self.args = {}
        self.retvals = None
        self.mark_dirty()

    def want_reg(self, reg, mask):
        newmask = self.wanted_regs[reg] | mask
        if self.wanted_regs[reg] != newmask:
            self.wanted_regs[reg] |= mask
            self.mark_dirty()

    def process(self):
        self.error = None
        self.connected = False
        self.livecheck = False
        self.structure = None
        self.cblocks = None
        try:
            self.find_blocks()
        except DecodeError as err:
            self.error = err
            return
        try:
            self.connect_blocks()
            self.findlive()
            self.find_sp()
            self.findlive()
            self.glue_blocks()
            self.forward_ins()
            self.find_const_calls()
            self.clean_preserved()
            self.update_sig((self.args, self.retvals))
            self.structuralize()
        except ConnectError as err:
            self.error = err
        self.processed = True

    def find_blocks(self):
        blocks = {self.start}
        queue = [self.start]  # yes, it's a stack.
        while queue:
            addr = queue.pop()
            block = FunBlock(self, Block(self.name + '_{:x}'.format(addr), self.isa, self.section, addr, None))
            self.process_calls(block)
            for out in block.outs:
                if out is not None and out not in blocks:
                    blocks.add(out)
                    queue.append(out)
        blocks = sorted(blocks)
        self.cblocks = {}
        for addr, naddr in zip(blocks, blocks[1:] + [None]):
            self.cblocks[addr] = FunBlock(self, Block(self.name + '_{:x}'.format(addr), self.isa, self.section, addr, naddr))
            self.process_calls(self.cblocks[addr])

    def process_calls(self, block):
        if isinstance(block.finalop, DecopCall):
            func = None
            if isinstance(block.finalop.addr, ExprConst):
                func = self.domain.find_function(block.finalop.addr.val)
            elif block.end in self.callees:
                func = self.domain.find_function(self.callees[block.end])
            if func is not None:
                if not func.processed:
                    func.try_process()
                func.deps.add(self)
                args = {reg: Block.encap(block.get_out(0, reg)) for reg in func.args}
                if func.retvals is None:
                    block.outs[0] = None
                    block.finalop = DecopNoretCall(self.isa, block.finalop.addr, func, args)
                else:
                    rets = {}
                    for reg, name in func.retvals.items():
                        var = TempVar(block.name + '_ret_' + name, reg.mask)
                        block.localdefs[var] = block.finalop
                        rets[reg] = var
                        block.outregs[0][reg] = var
                    block.finalop = DecopRetCall(self.isa, block.finalop.addr, func, rets, args)
            else:
                block.outs[0] = None

    def connect_blocks(self):
        entry = self.cblocks[self.start]
        self.eblock = EntryBlock(self, entry)
        entry.ins.add((self.eblock, 0))
        for block in self.cblocks.values():
            for idx in range(len(block.outs)):
                if isinstance(block.outs[idx], int):
                    target = self.cblocks[block.outs[idx]]
                    target.ins.add((block, idx))
                    block.outs[idx] = target
            if isinstance(block.finalop, DecopRet):
                if self.retvals is None:
                    self.retvals = {}
        self.connected = True

    def find_sp(self):
        self.spoffsets = {}
        if self.isa.stackptr is None:
            return
        if self.isa.stackptr not in self.eblock.outregs[0]:
            return
        osp = self.eblock.get_out(0, self.isa.stackptr)
        offsets = {}
        queue = []
        offsets[osp] = 0
        queue.append((self.eblock.outs[0], self.isa.stackptr, 0))
        spmask = self.isa.stackptr.mask
        while queue:
            block, reg, off = queue.pop()
            ivar = block.get_in(reg)
            if ivar not in offsets:
                offsets[ivar] = off
            elif offsets[ivar] != off and offsets[ivar] is not None:
                offsets[ivar] = None
            else:
                continue
            newoff = {ivar: offsets[ivar]}
            for op in block.ops:
                if not isinstance(op, DecopAssign):
                    continue
                aconv = op.src.as_offset()
                if aconv is None:
                    continue
                avar, aoff, amask = aconv
                if avar not in newoff:
                    continue
                # XXX not correct
                if amask | spmask != amask:
                    continue
                if newoff[avar] is None:
                    newoff[op.dst] = None
                else:
                    newoff[op.dst] = (newoff[avar] + aoff) & lowmask(spmask)
                offsets[op.dst] = newoff[op.dst]
            for out, regs in zip(block.outs, block.outregs):
                if out is not None:
                    for reg in regs:
                        if regs[reg] in newoff:
                            queue.append((out, reg, newoff[regs[reg]]))
        for block in self.cblocks.values():
            newops = []
            subst = {}
            for op in block.ops:
                if isinstance(op, DecopAssign) and op.dst in offsets and offsets[op.dst] is not None:
                    if offsets[op.dst] == 0:
                        subst[op.dst] = osp
                    else:
                        newops.append(DecopAssign(op.dst, Block.encap(osp) + offsets[op.dst] & spmask))
                else:
                    newops.append(op)
            block.ops = newops
            block.localdefs[osp] = None
            block.substvars(subst)
        self.spoffsets = offsets

    def findlive(self):
        for block in self.cblocks.values():
            block.mark_live_roots()
        for block in self.cblocks.values():
            for reg in list(block.inregs):
                if not block.livevars[block.inregs[reg]]:
                    del block.inregs[reg]
        for block in self.cblocks.values():
            block.ops = [op for op in block.ops if not isinstance(op, DecopAssign) or block.livevars[op.dst]]
            for out, regs in zip(block.outs, block.outregs):
                if out is None:
                    if isinstance(block.finalop, DecopRet):
                        regs = {reg: regs[reg] for reg in self.wanted_regs}
                    else:
                        regs.clear()
                else:
                    for reg in list(regs):
                        if reg not in out.inregs:
                            del regs[reg]
        self.livecheck = True

    def glue_blocks(self):
        for block in list(self.cblocks.values()):
            if not block.ops and isinstance(block.finalop, DecopJmp) and isinstance(block.outs[0], FunBlock):
                for iblock, idx in block.ins:
                    outregs = {}
                    for reg in block.outregs[0]:
                        tvar = block.outregs[0][reg]
                        if isinstance(tvar, int):
                            outregs[reg] = tvar
                        else:
                            ireg = block.localdefs[tvar]
                            outregs[reg] = iblock.outregs[idx][ireg]
                    iblock.outs[idx] = block.outs[0]
                    iblock.outregs[idx] = outregs
                    block.outs[0].ins.add((iblock, idx))
                block.outs[0].ins.remove((block, 0))
                del self.cblocks[block.start]

    def forward_ins(self):
        # extract variables
        vnext = {}
        vprev = {}
        for block in self.cblocks.values():
            for iblock, idx in block.ins:
                for reg in block.inregs:
                    src = iblock.outregs[idx][reg]
                    dst = block.inregs[reg]
                    if src not in vnext:
                        vnext[src] = set()
                        vprev[src] = set()
                    if dst not in vprev:
                        vprev[dst] = set()
                        vnext[dst] = set()
                    vnext[src].add(dst)
                    vprev[dst].add(src)
        vars = set(var for var in vnext)
        # color them
        color = {}
        for var in vars:
            if var not in color:
                queue = [var]
                color[var] = var
                while queue:
                    svar = queue.pop()
                    for ssvar in vnext[svar]:
                        if ssvar not in color:
                            color[ssvar] = var
                            queue.append(ssvar)
                    for ssvar in vprev[svar]:
                        if ssvar not in color:
                            color[ssvar] = var
                            queue.append(ssvar)
        # index colors
        rcolor = {}
        for var in vars:
            if color[var] not in rcolor:
                rcolor[color[var]] = set()
            rcolor[color[var]].add(var)
        # prepare substitution dict
        subst = {}
        # now process each color
        for c in rcolor:
            numroot = 0
            root = None
            for v in rcolor[c]:
                if not isinstance(v, InVar):
                    numroot += 1
                    root = v
            assert numroot
            if numroot == 1:
                # simple case
                for v in rcolor[c]:
                    if isinstance(v, InVar):
                        subst[v] = root
            else:
                # complex case
                shadow = {}
                # compute dominance sets
                for v in rcolor[c]:
                    queue = []
                    marked = set()
                    for root in rcolor[c]:
                        if not isinstance(root, InVar) and root != v:
                            queue.append(root)
                            marked.add(root)
                    while queue:
                        svar = queue.pop()
                        for ssvar in vnext[svar]:
                            if ssvar not in marked and ssvar != v:
                                marked.add(ssvar)
                                queue.append(ssvar)
                    shadow[v] = rcolor[c] - marked
                # largest sets first
                sshadow = sorted(shadow.items(), key=lambda x: len(x[1]), reverse=True)
                # compute actual substitutions
                for root, svars in sshadow:
                    for svar in svars:
                        if svar != root and svar not in subst:
                            subst[svar] = root
        for block in self.cblocks.values():
            block.substvars(subst)
        self.forward_done = True

    def find_const_calls(self):
        # XXX
        for block in self.cblocks.values():
            if isinstance(block.finalop, DecopCall) and isinstance(block.finalop.addr, ExprConst):
                addr = block.finalop.addr.val
                if block.end not in self.callees:
                    self.callees[block.end] = addr
                    self.mark_dirty()

    def clean_preserved(self):
        for block in self.cblocks.values():
            if isinstance(block.finalop, DecopRet):
                for reg in self.wanted_regs:
                    if reg != self.eblock.localdefs.get(block.outregs[0][reg], None) and reg not in self.retvals:
                        self.retvals[reg] = 'ret_' + reg.name
        for block in self.cblocks.values():
            if isinstance(block.finalop, DecopRet):
                for reg in self.wanted_regs:
                    if reg not in self.retvals:
                        del block.outregs[0][reg]
        livevars = Counter()
        for block in self.cblocks.values():
            for op in block.ops:
                op.findlivemasks(livevars)
            block.finalop.findlivemasks(livevars)
            for regs in block.outregs:
                for reg in regs:
                    livevars[regs[reg]] = -1
        for var in self.eblock.livevars:
            if var in livevars:
                self.args[self.eblock.localdefs[var]] = (var, self.eblock.livevars[var])

    def structuralize(self):
        stack = []
        done = set()
        active = set()
        stack.append((self.eblock, 0))
        active.add(self.eblock)
        depth = {self.eblock: 0, None: -1}
        parent = {}
        joins = []
        while stack:
            block, idx = stack.pop()
            if idx < len(block.outs):
                stack.append((block, idx + 1))
                nblock = block.outs[idx]
                if not nblock:
                    pass
                elif nblock in done:
                    # a join
                    joins.append((block, nblock))
                    # .. perhaps within a loop
                    tl = nblock
                    while tl.loop is not None and tl.loop not in active:
                        tl = parent[tl]
                    tl = tl.loop
                    if tl is not None:
                        cblock = block
                        while cblock != tl:
                            if depth[cblock.loop] < depth[tl]:
                                cblock.loop = tl
                            cblock = parent[cblock]
                elif nblock in active:
                    # a loop
                    nblock.loop = nblock
                    cblock = block
                    while cblock != nblock:
                        if depth[cblock.loop] < depth[nblock]:
                            cblock.loop = nblock
                        cblock = parent[cblock]
                else:
                    depth[nblock] = len(stack)
                    parent[nblock] = block
                    stack.append((nblock, 0))
                    active.add(nblock)
            else:
                active.remove(block)
                done.add(block)

        def lca(a, b):
            if a is None or b is None:
                return None
            while depth[a] > depth[b]:
                a = parent[a]
            while depth[b] > depth[a]:
                b = parent[b]
            while b != a:
                b = parent[b]
                a = parent[a]
            return a

        for a, b in joins:
            split = lca(a, b)
            if split.loop == b.loop:
                # same loop, make an if join
                # in case of join conflict, prefer deeper one
                if depth[split.join] < depth[b]:
                    split.join = b
            # XXX
            if False:
                # if a branch into a loop, or between unrelated loops, ignore it
                if depth[a.loop] < depth[b.loop]:
                    continue
                # find parent loop
                p = a.loop
                while p.loop == a.loop:
                    p = parent[p]
                # if target is not in the immediately containing loop, bail
                if p.loop != b.loop:
                    continue
                # otherwise, use it to find the best break target
                if depth[a.loop.brk] < depth[b]:
                    a.loop.brk = b

        self.structure, _ = self.struct_seq(self.eblock)
        for block in self.cblocks.values():
            assert block.used

    def struct_seq(self, block, join=None, cont=None, brk=None):
        res = Seq()
        entry = block
        while block:
            if block == brk:
                res.append(Break())
                return (res, False)
            if block.used or entry != cont:
                if block == join:
                    return (res, True)
                elif block == cont:
                    res.append(Continue())
                    return (res, False)
            if block.used:
                res.append(Goto(block))
                return (res, False)
            if block.loop != cont and block.loop == block:
                sbrk = block.brk or join
                loop, _ = self.struct_seq(block, block, block, sbrk)
                res.append(Loop(loop))
                block = sbrk
            elif len(block.outs) == 1:
                block.used = True
                res.append(block)
                block = block.outs[0]
            else:
                block.used = True
                sjoin = block.join or join
                outs = [self.struct_seq(out, sjoin, cont, brk) for out in block.outs]
                if not any(ju for _, ju in outs):
                    sjoin = None
                res.append(If(block, sjoin, outs))
                block = sjoin
        return (res, False)

    def print(self):
        if not self.cblocks:
            print(self.name + ':')
            print("    ERROR {}".format(self.error))
        elif not self.connected:
            print(self.name + ' [CONNECT FAILED]:')
            for addr in sorted(self.cblocks):
                self.cblocks[addr].print()
        else:
            if self.structure is not None:
                args = ["{} : {}[{:#x}]".format(self.args[reg][0], reg, self.args[reg][1]) for reg in sorted(self.args)]
                if self.retvals is not None:
                    retvals = ' -> (' + ', '.join(["{} : {}[{:#x}]".format(self.retvals[reg], reg, self.wanted_regs[reg]) for reg in sorted(self.retvals)]) + ')'
                else:
                    retvals = ''
                print("def " + self.name + '(' + ', '.join(args) + ')' + retvals + ':')
                self.structure.sprint(1)
            else:
                print(self.name + ':')
                if self.error is not None:
                    print("    ERROR {}".format(self.error))
                self.eblock.print()
                for addr in sorted(self.cblocks):
                    self.cblocks[addr].print()
        print()

from envy.deco.block import Block, Var, ParmVar, InVar, TempVar
from envy.deco.op import Decop, DecopJmp, DecopAssign, DecopCall, DecopRet, DecopNoretCall, DecopRetCall
from envy.deco.expr.const import ExprConst
from envy.deco import DecodeError
from envy.util import lowmask
