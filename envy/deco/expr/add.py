from envy.deco.expr import ExprBin, Expr
from envy.deco.expr.const import ExprConst
from envy.util import lowmask, highmask
from collections import namedtuple


class Part(namedtuple('Part', ['expr', 'mul'])):
    def __str__(self):
        res = str(self.expr)
        if self.mul > 0:
            res = ' + ' + res
        else:
            res = ' - ' + res
        if abs(self.mul) != 1:
            res += ' * {:#x}'.format(self.mul)
        return res


class ExprSum(Expr):
    def __new__(cls, expr, mask=-1):
        mask = lowmask(mask)
        self = super().__new__(cls)
        self.const = 0
        self.bmask = 0
        self.parts = []
        self._add(expr, mask, 1)
        return self.simplify(mask)

    def simplify(self, mask=-1):
        newparts = []
        for part in self.parts:
            newparts.append(Part(part.expr.mask(mask), part.mul))
        self.parts = newparts
        self.const &= mask
        self.bmask = highmask(self.const)
        for part in self.parts:
            self.bmask |= highmask(part.expr.bmask * part.mul)
        if not self.parts:
            return ExprConst(self.const)
        if not self.const and len(self.parts) == 1:
            part = self.parts[0]
            if part.mul == 1:
                return part.expr
        return self

    def __init__(self, *args):
        pass

    def __str__(self):
        meat = ''.join(map(str, self.parts))
        if self.const:
            meat = '{:#x}'.format(self.const) + meat
        return '(' + meat + ')'

    def fold(self, vars_, reason):
        if reason != FOLD_ALL:
            reason = FOLD_SUM
        res = super().__new__(type(self))
        res.const = self.const
        res.parts = []
        for expr, mul in self.parts:
            res._add(expr.fold(vars_, reason), -1, mul)
        return res.simplify()

    def findvars(self, vars_):
        for part in self.parts:
            part.expr.findvars(vars_)

    def findlivemasks(self, vars_, mask):
        for part in self.parts:
            part.expr.findlivemasks(vars_, lowmask(mask))

    def _add(self, expr, mask, mul):
        if not mul:
            return
        if isinstance(expr, ExprSum):
            self._add(ExprConst(expr.const), mask, mul)
            for sexpr, smul in expr.parts:
                self._add(sexpr, mask, smul * mul)
            return
        if isinstance(expr, ExprAdd):
            self._add(expr.e1, mask, mul)
            self._add(expr.e2, mask, mul)
            return
        if isinstance(expr, ExprSub):
            self._add(expr.e1, mask, mul)
            self._add(expr.e2, mask, -mul)
            return
        if isinstance(expr, ExprMul) and isinstance(expr.e2, ExprConst):
            self._add(expr.e1, mask, mul * expr.e2.val)
            return
        if isinstance(expr, ExprMul) and isinstance(expr.e1, ExprConst):
            self._add(expr.e2, mask, mul * expr.e1.val)
            return
        if isinstance(expr, ExprConst):
            self.const += expr.val * mul
            self.const &= mask
            return
        self.parts.append(Part(expr.mask(mask), mul))

    def mask(self, mask):
        return ExprSum(self, mask)

    def as_offset(self):
        if len(self.parts) > 1:
            return None
        part = self.parts[0]
        if part.mul != 1:
            return None
        if not isinstance(part.expr, ExprVar):
            return None
        return part.expr.var, self.const, -1


class ExprAdd(ExprBin):
    op = '+'

    @classmethod
    def new(cls, e1, e2):
        return ExprSum(super().new(e1, e2))

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, lowmask(mask))
        self.e2.findlivemasks(vars_, lowmask(mask))

    def mask(self, mask):
        e1 = self.e1.mask(lowmask(mask))
        e2 = self.e2.mask(lowmask(mask))
        return e1 + e2


class ExprSub(ExprBin):
    op = '-'

    @classmethod
    def new(cls, e1, e2):
        return ExprSum(super().new(e1, e2))

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, lowmask(mask))
        self.e2.findlivemasks(vars_, lowmask(mask))

    def mask(self, mask):
        e1 = self.e1.mask(lowmask(mask))
        e2 = self.e2.mask(lowmask(mask))
        return e1 - e2


class ExprMul(ExprBin):
    op = '*'

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(e1.val * e2.val)
        if isinstance(e1, ExprConst):
            e1, e2 = e2, e1
        if isinstance(e2, ExprConst):
            return ExprSum(super().new(e1, e2))
        return super().new(e1, e2)

    def mask(self, mask):
        e1 = self.e1.mask(lowmask(mask))
        e2 = self.e2.mask(lowmask(mask))
        return e1 * e2

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, lowmask(mask))
        self.e2.findlivemasks(vars_, lowmask(mask))

from envy.deco.block import FOLD_SUM, FOLD_ALL
from envy.deco.expr.var import ExprVar
