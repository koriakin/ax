class Object:
    def __init__(self, world):
        self.dirty = False
        self.inproc = False
        self.world = world
        self.deps = set()
        self.prevsig = None

    def process(self):
        pass

    def try_process(self):
        if self.dirty and not self.inproc:
            self.world.dirties.remove(self)
            self.dirty = False
            self.inproc = True
            self.process()
            self.inproc = False

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.world.dirties.add(self)

    def update_sig(self, sig):
        if self.prevsig != sig:
            for dep in self.deps:
                dep.mark_dirty()
        self.prevsig = sig
