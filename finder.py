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
import logging
import os
import os.path as osp
import re
import sys
from xdg.BaseDirectory import xdg_cache_home

import mcworldlib as mc


if __name__ == '__main__':
    myname = osp.basename(osp.splitext(__file__)[0])
else:
    myname = __name__

log = logging.getLogger(myname)


def setup_logging(level):
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


def parse_args(args=None):
    parser = mc.basic_parser(description=__doc__)

    parser.add_argument('-e',  '--entity',    help="Entity ID to search")
    parser.add_argument('-b',  '--block',     help="Block ID to search")
    parser.add_argument('-tn', '--tag-name',  help="NBT tag name to search")
    parser.add_argument('-tv', '--tag-value', help="NBT tag value to search")
    parser.add_argument('-tp', '--tag-path',  help="NBT tag path to search")
    parser.add_argument('-tt', '--tag-type',  help="NBT tag type to search")
    parser.add_argument('-te', '--tag-exclude', nargs='+',
                        help="NBT tag key to prune from search, such as:"
                             " TileTicks LiquidTicks Lights LiquidsToBeTicked ToBeTicked")

    return parser.parse_args(args)


def chunkcoords(world, chunk):
    cx, cz = chunk.chunkPosition
    region = world.worldFolder.getRegionForChunk(cx, cz)
    return region.regionCoords, (cx & 0x1F, cz & 0x1F), (cx, cz)


def logcoords(world, chunk, coords=None):
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


def nbt_walk(tag, path=None, prune=()):
    """Yield 3-tuples of dot-separated tag paths, tag leaf names and corresponding values"""
    if isinstance(tag, list):
        for i, item in enumerate(tag):
            yield from nbt_walk(item, f"{path}.{i}", prune)
    elif isinstance(tag, dict):
        for k, item in tag.items():
            if k in prune:
                continue
            yield from nbt_walk(item, (f"{path}.{k}" if path else k), prune)
    elif isinstance(tag, (str, int, float)):
        yield path, path.split('.')[-1], tag
    elif not isinstance(tag, (mc.nbt.ByteArray, mc.nbt.IntArray, mc.nbt.LongArray)):
        log.warning("Unexpected tag type in %s=%r: %s", path, tag, type(tag))


def match_tag(value, search, exact=False, cls=False) -> bool:
    """
    :param value: What I'm looking for, None to abort
    :param search: Some data from NBT. Might be path, key, or value
    :param exact:
    :param cls: perform a class (type) match
    :return:
    """
    if value is None:  # Nothing to match
        return True
    if cls:
        return value == search.__class__.__name__
    # search might be path (str), key (str) or value (tag)
    if isinstance(search, str):
        if exact:
            return value.lower() == search.lower()
        return bool(re.search(value, search, re.IGNORECASE))
    # search will always be a tag, so value must be converted to numeric
    # Not sure if Compound and List accepts SNBT, so keeping this generic
    return search.__class__(value) == search  # ints and floats


def main(argv=None):
    args = parse_args(argv)

    # setup_logging(args.loglevel)
    logging.basicConfig(level=args.loglevel, format='%(levelname)s: %(message)s')
    log.debug(args)

    world = mc.load(args.world)

    for name, arg, func in (
            ('entity', args.entity, find_entity),
            ('block',  args.block,  find_block),
    ):
        if arg is None:
            continue
        log.info("Searching for %s '%s' on the entire world", name, arg)
        eid = ename = arg.lower()
        if ':' not in eid:
            eid = 'minecraft:' + eid
        count = 0
        for chunk in world.get_chunks(progress=(args.loglevel >= logging.INFO)):
            ename, ecount = func(chunk, eid, ename)
            count += ecount
        print(f"{ename} [{eid}]: {count}")
        return

    if (
            args.tag_value is not None or
            args.tag_name  is not None or
            args.tag_type  is not None or
            args.tag_path  is not None
    ):
        find_nbt(world, args)
        return


def find_nbt(world: mc.World, args):
    def match(nbt):
        if args.tag_exclude:
            prune = set(args.tag_exclude)
        else:
            prune = ()
        for path, name, value in nbt_walk(nbt, prune=prune):
            if (
                    match_tag(args.tag_path,  path) and
                    match_tag(args.tag_name,  name) and
                    match_tag(args.tag_type,  value, cls=True) and
                    match_tag(args.tag_value, value)
            ):
                yield path, value

    for tag_path, tag_value in match(world.level):
        print("%s: %r" % (tag_path, tag_value))

    for dimension, category, chunk in world.get_all_chunks(progress=(args.loglevel == logging.INFO)):
        for tag_path, tag_value in match(chunk):
            print("%s %s R%s, C%s %s: %r" % (
                  dimension.name.title(), category.title(),
                  chunk.region.pos, chunk.pos, tag_path, tag_value))


def find_entity(chunk, eid, ename):
    count = 0
    for entity in chunk.entities:
        log.debug(entity)
        if not (eid == entity["id"] or ename == entity.name.lower()):
            continue
        ename = entity.name
        count += 1
        # log.info(logcoords(world, chunk, (_.value for _ in entity["Pos"])))
        log.info("R%s, C%s: %s", chunk.region.pos, chunk.pos, entity)
        # log.info("[%r] %s", chunk, entity)
        log.debug("%r", entity)  # NBT
    return ename, count


def find_block(chunk, bid, bname):
    count = 0
    for section in chunk.root.get('Sections', []):
        for p, palette in enumerate(section.get('Palette', [])):
            blockid = str(palette['Name'])
            if blockid == bid or bname in blockid:
                log.info("R(%2d, %2d), C(%2d, %2d), SY %d, P %2d: %s",
                         *chunk.region.pos,
                         *chunk.pos,
                         section['Y'], p, palette)
                count += 1  # FIXME: not actual block count!
    for t, tile in enumerate(chunk.root.get('TileEntities', [])):
        blockid = str(tile['id'])
        if blockid == bid or bname in blockid:
            log.info("R(%2d, %2d), C(%2d, %2d), TE %d: %s",
                     *chunk.region.pos,
                     *chunk.pos,
                     t, tile)
            count += 1  # FIXME: not actual block count!
    # cx, cz = chunk.chunkPosition
    # for xc, zc, y in zip(*numpy.where(chunk.Blocks == block.ID)):
    # blockcount += 1
    # x, z = xc + 16 * cx, zc + 16 * cz
    # log.info(logcoords(world, chunk, (x, y, z)))
    return bname, count


if __name__ == "__main__":
    try:
        sys.exit(main())
    except mc.MCError as error:
        log.error(error)
    except Exception as error:
        log.critical(error, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
