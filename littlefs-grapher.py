#!/usr/bin/env python

import sys
import struct
import binascii
import json
import itertools

DISK = None
BLOCK_SIZE = None
BLOCK_COUNT = None

# Get a block as string from disk
def get_block(block):
    DISK.seek(block*BLOCK_SIZE)
    return DISK.read(BLOCK_SIZE)

# load a dir block, pairs is tuple of two blocks
def get_dir(pair):
    pair = list(pair)
    dats = []
    refs = []
    reason = 'old'

    for i, _ in enumerate(pair):
        dats.append(get_block(pair[i]))
        ref, size = struct.unpack('<II', dats[i][:8])
        size = 0x7fffffff & size
        if size > len(dats[0]):
            refs.append(None)
            reason = 'bad size'
            continue

        crc = ~binascii.crc32(dats[i][:size])
        if crc != 0:
            refs.append(None)
            reason = 'bad crc'
            continue

        refs.append(ref)

    dat, block, _ = max(zip(dats, pair, refs), key=lambda p: p[2])
    return dat, block, reason

def popc(x):
    return bin(x).count('1')

def ctz(x):
    b = bin(x)
    return len(b) - len(b.rstrip('0'))

def ctz_index(size):
    size -= 1
    b = BLOCK_SIZE - 2*4
    i = size // b
    if i == 0:
        return 0, size

    i = (size - 4*(popc(i-1)+2)) // b;
    off = size - b*i - 4*popc(i);
    return i, off

def iter_file(path, head, size):
    inithead, depth = head, 0
    i, _ = ctz_index(size)
    while i > 0:
        dat = get_block(head)
        next, = struct.unpack('<I', dat[0:4])
        yield 'filex', 'list', path, (head, next, inithead, depth)

        for j in range(1, ctz(i)+1):
            farnext, = struct.unpack('<I', dat[4*j:4*j+4])
            yield 'filexx', 'list', path, (head, farnext)

        head = next
        depth += 1
        i -= 1

def iter_dir(path, dat):
    size, = struct.unpack('<I', dat[4:8])
    tail = set(struct.unpack('<II', dat[8:16]))
    if size & 0x80000000:
        yield 'dir', 'tail', path, tail
    else:
        if tail != {0xffffffff}:
            yield 'dir', 'tailx', None, tail

    off = 16
    size = (0x7fffffff & size) - 4
    while off < size:
        type, elen, alen, nlen = struct.unpack('<BBBB', dat[off:off+4])
        type = 0x7f & type
        if type == 0x11:
            assert elen == 8, "elen => %d?" % elen
            assert alen == 0, "alen => %d?" % alen
            head, nsize = struct.unpack('<II', dat[off+4:off+12])
            npath = dat[off+12:off+12+nlen]
            yield 'file', 'child', npath, head
            for e in iter_file(npath, head, nsize):
                yield e
            
        elif type == 0x22:
            assert elen == 8, "elen => %d?" % elen
            assert alen == 0, "alen => %d?" % alen
            child = struct.unpack('<II', dat[off+4:off+12])
            npath = dat[off+12:off+12+nlen]
            yield 'dir', 'child', npath, set(child)

        elif type == 0x2e:
            assert elen == 20, "elen => %d?" % elen
            assert alen == 0,  "alen => %d?" % alen
            child = struct.unpack('<II', dat[off+4:off+12])
            yield 'dir', 'tail', '/', set(child)
            
        else:
            assert False, "Unknown type %#x" % type

        off += elen + alen + nlen + 4
            
            

def get_nodes_and_edges():
    nodes = {}
    edges = []
    seenblocks = set()

    dirs = [('/', {0, 1})]
    while dirs:
        path, blocks = dirs.pop()

        if blocks == {0xffffffff}:
            continue

        dat, block, reason = get_dir(blocks)
        seen = block in nodes

        for b in blocks:
            if b not in nodes:
                nodes[b] = {
                    'block': b,
                    'type': 'dirx',
                    'path': None,
                    'reason': None,
                }

            nodes[b]['path'] = nodes[b]['path'] or path
            nodes[b]['type'] = 'dir' if block == b else nodes[b]['type']
            nodes[b]['reason'] = reason if block != b else nodes[b].get('reason', None)

        if not seen:
            edges.append({
                'type': 'pair',
                'edge': tuple(blocks)
            })

            for xoff, es in enumerate(iter_dir(path, dat)):
                ntype, etype, npath, edge = es
                if ntype == 'dir':
                    dirs.append((npath, edge))

                    for dest in edge:
                        edges.append({
                            'type': etype,
                            'edge': (block, dest)
                        })
                elif ntype == 'file':
#                    assert (edge not in nodes or
#                            nodes[edge]['type'].startswith('file')), (
#                            "block %d is not a file!" % edge)
                    if edge not in nodes:
                        nodes[edge] = {
                            'block': edge,
                            'type': 'file',
                            'path': npath,
                        }
                    edges.append({
                        'type': etype,
                        'edge': (block, edge)
                    })
                elif ntype == 'filex':
