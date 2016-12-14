from envy.deco.expr import Expr


class ExprVar(Expr):
    def __init__(self, var, omask=-1):
        super().__init__()
        self.var = var
        self.bmask = var.mask
        self.omask = omask & var.mask

    def __str__(self):
        return self.var.name

    def __hash__(self):
        return hash(self.var.name)

    def fold(self, vars_, reason):
        if self.var not in vars_:
            return self
        val = vars_[self.var]
        if not isinstance(val, Expr):
            val = Block.encap(val)
        return val
        # meh.
        if reason in [FOLD_TOP, FOLD_ALL]:
            return val
        if isinstance(val, (ExprConst, ExprVar)):
            return val
        if isinstance(val, ExprBigOr) and reason == FOLD_BIGOR:
            return val
        if isinstance(val, ExprBigOr) and reason == FOLD_SUM and len(val.bitfields) == 1 and isinstance(val.bitfields[0].expr, ExprSum):
            return val
        if isinstance(val, ExprSum) and reason == FOLD_SUM:
            return val
        return self

    def mask(self, mask):
        return ExprVar(self.var, self.omask & mask)

    def findvars(self, vars_):
        vars_[self.var] += 1

    def findlivemasks(self, vars_, mask):
        vars_[self.var] |= mask

from envy.deco.expr.logop import ExprBigOr
from envy.deco.expr.add import ExprSum
from envy.deco.expr.const import ExprConst
from envy.deco.block import FOLD_TOP, FOLD_ALL, FOLD_BIGOR, FOLD_SUM, Block
