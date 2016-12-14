from envy.deco.expr import ExprBin, Expr
from envy.deco.expr.const import ExprConst
from envy.util import bflmask, sext, shl
from collections import namedtuple


class Bitfield(namedtuple('Bitfield', ['expr', 'sign', 'shift', 'mask'])):
    def __str__(self):
        res = str(self.expr)
        if self.sign is not None:
            res = 'sext({}, {})'.format(res, self.sign)
        if self.shift > 0:
            res += ' << {}'.format(self.shift)
        if self.shift < 0:
            res += ' >> {}'.format(-self.shift)
        if self.mask != -1:
            res += ' & {:#x}'.format(self.mask)
        return res


class ExprBigOr(Expr):
    def __new__(cls, expr, mask=-1):
        self = super().__new__(cls)
        self.const = 0
        self.bmask = 0
        self.bitfields = []
        self._add(expr, None, 0, mask)
        return self.simplify(mask)

    def simplify(self, mask):
        newbitfields = []
        for bf in self.bitfields:
            if (bf.mask | self.const) == self.const:
                pass
            elif ((mask & shl(sext(bf.expr.bmask, bf.sign), bf.shift)) | bf.mask) == bf.mask:
                newbitfields.append(Bitfield(bf.expr, bf.sign, bf.shift, -1))
            else:
                newbitfields.append(bf)
        self.bitfields = newbitfields
        if not self.bitfields:
            return ExprConst(self.const)
        if not self.const and len(self.bitfields) == 1:
            bf = self.bitfields[0]
            if bf.mask == -1 and bf.sign is None and bf.shift == 0:
                return bf.expr
        return self

    def __init__(self, *args):
        pass

    def __str__(self):
        meat = ' | '.join(map(str, self.bitfields))
        if self.const:
            meat += ' | {:#x}'.format(self.const)
        return '(' + meat + ')'

    def fold(self, vars_, reason):
        if reason != FOLD_ALL:
            reason = FOLD_BIGOR
        res = super().__new__(type(self))
        res.const = self.const
        res.bmask = self.const
        res.bitfields = []
        for expr, sign, shift, mask in self.bitfields:
            res._add(expr.fold(vars_, reason), sign, shift, mask)
        return res.simplify(-1)

    def findvars(self, vars_):
        for bf in self.bitfields:
            bf.expr.findvars(vars_)

    def findlivemasks(self, vars_, mask):
        for bf in self.bitfields:
            imask = shl(mask & bf.mask, -bf.shift)
            if bf.sign is not None:
                if imask & -1 << bf.sign:
                    imask |= 1 << bf.sign
                imask &= bflmask(bf.sign + 1)
            bf.expr.findlivemasks(vars_, imask)

    def _reduce(self, ssign, sshift, smask, sign, shift, mask):
        # sext(sext(EXPR, ssign) << sshift & smask, sign) << shift & mask
        mask &= shl(sext(smask, sign), shift)
        # sext(sext(EXPR, ssign) << sshift, sign) << shift & mask
        if sign is not None:
            sign -= sshift
            if sign < 0:
                return None, 0, 0
        # sext(sext(EXPR, ssign), sign) << sshift << shift & mask
        if ssign is not None:
            if sign is None:
                sign = ssign
            else:
                sign = min(sign, ssign)
        # sext(EXPR, sign) << sshift << shift & mask
        shift += sshift
        # sext(EXPR, sign) << shift & mask
        return sign, shift, mask

    # self |= sext(expr, sign) << shift & mask
    def _add(self, expr, sign, shift, mask):
        if sign is not None and not (mask & shl(-1, shift + sign + 1)):
            sign = None
        if not mask:
            return
        imask = shl(mask, -shift)
        if sign is not None:
            if imask & -1 << sign:
                imask |= 1 << sign
            imask &= bflmask(sign + 1)
        if isinstance(expr, ExprBigOr):
            self._add(ExprConst(expr.const), sign, shift, mask)
            for sexpr, ssign, sshift, smask in expr.bitfields:
                self._add(sexpr, *self._reduce(ssign, sshift, smask, sign, shift, mask))
            return
        if isinstance(expr, ExprAnd):
            e1 = expr.e1.mask(imask)
            e2 = expr.e2.mask(imask)
            if isinstance(e1, ExprConst):
                e2, e1 = e1, e2
            if isinstance(e2, ExprConst):
                self._add(e1, *self._reduce(None, 0, e2.val, sign, shift, mask))
                return
        if isinstance(expr, ExprOr):
            self._add(expr.e1, sign, shift, mask)
            self._add(expr.e2, sign, shift, mask)
            return
        if isinstance(expr, ExprConst):
            val = shl(sext(expr.val, sign), shift) & mask
            self.const |= val
            self.bmask |= val
            return
        if isinstance(expr, ExprShl) and isinstance(expr.e2, ExprConst):
            self._add(expr.e1, *self._reduce(None, expr.e2.val, -1, sign, shift, mask))
            return
        if isinstance(expr, ExprSext) and isinstance(expr.e2, ExprConst):
            self._add(expr.e1, *self._reduce(expr.e2.val, 0, -1, sign, shift, mask))
            return
        expr = expr.mask(imask)
        if not expr.bmask & imask:
            return
        self.bmask |= shl(sext(expr.bmask, sign), shift) & mask
        self.bitfields.append(Bitfield(expr, sign, shift, mask))

    def mask(self, mask):
        return ExprBigOr(self, mask)

    def as_offset(self):
        if self.const or len(self.bitfields) != 1:
            return None
        bf = self.bitfields[0]
        if bf.sign is not None or bf.shift != 0:
            return None
        sconv = bf.expr.as_offset()
        if sconv is None:
            return None
        svar, soff, smask = sconv
        return svar, soff, smask & bf.mask


