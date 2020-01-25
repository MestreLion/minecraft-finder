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

#import numpy
#import tqdm

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
    parser.add_argument('--tag-name', '-tn', help="NBT tag name to search;")
    parser.add_argument('--tag-value', '-tv', help="NBT tag value to search;")
    parser.add_argument('--tag-path', '-tp', help="NBT tag path to search;")

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


def nbt_walk(tag, path=None):
    if isinstance(tag, list):
        for i, item in enumerate(tag):
            yield from nbt_walk(item, f"{path}.{i}")
    elif isinstance(tag, dict):
        for k, item in tag.items():
            if not k: k = "''"
            yield from nbt_walk(item, f"{path}.{k}" if path else k)
    elif isinstance(tag, (str, int, float)):
        yield path, tag


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
            bid = bname = args.block.lower()  # @UnusedVariable
            if ':' not in bid:
                bid = 'minecraft:' + bid
            log.info("Searching for block '%s' on the entire world", bid)
            #block = world.materials[args.block]

        for chunk in world.get_chunks(progress=(args.loglevel > logging.INFO)):
            if (args.tag_value is not None or
                args.tag_name  is not None or
                args.tag_path  is not None
            ):
                for tag_path, tag in nbt_walk(chunk):
                    if (
                        (args.tag_value is not None and args.tag_value in str(tag)) or
                        (args.tag_name  is not None and tag_path.lower().split('.')[-1] ==  args.tag_name.lower()) or
                        (args.tag_path  is not None and tag_path.lower().startswith(args.tag_path.lower()))
                    ):
                        log.info("R%s,C%s %s: %r", chunk.region.pos, chunk.pos, tag_path, tag)

            if args.entity is not None:
                for entity in chunk.entities:
                    log.debug(entity)
                    if eid == entity["id"] or ename == entity.name.lower():
                        eid = entity["id"]
                        ename = entity.name
                        entitycount += 1
                        #log.info(logcoords(world, chunk, (_.value for _ in entity["Pos"])))
                        log.info("R%s,C%s: %s", chunk.region.pos, chunk.pos, entity)
                        #log.info("[%r] %s", chunk, entity)
                        log.debug("%r", entity)  # NBT

            if args.block is not None:
                for section in chunk.root.get('Sections', []):
                    for p, palette in enumerate(section.get('Palette', [])):
                        if palette['Name'] == bid:
                            log.info("R(%2d, %2d), C(%2d, %2d), SY %d, P %2d: %s",
                                     *chunk.region.pos,
                                     *chunk.pos,
                                     section['Y'], p, palette)
                            blockcount += 1  #FIXME: not actual block count!
                #cx, cz = chunk.chunkPosition
                #for xc, zc, y in zip(*numpy.where(chunk.Blocks == block.ID)):
                    #blockcount += 1
                    #x, z = xc + 16 * cx, zc + 16 * cz
                    #log.info(logcoords(world, chunk, (x, y, z)))

        if args.entity is not None:
            print(f"{ename} [{eid}]: {entitycount}")

        if args.block is not None:
            print(f"{bname} [{bid}]: {blockcount}")


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
