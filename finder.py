#!/usr/bin/env python

import sys
import os
import os.path as osp
import argparse
import logging
from xdg.BaseDirectory import xdg_cache_home
import collections

import numpy

import pymclevel

if __name__ == '__main__':
    myname = osp.basename(osp.splitext(__file__)[0])
else:
    myname = __name__

log = logging.getLogger(myname)


class PyMCLevelError(Exception):
    pass

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
    parser = argparse.ArgumentParser(
        description="Find and list things in a Minecraft world",)

    parser.add_argument('--quiet', '-q', dest='loglevel',
                        const=logging.WARNING, default=logging.INFO,
                        action="store_const",
                        help="Suppress informative messages.")

    parser.add_argument('--verbose', '-v', dest='loglevel',
                        const=logging.DEBUG,
                        action="store_const",
                        help="Verbose mode, output extra info.")

    parser.add_argument('--world', '-w', default="newworld",
                        help="Minecraft world, either its 'level.dat' file"
                            " or a name under '~/.minecraft/saves' folder."
                            " [Default: %(default)s]")

    parser.add_argument('--player', '-p', default="Player",
                        help="Player name."
                            " [Default: %(default)s]")

    return parser.parse_args(args)


def load_world(name):
    if isinstance(name, pymclevel.MCLevel):
        return name

    try:
        if osp.isfile(name):
            return pymclevel.fromFile(name)
        else:
            return pymclevel.loadWorld(name)
    except IOError as e:
        raise PyMCLevelError(e)
    except pymclevel.mclevel.LoadingError:
        raise PyMCLevelError("Not a valid Minecraft world: '%s'" % name)


def get_player(world, playername=None):
    if playername is None:
        playername = "Player"
    try:
        return world.getPlayerTag(playername)
    except pymclevel.PlayerNotFound:
        raise PyMCLevelError("Player not found in world '%s': %s" % (world.LevelName, playername))


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

def itemtype(entity):
    from pymclevel.items import items as ItemTypes
    return ItemTypes.findItem(entity["id"].value,
                              entity["Damage"].value)

def itemdesc(entity):
    return "%2d %s" % (entity["Count"].value,
                       itemtype(entity).name)


class NbtObject(object):
    '''High-level wrapper for NBT Compound tags'''

    def __init__(self, nbt):
        self._nbt = nbt

    def _create_nbt_attrs(self, *attrs):
        assert self._nbt.tagID == pymclevel.nbt.TAG_COMPOUND, \
            "Can not create attributes from a non-compound NBT tag"

        for attr in attrs:
            setattr(self, attr.lower(), self._objectify(self._nbt[attr]))

    def _objectify(self, nbt):
        if nbt.tagID == pymclevel.nbt.TAG_COMPOUND:
            return NbtObject(nbt)

        if nbt.tagID == pymclevel.nbt.TAG_LIST:
            items = []
            for item in nbt:
                items.append(self._objectify(item))
            return items

        return nbt.value

    def __str__(self):
        return str(self._nbt)

    def __repr__(self):
        return "<%s>" % (self.__class__.__name__)

    def __getattr__(self, name):
        '''Fallback for non-objectified attributes from nbt data
            Allow accessing `item._nbt["Damage"].value` as `item.damage`
        '''
        try:
            return self._objectify(self._nbt[name])
        except KeyError:
            lowername = name.lower()
            for attr in self._nbt:
                if attr.lower() == lowername:
                    return self._objectify(self._nbt[attr])
            else:
                raise AttributeError("'%s' object has no attribute '%s'"
                                     % (self.__class__.__name__,
                                        name))


def _itemtypes():
    from pymclevel.items import items as ItemTypes
    for ID, stacksize in (( 58, 64),  # Workbench (Crafting Table)
                          (116, 64),  # Enchantment Table
                          (281, 64),  # Bowl
                          (282,  1),  # Mushroom Stew
                          (324,  1),  # Wooden Door
                          (337, 64),  # Clay (Ball)
                          (344, 16),  # Egg
                          (345, 64),  # Compass
                          (347, 64),  # Clock
                          (379, 64),  # Brewing Stand
                          (380, 64),  # Cauldron
                          (395, 64),  # Empty Map
                          ):
        ItemTypes.findItem(ID).stacksize = stacksize
    for item in ItemTypes.itemtypes.itervalues():
        if item.maxdamage is not None:
            item.stacksize = 1
    return ItemTypes


