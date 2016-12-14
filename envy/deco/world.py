class World:
    def __init__(self):
        self.sections = []
        self.domains = []
        self.dirties = set()

    def process(self):
        while self.dirties:
            obj = self.dirties.pop()
            obj.dirty = False
            obj.inproc = True
            obj.process()
            obj.inproc = False

    def print(self):
        for section in self.sections:
            section.print()


class Domain:
    def __init__(self, world, isa):
        self.world = world
        self.isa = isa
        self.spaces = {}

    def add_section(self, space, section):
        if space not in self.spaces:
            self.spaces[space] = []
        self.spaces[space].append(section)

    def find_section(self, space, addr):
        for section in self.spaces[space]:
            if addr in section.range:
                return section
        raise IndexError("No section mapped at {:x}".format(addr))

    def lookup(self, space, addr):
        return self.find_section(space, addr).lookup(addr)

    def attach(self, space, addr, obj):
        self.find_section(space, addr).attach(addr, obj)

    def find_function(self, addr):
        try:
            objects = self.lookup(self.isa.codemem, addr)
        except IndexError:
            return None
        for obj in objects:
            if isinstance(obj, Function):
                return obj
        obj = Function('func_{:x}'.format(addr), self, addr)
        self.attach(self.isa.codemem, addr, obj)
        return obj

from envy.deco.func import Function
