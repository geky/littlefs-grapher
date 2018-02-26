#!/usr/bin/env python

import sys
import os

def main(blocks, image, block_size=512):
    with open(image, 'wb') as disk:
        for block in os.listdir(blocks):
            path = os.path.join(blocks, block)
            if not os.path.isfile(path):
                continue 

            try:
                block = int(block, 16)
            except ValueError:
                continue

            assert os.path.getsize(path) <= block_size, (
                "Block %x does not match block size %d, is %d bytes large" %
                (block, block_size, os.path.getsize(path)))

            disk.seek(block * block_size)

            with open(path, 'rb') as file:
                disk.write(file.read(block_size).ljust(block_size, '\0'))

if __name__ == '__main__':
    main(*sys.argv[1:])
