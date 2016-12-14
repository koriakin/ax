from envy.deco.expr import Expr


class ExprConst(Expr):
    def __init__(self, val):
        super().__init__()
        self.val = val
        self.bmask = val

    def mask(self, mask):
        return ExprConst(self.val & mask)

    def __str__(self):
        return hex(self.val)

    def __hash__(self):
        return hash(self.val)
