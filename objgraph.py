#!/usr/bin/env python

import sys
import os
import subprocess
import re
import itertools
import json


TYPES = {
    't': 'text',
    'b': 'bss',
    'd': 'data'
}

# Get symbol sizes from nm
def getsizes(objs):
    for obj in objs:
        file = os.path.basename(obj)

        raw = subprocess.check_output(['nm', '-S', obj])

        for line in raw.splitlines():
            if line.endswith(':'):
                file = line[:-1]
                continue

            cols = line.split()
            if len(cols) == 4:
                size = int(cols[1], 16)
                type = cols[2].lower()
                sym  = cols[3]

                if type in TYPES:
                    yield file, sym, TYPES[type], size

# Get symbol dependencies from objdump disas
def getasms(objs):
    for obj in objs:
        file = os.path.basename(obj)
        sym = None
        off = 0
        asm = []

        raw = subprocess.check_output(['objdump', '-d', obj])

        for line in itertools.chain(raw.splitlines(), ['']):
            m = re.match('^([^ ]+):', line)
            if m:
                file = m.group(1)
                continue

            m = re.match('^([^ ]+) <([^ ]+)>:', line)
            if m:
                off = int(m.group(1), 16)
                sym = m.group(2)
                continue

            m = re.match('^ +[^ ]+:(.*)$', line)
            if m:
                asm.append(m.group(1).strip())
                continue

            if sym is not None:
                yield file, sym, off, asm
                sym = None
                off = 0
                asm = []

# Find all relocatable symbols
def getrelocs(objs):
    for obj in objs:
        file = os.path.basename(obj)

        raw = subprocess.check_output(['objdump', '-r', obj])

        for line in raw.splitlines():
            m = re.match('^([^ ]+):', line)
            if m:
                file = m.group(1)
                continue

            m = re.match('^([0-9a-fA-F]+) +[^ ]+ +([^+-]+)', line)
            if m:
                off = int(m.group(1), 16)
                reloc = m.group(2)
                yield file, off, reloc


def main(*objs):
    assert len(objs) > 0, "Need at least one obj file"

    # Get symbol info
    symbols = {}

    for file, sym, type, size in getsizes(objs):
        assert sym not in symbols
        symbols[sym] = {
            'file': file,
            'sym': sym,
            'type': type,
            'size': size
        }

    for file, sym, off, asm in getasms(objs):
        if sym in symbols:
            deps = set()
            for line in asm:
                m = re.search('<([^ +<>]+)[^<>]*>', line)
                if m and m.group(1) != sym:
                    deps.add(m.group(1))

            symbols[sym]['off']  = off
            symbols[sym]['asm']  = asm
            symbols[sym]['deps'] = deps

    for file, off, reloc in getrelocs(objs):
        for sym in symbols.itervalues():
            if sym['file'] == file:
                if ('off' in sym and off >= sym['off'] and
                        off < sym['off'] + sym['size']):
                    sym['deps'].add(reloc)

    # Generate graph data
    nodes = []
    edges = []

    for sym in symbols.itervalues():
        nodes.append({
            'label': sym['sym'],
            'id': sym['sym'],
            'group': sym['file'],
            'value': sym['size']
        })

        sym['deps'] = list(sym.get('deps', []))
        for dep in sym['deps']:
            edges.append({
                'from': sym['sym'],
                'to': dep
            })

    data = {
        'nodes': nodes,
        'edges': edges,
        'symbols': symbols
    }

    with open('objgraph.data.json', 'wb') as file:
        json.dump(data, file)


if __name__ == '__main__':
    main(*sys.argv[1:])

