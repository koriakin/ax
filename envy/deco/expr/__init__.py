class Expr:
    def __init__(self):
        self.bmask = -1

    def __repr__(self):
        return str(self)

    def __or__(self, other):
        return ExprOr(self, other)

    def __and__(self, other):
        return ExprAnd(self, other)

    def __xor__(self, other):
        return ExprXor(self, other)

    def __add__(self, other):
        return ExprAdd(self, other)

    def __sub__(self, other):
        return ExprSub(self, other)

    def __mul__(self, other):
        return ExprMul(self, other)

    def __lshift__(self, other):
        return ExprShl(self, other)

    def __rshift__(self, other):
        return ExprShl(self, -other)

    def __neg__(self):
        return ExprSub(0, self)

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    def mask(self, mask):
        return self

    def fold(self, vars_, reason):
        return self

    def __hash__(self):
        return hash(self.__class__)

    def findvars(self, vars_):
        pass

    def findlivemasks(self, vars_, mask):
        pass

    def as_offset(self):
        return None


class ExprBin(Expr):
    def __new__(cls, e1, e2):
        if isinstance(e1, int):
            e1 = ExprConst(e1)
        if isinstance(e2, int):
            e2 = ExprConst(e2)
        return cls.new(e1, e2)

    def __init__(self, e1, e2):
        super().__init__()

    @classmethod
    def new(cls, e1, e2):
        res = super().__new__(cls)
        res.e1 = e1
        res.e2 = e2
        return res

    def __str__(self):
        return '(' + str(self.e1) + ' ' + self.op + ' ' + str(self.e2) + ')'

    def fold(self, vars_, reason):
        if reason != FOLD_ALL:
            reason = FOLD_OTHER
        e1 = self.e1.fold(vars_, reason)
        e2 = self.e2.fold(vars_, reason)
        return type(self)(e1, e2)

    def findvars(self, vars_):
        self.e1.findvars(vars_)
        self.e2.findvars(vars_)

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, -1)
        self.e2.findlivemasks(vars_, -1)

    def __hash__(self):
        return hash((self.e1, self.e2))

from envy.deco.expr.add import ExprAdd, ExprSub, ExprMul
from envy.deco.expr.const import ExprConst
from envy.deco.expr.logop import ExprAnd, ExprOr, ExprXor, ExprShl
from envy.deco.block import FOLD_OTHER, FOLD_ALL