class Item(NbtObject):
    _types = _itemtypes()
    _armorslots = {i: 103 - ((i - 298) % 4) for i in range(298, 318)}

    def __init__(self, nbt):
        super(Item, self).__init__(nbt)
        self._create_nbt_attrs("id", "Damage", "Count")
        self.key = (self.id, self.damage)
        self.type = self._types.findItem(*self.key)

    def __str__(self):
        if self.count > 1:
            return "%d %ss" % (self.count, self.type.name)
        else:
            return self.type.name


class SlotItem(Item):
    def __init__(self, nbt):
        super(SlotItem, self).__init__(nbt)
        self._create_nbt_attrs("Slot")

    def __str__(self):
        return "%s in slot %d" % (super(SlotItem, self).__str__(),
                                  self.slot)


class Pos(collections.Sequence):
    def __init__(self, value):
        self._value = tuple(value)
        self.x, self.y, self.z = self._value
        self.cx, self.cz = self.chunkCoords()

    def __getitem__(self, index):
        return self._value[index]

    def __len__(self):
        return len(self._value)

    def __str__(self):
        strpos = "(%4d, %4d, %4d)" % self._value
        strreg = "(%3d, %3d)" % self.regionCoords()
        stroff = "(%2d, %2d)" % self.regionPos()
        strcnk = "(%4d, %4d)" % self.chunkCoords()
        return ("%s [Region %s, Chunk %s / %s]" %
                (strpos,
                 strreg,
                 stroff,
                 strcnk))

    def __repr__(self):
        return "<%s%r>" % (self.__class__.__name__,
                           self._value)

    def chunkCoords(self):
        '''Return (cx, cz), the coordinates of position's chunk'''
        return (int(self.x) >> 4,
                int(self.z) >> 4)

    def chunkPos(self):
        '''Return (xc, zc, y), the position in its chunk'''
        return (int(self.x) & 0xf,
                int(self.z) & 0xf,
                int(self.y))

    def regionCoords(self):
        '''Return (rx, rz), the coordinates of position's region'''
        cx, cz = self.chunkCoords()
        return (cx >> 5,
                cz >> 5)

    def regionPos(self):
        '''Return (cxr, czr), the chunk's position in its region'''
        cx, cz = self.chunkCoords()
        return (cx & 0x1F,
                cz & 0x1F)


class Entity(NbtObject):
    def __init__(self, nbt):
        super(Entity, self).__init__(nbt)
        self._create_nbt_attrs("id")
        self.pos = Pos((_.value for _ in self._nbt["Pos"]))

    def __str__(self):
        return "Entity at %s" % self.pos


class Mob(Entity):
    pass

class Offer(NbtObject):
    def __init__(self, nbt):
        super(Offer, self).__init__(nbt)
        self.buy = []
        for tag in ("buy", "buyB"):
            if tag in self._nbt:
                self.buy.append(Item(self._nbt[tag]))
        self.sell = Item(self._nbt["sell"])
        self.name = "%s for %s" % (self.sell,
                                   ", ".join([str(_) for _ in self.buy]),
                                   )

    def __str__(self):
        return "[%2d/%2d] %s" % (self.uses,
                                 self.maxuses,
                                 self.name,
                                 )


class Villager(Mob):
    professions = {0: "Farmer",
                   1: "Librarian",
                   2: "Priest",
                   3: "Blacksmith",
                   4: "Butcher"}

    def __init__(self, nbt):
        super(Villager, self).__init__(nbt)
        self.profession = self.professions[self._nbt["Profession"].value]
        self.offers = []
        if "Offers" in self._nbt:
            for offer in self._nbt["Offers"]["Recipes"]:
                self.offers.append(Offer(offer))

    def __str__(self):
        return ("%s: %s\n\t%s"
                % (super(Villager, self).__str__(),
                   self.profession,
                   "\n\t".join([str(_) for _ in self.offers]))
                ).strip()


def main(argv=None):

    args = parseargs(argv)
    args.entity = "Villager"
    args.block = None  #97

    setuplogging(args.loglevel)
    log.debug(args)

    try:
        world = load_world(args.world)
        player = get_player(world, args.player)

        if not player["Dimension"].value == 0:  # 0 = Overworld
            world = world.getDimension(player["Dimension"].value)

        if args.entity is not None:
            entityid = args.entity
            entitycount = 0
            for chunk in world.getChunks():
                for entity in chunk.Entities:
                    if entity["id"].value.lower() == args.entity.lower():
                        entityid = entity["id"].value
                        entitycount += 1
                        #log.info(logcoords(world, chunk, (_.value for _ in entity["Pos"])))
                        log.debug(entity)
                        if entityid == "Villager":
                            villager = Villager(entity)
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


    except (PyMCLevelError, LookupError, IOError) as e:
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