#                    assert (edge[1] not in nodes or
#                            nodes[edge[1]]['type'].startswith('file')), (
#                            "block %d is not a file!" % edge[1])
                    if edge[1] not in nodes:
                        nodes[edge[1]] = {
                            'block': edge[1],
                            'type': 'file',
                            'path': npath,
                            'head': edge[2],
                            'depth': edge[3]
                        }
                    edges.append({
                        'type': etype,
                        'edge': edge[:2]
                    })
                elif ntype == 'filexx':
                    edges.append({
                        'type': etype,
                        'edge': edge
                    })
                else:
                    assert False, 'Unknown type %r' % ntype

    return nodes.values(), edges

def main(disk, block_size=512):
    global DISK
    global BLOCK_SIZE
    global BLOCK_COUNT

    with open(disk, 'rb') as disk:
        DISK = disk
        BLOCK_SIZE = block_size
        disk.seek(0, 2)
        BLOCK_COUNT = disk.tell() / BLOCK_SIZE

        nodes, edges = get_nodes_and_edges()
        visnodes, visedges, visblocks = [], [], {}

        blocks = {node['block']: node for node in nodes}
        parents = {}
        preds = {}
        invalids = set()

        for edge in edges:
            if edge['type'] == 'child':
                parents[edge['edge'][1]] = edge['edge'][0]
            elif edge['type'] == 'tail' or edge['type'] == 'tailx':
                preds[edge['edge'][1]] = edge['edge'][0]

        def realparent(p, default=None):
            while p not in parents and p in preds:
                p = preds[p]

            return parents[p] if p in parents else default

        def tailcount(p):
            count = 0
            while p in preds:
                p = preds[p]
                count += 1
            return count

        maxy = 0
        for node in nodes:
            p, y = node['block'], 0
            orphan = True
            for i in xrange(10000):
                if p in parents:
                    p = parents[p]
                    y += 1
                    orphan = False
                elif p in preds:
                    p = preds[p]
                    orphan = False
                else:
                    break
            
            node['y'] = y
            maxy = max(y, maxy)

        for y in reversed(range(maxy)):
            for node in nodes:
                if node['y'] == y:
                    children = [n for n in nodes
                        if realparent(n['block'], None) == node['block']]
                    node['width'] = max(1,
                        sum(c.get('width', 1) for c in children)-1)

        for node in itertools.chain([{}], [
                node for y in range(maxy)
                for node in nodes
                if node['y'] == y]):
            children = [n for n in nodes
                if realparent(n['block'], None) == node.get('block', None)]

            def key(c):
                return (0 if c['type'].startswith('dir') else 1,
                        tailcount(c['block']), c['path'],
                        1 if c['type'] == 'dirx' else 0)

            total = node.get('x', 0)
            ptotal = total
            for child in sorted(children, key=key):
                if child['type'] == 'dirx':
                    child['x'] = ptotal + 1
                else:
                    child['x'] = total
                ptotal = total
                total += child.get('width', 1)

        for node in nodes:
            if node['type'] == 'file' and node['block'] not in parents:
                head = blocks[node['head']]
                node['x'] = head['x']
                node['y'] = head['y'] + 0.75*(node['depth'] + 1)

        for node in nodes:
            if node['block'] < BLOCK_COUNT:
                info = '%s %s\nblock %x\n%s\n' % (
                    node['type'], node['path'], node['block'],
                    node['reason'] if node['type'] == 'dirx' else '')

                visnodes.append({
                    'label': info,
                    'id': node['block'],
                    'group': node['path'],
                    'x': 200*node['y'], # + (0 if node['type'] == 'dirx' else 1),
                    'y': 100*node['x'],
                    'fixed': True, #node['type'] != 'filex'
                })

                visblocks[node['block']] = {
                    'info': info,
                    'raw': get_block(node['block']).encode('base64')
                }

        for edge in edges:
            if (edge['edge'][1] >= BLOCK_COUNT and
                edge['edge'][1] not in invalids):
                visnodes.append({
                    'label': 'invalid\nblock %x\n\n' % edge['edge'][1],
                    'id': edge['edge'][1],
                    'group': 'invalid',
                })
                invalids.add(edge['edge'][1])

            visedges.append({
                'arrows': 'to' if edge['type'] != 'pair' else '',
                'dashes': edge['type'] in ('pair', 'tailx'),
                #'physics': edge['type'] != 'tailx',
                'title': edge['type'],
                'from': edge['edge'][0],
                'to': edge['edge'][1],
                'smooth': False if edge['type'] in ('child', 'pair') else {
                    'type': 'curvedCW',
                    'roundness': 0.2,
                } if edge['type'] == 'list' else True
            })

        vis = {'nodes': visnodes, 'edges': visedges, 'blocks': visblocks}
        sys.stdout.write(json.dumps(vis))
        sys.stdout.write('\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
