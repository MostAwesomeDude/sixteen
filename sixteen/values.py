# -*- coding: utf-8 -*-


class Box(object):
    """A base class that defines the Box interface with some sane defaults.
    Everything that will be used as a box *needs* these four methods: "get",
    "set", "after", and, of course, "__init__".

    Each Box's __init__ takes two arguments -- "self", of course, and "cpu",
    which is probably an instance of sixteen.dcpu16.DCPU16. The default thing
    to do is to save "key"and "container" attributes, which are used to look up
    or set things in "get" and "set".

    This class (it *is* a base class) doesn't define "__init__", so you'll need
    to subclass and define it yourself.
    """
    def get(self):
        """'get' is called to retrieve the contained value. Nothing
        destructive should happen here. Everything that gets the next word etc
        should happen in __init__.
        """
        return self.container[self.key]

    def set(self, value):
        "This is what gets called when something tries to change this value."
        self.container[self.key] = value

    def after(self):
        """Well-behaved CPUs will call this after everything, for cleaning up,
        postincrement and decrement, or anything else really.
        """
        pass


class Register(object):
    """This class abstracts away much of the work for registers. It isn't a Box
    subclass itself, but it defines three methods that construct and return
    such classes. 
    """
    def __init__(self, name):
        "Given the name of this register, initialize a Register."
        self.name = name

    def as_value(self):
        "Return a Box that gets and sets the value of this register."
        def value_init(s, cpu):
            s.container = cpu.registers

        value = type(self.name, (Box,), {"__init__": value_init})
        value.key = self.name
        return value

    def as_pointer(self):
        "Return a Box that gets and sets the value this register points to."
        def pointer_init(s, cpu):
            s.container = cpu.RAM
            s.key = cpu.registers[self.name]

        return type("[%s]" % self.name, (Box,), {"__init__": pointer_init})

    def and_next_word(self):
        """Return a box that gets and sets the register the sum of this
        register and the next word points to.
        """
        def r_init(s, cpu):
            s.container = cpu.RAM
            s.key = cpu.registers[self.name] + cpu.get_next()
            # handle overflow
            if s.key >= len(cpu.RAM) - 1:
                s.key -= (cput.RAM - 1)

        return type("[%s + next word]" % self.name, (Box,),
                {"__init__": r_init})


class NextWord(Box):
    "0x1f: next word (literal)"
    def __init__(self, cpu):
        self.value = cpu.get_next()
    
    def get(self):
        return self.value

    def set(self, value):
        """"So say the docs:
        'If any instruction tries to assign a literal value, the assignment fails
        silently. Other than that, the instruction behaves as normal.'
        """
        pass
    

class NextWordAsPointer(Box):
    "0x1e: [next word]"
    def __init__(self, cpu):
        "Get and set to and from the address stored in the next word."
        self.container = cpu.RAM
        self.key = cpu.get_next()


def ShortLiteral(n):
    "0x20-0x3f: literal value 0x00-0x1f (literal)"
    class LiteralN(Box):
        def __init__(self, cpu):
            self.value = n
        
        def get(self):
            return self.value

        def set(self, value):
            """"So say the docs:
            'If any instruction tries to assign a literal value, the assignment fails
            silently. Other than that, the instruction behaves as normal.'
            """
            pass

    return LiteralN