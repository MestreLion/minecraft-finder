#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

import pymctoolslib as mc

if __name__ == '__main__':
    myname = osp.basename(osp.splitext(__file__)[0])
else:
    myname = __name__

log = logging.getLogger(myname)


def setuplogging(level):
    # Console output
    for logger, lvl in [(log, level),
                        # pymclevel is too verbose
                        (logging.getLogger("pymclevel"), logging.WARNING)]:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        sh.setLevel(lvl)
        logger.addHandler(sh)

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
        logger.warn("%s\nLogging will not work.", e)


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

    setuplogging(args.loglevel)
    log.debug(args)

    try:
        world, _ = mc.load_player_dimension(args.world, args.player)

        if args.entity is not None:
            log.info("Searching for '%s' on the entire world", args.entity)
            entityid = args.entity
            entitycount = 0
            for chunk in mc.iter_chunks(world,  progress=args.loglevel==logging.INFO):
                for entity in chunk.Entities:
                    entity = mc.Entity(entity)
                    log.debug(entity)
                    if args.entity.lower() == entity.name.lower():   # entity["id"].lower():
                        entityid = entity["id"]
                        entitycount += 1
                        #log.info(logcoords(world, chunk, (_.value for _ in entity["Pos"])))
                        log.info(entity)
                        if entityid == "Villager":
                            villager = mc.Villager(entity)
                            log.info(villager)
            log.info("%s: %d", entityid, entitycount)

        if args.block is not None:
            blockcount = 0
            blockname = world.materials[args.block].name
            for chunk in sorted(world.getChunks(), key=lambda chunk: chunk.chunkPosition):
                cx, cz = chunk.chunkPosition
                for xc, zc, y in zip(*numpy.where(chunk.Blocks == args.block)):
                    blockcount += 1
                    x, z = xc + 16 * cx, zc + 16 * cz
                    log.debug(logcoords(world, chunk, (x, y, z)))
            log.info("%s: %d", blockname, blockcount)


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
