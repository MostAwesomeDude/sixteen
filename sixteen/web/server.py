import json
from twisted.internet import protocol, reactor
from txws import WebSocketFactory
from sixteen.dcpu16 import DCPU16
from sixteen.output import OutputCPU
from sixteen.input import InputCPU
from sixteen.halting import LoopDetecting
from sixteen.memorymap import MemoryMap
from sixteen.characters import characters


class WebCPU(DCPU16, OutputCPU, InputCPU, LoopDetecting):
    def __init__(self, protocol):
        "Given a twisted protocol, initialize a WebCPU."
        self.protocol = protocol
        # copy my own `registers` dict.
        self.registers = self._registers.copy()
        # this gets turned into True if we suspect the program is looping.
        self.stop = False
        self.RAM = MemoryMap(self.cells, [
            (self.vram, self.change_letter),
            (self.background, self.change_background),
            (self.chars, self.change_character),
        ])
        # read the default characters to the RAM
        self.RAM[self.chars[0]:] = characters

        # And set the input pointer.
        self.RAM[0x9010] = 0x9000

    def change_character(self, index, value):
        # return the whole character because half-characters are a pain.
        # if it's an even index, it's the first of a pair.
        if index % 2 == 0:
            top = value
            bottom = self.RAM[index + 1]
            location = (index - self.chars[0]) // 2
        else:
            top = self.RAM[index - 1]
            bottom = value
            location = ((index - 1) - self.chars[0]) // 2
        # use sixteen.output.OutputCPU.character to get a list of rows.
        rows = self.character(top, bottom)
        # and set the chars_changed to the rows
        self.protocol.chars_changed[location] = rows
        # ugly hack: make the frontend refresh the ones that have been changed
        # (might be too slow)
        for addr in (a for a in xrange(*self.vram) if (
            self.RAM[a] & 0b0000000001111111) == location):
             self.change_letter(addr, self.RAM[addr])

    def change_background(self, index, value):
        # format the background color as an html/css hex color.
        background = "#%02x%02x%02x" % self.color(value & 0x0f)
        self.protocol.change_background = background

    def change_letter(self, index, value):
        "This is called whenever a cell of vram is changed."
        # get the data from sixteen.output.OutputCPU.letter
        x, y, foreground, background, blink, char = self.letter(index, value)
        self.protocol.letters_changed[(x, y)] = {
            "x": x, "y": y, "char": char, "blink": blink,
            # format the background and foreground tuples as html/css colors.
            "foreground": "#%02x%02x%02x" % foreground,
            "background": "#%02x%02x%02x" % background,
        }


class DCPU16Protocol(protocol.Protocol):
    cycle_counter = 0

    def __init__(self, code):
        # and the letters_changed list
        self.letters_changed = {}
        self.chars_changed = {}
        self.change_background = None
        self.errors = []
        # intialize the cpu
        self.cpu = WebCPU(self)
        # read the code from the factory to the RAM
        self.cpu.RAM[:len(code)] = code

    def dump_cpu(self, op, args):
        if self.cpu.cycles >= self.cycle_counter:
            self.cycle_counter += 100
            print "---- " * 11
            print "A    B    C    I    J    X    Y    Z    SP   PC   O"
            print "---- " * 11
        rs = self.cpu.registers
        rs["dis"] = str("%s %s" % (op, args))
        s = ("%(A)04x %(B)04x %(C)04x %(I)04x %(J)04x %(X)04x %(Y)04x %(Z)04x"
                " %(SP)04x %(PC)04x %(O)04x: %(dis)s") % rs
        print s

    def dataReceived(self, data):
        # get the keypresses and the number of cycles from the frontend
        keypresses, count = json.loads(data)
        for k in keypresses:
            self.cpu.keyboard_input(ord(k))
        try:
            # cycle as many times as we're supposed to,
            for _ in xrange(count):
                # ... checking for infinite loops.
                if not self.cpu.is_looping():
                    op, args = self.cpu.cycle()
                    self.dump_cpu(op, args)
                else:
                    break
        # if we get any errors, let the frontend know.
        except Exception as e:
            self.errors.append(str(e))
        # and then pass everything to the frontend.
        self.write_changes()

    def write_changes(self):
        "Write the changes to the websockets client and reset."
        changes = {
            # None if there's no new background color, otherwise a color.
            "background": self.change_background,
            # the cells that have been changed since last time
            "cells": self.letters_changed.values(),
            # the characters (fonts) that have been changed
            "characters": self.chars_changed,
            # any errors we've encountered
            "errors": self.errors,
            # whether the frontend should stop.
            "halt": self.cpu.stop,
        }
        # reset everything
        self.transport.write(json.dumps(changes))
        self.letters_changed = {}
        self.chars_changed = {}
        self.change_background = None
        self.errors = []