class ExprShl(ExprBin):
    op = '<<'

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(shl(e1.val, e2.val))
        if isinstance(e2, ExprConst):
            if e2.val == 0:
                return e1
            return ExprBigOr(super().new(e1, e2))
        return super().new(e1, e2)


class ExprAnd(ExprBin):
    op = '&'

    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(e1.val & e2.val)
        if (e1.bmask & e2.bmask) == 0:
            return ExprConst(0)
        if isinstance(e1, ExprConst):
            e1, e2 = e2, e1
        if isinstance(e2, ExprConst):
            return ExprBigOr(super().new(e1, e2))
        return super().new(e1, e2)

    def mask(self, mask):
        e1 = self.e1.mask(mask)
        e2 = self.e2.mask(mask)
        return e1 & e2

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, mask)
        self.e2.findlivemasks(vars_, mask)


class ExprOr(ExprBin):
    op = '|'

    @classmethod
    def new(cls, e1, e2):
        return ExprBigOr(super().new(e1, e2))

    def __init__(self, e1, e2):
        super().__init__(e1, e2)
        self.bmask = self.e1.bmask | self.e2.bmask

    def mask(self, mask):
        e1 = self.e1.mask(mask)
        e2 = self.e2.mask(mask)
        return e1 | e2

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, mask)
        self.e2.findlivemasks(vars_, mask)


class ExprBigXor(Expr):
    def __new__(cls, expr, mask=-1):
        self = super().__new__(cls)
        self.const = 0
        self.exprs = set()
        self._add(expr, mask)
        return self.simplify()

    def simplify(self):
        self.bmask = self.const
        for expr in self.exprs:
            self.bmask |= expr.bmask
        if not self.exprs:
            return ExprConst(self.const)
        if self.const == 1:
            for expr in list(self.exprs):
                if isinstance(expr, ExprBinBool):
                    self.const = 0
                    self.exprs ^= {expr, expr.negate()}
        if not self.const and len(self.exprs) == 1:
            return list(self.exprs)[0]
        return self

    def __init__(self, *args):
        pass

    def __str__(self):
        meat = ' ^ '.join(map(str, self.exprs))
        if self.const:
            meat += ' ^ {:#x}'.format(self.const)
        return '(' + meat + ')'

    def fold(self, vars_, reason):
        if reason != FOLD_ALL:
            reason = FOLD_BIGOR
        res = super().__new__(type(self))
        res.const = self.const
        res.exprs = set()
        for expr in self.exprs:
            res._add(expr.fold(vars_, reason), -1)
        return res.simplify()

    def findvars(self, vars_):
        for expr in self.exprs:
            expr.findvars(vars_)

    def findlivemasks(self, vars_, mask):
        for expr in self.exprs:
            expr.findlivemasks(vars_, mask)

    def _add(self, expr, mask):
        if isinstance(expr, ExprBigXor):
            self._add(ExprConst(expr.const), mask)
            for sexpr in expr.exprs:
                self._add(sexpr, mask)
            return
        if isinstance(expr, ExprXor):
            self._add(expr.e1, mask)
            self._add(expr.e2, mask)
            return
        if isinstance(expr, ExprConst):
            self.const ^= expr.val
            return
        expr = expr.mask(mask)
        if not expr.bmask & mask:
            return
        self.exprs ^= {expr}

    def mask(self, mask):
        return ExprBigXor(self, mask)


class ExprXor(ExprBin):
    op = '^'

    @classmethod
    def new(cls, e1, e2):
        return ExprBigXor(super().new(e1, e2))

    def __init__(self, e1, e2):
        super().__init__(e1, e2)
        self.bmask = self.e1.bmask | self.e2.bmask

    def mask(self, mask):
        e1 = self.e1.mask(mask)
        e2 = self.e2.mask(mask)
        return e1 ^ e2

    def findlivemasks(self, vars_, mask):
        self.e1.findlivemasks(vars_, mask)
        self.e2.findlivemasks(vars_, mask)


class ExprSext(ExprBin):
    @classmethod
    def new(cls, e1, e2):
        if isinstance(e1, ExprConst) and isinstance(e2, ExprConst):
            return ExprConst(sext(e1.val, e2.val))
        if isinstance(e2, ExprConst):
            return ExprBigOr(super().new(e1, e2))
        return super().new(e1, e2)

    def __str__(self):
        return 'sext(' + str(self.e1) + ', ' + str(self.e2) + ')'

from envy.deco.block import FOLD_BIGOR, FOLD_ALL
from envy.deco.expr.cmp import ExprBinBool
