#!/usr/bin/env python3
#
#    Copyright (C) 2018 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. See <http://www.gnu.org/licenses/gpl.html>

"""
Find and list things in a Minecraft world
"""

import sys
import os
import os.path as osp
import logging
from xdg.BaseDirectory import xdg_cache_home

import numpy

import mcworldlib as mc


if __name__ == '__main__':
    myname = osp.basename(osp.splitext(__file__)[0])
else:
    myname = __name__

log = logging.getLogger(myname)


def setuplogging(level):
    # Console output
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

    # File output
    logger = logging.getLogger()  # root logger, so it also applies to pymclevel
    logger.setLevel(logging.DEBUG)  # set to minimum so it doesn't discard file output
    try:
        logdir = osp.join(xdg_cache_home, 'minecraft')
        if not osp.exists(logdir):
            os.makedirs(logdir)
        fh = logging.FileHandler(osp.join(logdir, "%s.log" % myname))
        fh.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s'))
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
    except IOError as e:  # Probably access denied
        logger.warning("%s\nLogging will not work.", e)


def parseargs(args=None):
    parser = mc.basic_parser(description=__doc__)

    parser.add_argument('--entity', '-e', help="Entity ID to search;")
    parser.add_argument('--block',  '-b', help="Block ID to search;")

    return parser.parse_args(args)


def chunkcoords(world, chunk):
    cx, cz = chunk.chunkPosition
    region = world.worldFolder.getRegionForChunk(cx, cz)
    return region.regionCoords, (cx & 0x1F, cz & 0x1F), (cx, cz)


def logcoords(world, chunk, coords=()):
    if coords:
        x, y, z = coords
        pos = "\tPosition [%5d, %5d, %5d]" % (x, z, y)
    else:
        pos = ""

    (rx, rz), (cxr, czr), (cx, cz) = chunkcoords(world, chunk)
    return ("Region (%3d, %3d)\t"
            "Chunk [%2d, %2d] / (%4d, %4d)"
            "%s"
            % (rx, rz, cxr, czr, cx, cz, pos))




def main(argv=None):
    args = parseargs(argv)

    #setuplogging(args.loglevel)
    logging.basicConfig(level=args.loglevel, format='%(levelname)s: %(message)s')
    log.debug(args)

    try:
        world = mc.load(args.world)

        entitycount = 0
        blockcount  = 0

        if args.entity is not None:
            log.info("Searching for entity '%s' on the entire world", args.entity)
            eid = ename = args.entity.lower()
            if ':' not in eid:
                eid = 'minecraft:' + eid

        if args.block is not None:
            log.warning("Block finding does not work in Minecraft 1.13 onwards")
            args.block = None
            block = None
            #block = world.materials[args.block]
            #log.info("Searching for block '%s' on the entire world", block.name)

        for chunk in world.get_chunks(progress=(args.loglevel==logging.INFO)):
            if args.entity is not None:
                for entity in chunk.entities:
                    log.debug(entity)
                    if eid == entity["id"] or ename == entity.name.lower():
                        eid = entity["id"]
                        ename = entity.name
                        entitycount += 1
                        #log.info(logcoords(world, chunk, (_.value for _ in entity["Pos"])))
                        log.info("%s [%r]", entity, chunk)
                        log.debug("%r", entity)  # NBT

            if args.block is not None:
                cx, cz = chunk.chunkPosition
                for xc, zc, y in zip(*numpy.where(chunk.Blocks == block.ID)):
                    blockcount += 1
                    x, z = xc + 16 * cx, zc + 16 * cz
                    log.info(logcoords(world, chunk, (x, y, z)))

        if args.entity is not None:
            log.info("%s [%s]: %d", ename, eid, entitycount)

        if args.block is not None:
            log.info("%s: %d", block.name, blockcount)


    except mc.MCError as e:
        log.error(e)
        return




if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
