from envy.util import bflmask


class Isa:
    pass

ISA_MEM_RO = 'ro'
ISA_MEM_RW = 'rw'
ISA_MEM_IO = 'io'


class IsaMem:
    def __init__(self, name, bsz, amask, mode):
        self.name = name
        self.bsz = bsz
        self.amask = amask
        self.mode = mode

    def __str__(self):
        return self.name


class IsaReg:
    def __init__(self, name, mask):
        self.name = name
        self.mask = mask
        self.dmask = mask

    def __str__(self):
        return '$' + self.name

    def __lt__(self, other):
        return self.name < other.name

    def __hash__(self):
        return hash(self.name)


class IsaVisibleReg:
    def __init__(self, name, mask):
        self.name = name
        self.mask = mask
        self.dmask = mask

    def __str__(self):
        return '$' + self.name

    def __lt__(self, other):
        return self.name < other.name

    def __hash__(self):
        return hash(self.name)


class IsaSubReg:
    def __init__(self, reg, start, len_):
        self.reg = reg
        self.start = start
        self.len_ = len_


class IsaExec:
    def __init__(self, name, omask, imask):
        self.name = name
        self.omask = omask
        self.imask = imask

    def __str__(self):
        return self.name


class IsaSplitReg:
    def __init__(self, name, fields):
        self.name = name
        self.mask = 0
        self.dmask = 0
        self.fields = fields
        for start, len_, field in fields:
            mask = bflmask(len_) << start
            if isinstance(field, (IsaReg, IsaVisibleReg)):
                self.dmask |= mask
                self.mask |= mask
            elif isinstance(field, int):
                self.mask |= field << start
            else:
                raise TypeError("Unknown field type")

    def __str__(self):
        return '$' + self.name
