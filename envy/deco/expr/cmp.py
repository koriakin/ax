from envy.deco.expr import ExprBin
from envy.deco.expr.const import ExprConst


class ExprBinBool(ExprBin):
    def __init__(self, e1, e2):
        super().__init__(e1, e2)
        self.bmask = 1

    def negate(self):
        return self.negtype(self.e1, self.e2)


class ExprEq(ExprBinBool):
    op = '=='

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(e1.val == e2.val)
        return super().new(e1, e2)


class ExprNe(ExprBinBool):
    op = '!='

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(e1.val != e2.val)
        return super().new(e1, e2)


class ExprLt(ExprBinBool):
    op = '<'

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(e1.val < e2.val)
        return super().new(e1, e2)


class ExprGe(ExprBinBool):
    op = '>='

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(e1.val >= e2.val)
        return super().new(e1, e2)

ExprEq.negtype = ExprNe
ExprNe.negtype = ExprEq
ExprGe.negtype = ExprLt
ExprLt.negtype = ExprGe
