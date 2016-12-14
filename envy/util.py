def bflmask(a):
    return (1 << a) - 1


def sext(a, b):
    if b is None:
        return a
    if a & 1 << b:
        return a | ~bflmask(b)
    else:
        return a & bflmask(b)


def extr(a, b, c):
    return (a >> b) & bflmask(c)


def extrs(a, b, c):
    return sext(extr(a, b, c), c - 1)


def lowmask(mask):
    if mask < 0:
        return -1
    return bflmask(mask.bit_length())


def highmask(mask):
    if mask < 0:
        mask = -mask
    for idx in range(mask):
        if mask & 1 << idx:
            return -1 << idx
    return 0


def shl(a, b):
    if b > 0:
        return a << b
    else:
        return a >> -b
