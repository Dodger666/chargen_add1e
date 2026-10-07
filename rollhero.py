#!/usr/bin/env python3
"""CLI character generator (Python port of rollhero.js / character.js).

Usage:
    python rollhero.py [params...]

Params mirror the Discord "~rollHero" command, e.g.:
    python rollhero.py fighter xp12000
    python rollhero.py "fighter|thief" elf xp40000 name=Bob
    python rollhero.py magicuser xp60000

Notes:
    - Quote multiclass values so the shell does not interpret the pipe, e.g. "fighter|thief".
    - Without an xp<number> param the character is level 1 and receives (almost) no magic items.
    - A seed<number> param makes the whole run deterministic.
    - Attribute params must be UPPERCASE to take effect, e.g. STR=17 (matches the JS behaviour).

Everything lives in this one file. The public class is `Character`; call
`Character.generate(command_line)` or use the command line interface via main().
"""

import sys
import re
import math
import random
import copy

# --------------------------------------------------------------------------
# Randomness (single shared RNG so that a seed makes the whole run reproducible)
# --------------------------------------------------------------------------
_rng = random.Random()


def set_seed(seed):
    _rng.seed(seed)


def _rand():
    return _rng.random()


NAN = float('nan')


def js_round(x):
    """JS Math.round: round half up."""
    return math.floor(x + 0.5)


def _at(arr, i):
    """Return arr[i] if in range else NaN (mimics out-of-range JS array access in numeric context)."""
    if 0 <= i < len(arr):
        return arr[i]
    return NAN


def _at_elem(arr, i):
    """Return arr[i] if in range else None (supports negative like JS .at())."""
    n = len(arr)
    if i < 0:
        i += n
    if 0 <= i < n:
        return arr[i]
    return None


def _pad_end(s, length, ch=' '):
    s = str(s)
    if len(s) >= length:
        return s
    return s + ch * (length - len(s))


def _pad_start(s, length, ch=' '):
    s = str(s)
    if len(s) >= length:
        return s
    return ch * (length - len(s)) + s


# ==========================================================================
# Def - definitions, tables and rules data
# ==========================================================================
class Def:
    STR = "STR"
    DEX = "DEX"
    CON = "CON"
    INT = "INT"
    WIS = "WIS"
    CHA = "CHA"
    ATTRIBUTES = [STR, DEX, CON, INT, WIS, CHA]

    FIGHTER = "fighter"
    THIEF = "thief"
    CLERIC = "cleric"
    MAGICUSER = "magicuser"
    ASSASSIN = "assassin"
    DRUID = "druid"
    PALADIN = "paladin"
    ILLUSIONIST = "illusionist"
    RANGER = "ranger"
    MONK = "monk"
    CLASSES = [FIGHTER, THIEF, CLERIC, MAGICUSER, ASSASSIN, DRUID, PALADIN, ILLUSIONIST, RANGER, MONK]

    FIGHTER_THIEF = FIGHTER + "|" + THIEF
    FIGHTER_CLERIC = FIGHTER + "|" + CLERIC
    FIGHTER_MAGICUSER = FIGHTER + "|" + MAGICUSER
    FIGHTER_ASSASSIN = FIGHTER + "|" + ASSASSIN
    FIGHTER_ILLUSIONIST = FIGHTER + "|" + ILLUSIONIST
    FIGHTER_THIEF_MAGICUSER = FIGHTER + "|" + THIEF + "|" + MAGICUSER
    FIGHTER_MAGICUSER_CLERIC = FIGHTER + "|" + MAGICUSER + "|" + CLERIC
    THIEF_MAGICUSER = THIEF + "|" + MAGICUSER
    THIEF_ILLUSIONIST = THIEF + "|" + ILLUSIONIST
    THIEF_CLERIC = THIEF + "|" + CLERIC
    CLERIC_ASSASSIN = CLERIC + "|" + ASSASSIN
    CLERIC_RANGER = CLERIC + "|" + RANGER
    CLERIC_MAGICUSER = CLERIC + "|" + MAGICUSER
    MULTICLASSES = [FIGHTER_THIEF, FIGHTER_CLERIC, FIGHTER_MAGICUSER, FIGHTER_ASSASSIN, FIGHTER_ILLUSIONIST,
                    FIGHTER_THIEF_MAGICUSER, FIGHTER_MAGICUSER_CLERIC,
                    THIEF_MAGICUSER, THIEF_ILLUSIONIST, THIEF_CLERIC,
                    CLERIC_ASSASSIN, CLERIC_MAGICUSER, CLERIC_RANGER]

    HUMAN = "human"
    HALFLING = "halfling"
    DWARF = "dwarf"
    GNOME = "gnome"
    ELF = "elf"
    HALFORC = "half-orc"
    HALFELF = "half-elf"
    RACES = [HUMAN, HALFLING, DWARF, GNOME, ELF, HALFORC, HALFELF]

    LG = "lawful good"
    LN = "lawful neutral"
    LE = "lawful evil"
    CG = "chaotic good"
    CN = "chaotic neutral"
    CE = "chaotic evil"
    NN = "true neutral"
    NG = "neutral good"
    NE = "neutral evil"
    ALIGNMENT = [LG, LN, LE, CG, CN, CE, NN, NG, NE]

    PICKPOCKETS = "pickpockets"
    OPENLOCKS = "open locks"
    FINDTRAPS = "find&remove traps"
    MOVESILENT = "move silently"
    HIDEINSHADOW = "hide in shadows"
    HEARNOISE = "hear noise"
    CLIMBWALLS = "climb walls"
    READLANGUAGE = "read languages"
    THIEFTALENTS = [PICKPOCKETS, OPENLOCKS, FINDTRAPS, MOVESILENT, HIDEINSHADOW, HEARNOISE, CLIMBWALLS, READLANGUAGE]

    ALLCLASSES = CLASSES + MULTICLASSES

    @staticmethod
    def race_mods(race):
        if race == Def.HALFLING:
            return {Def.DEX: 1, Def.STR: -1}
        if race == Def.HALFORC:
            return {Def.STR: 1, Def.CON: 1, Def.CHA: -2}
        if race == Def.ELF:
            return {Def.DEX: 1, Def.CON: -1}
        if race == Def.DWARF:
            return {Def.CON: 1, Def.CHA: -1}
        return {}

    HITDICE = {FIGHTER: 10, THIEF: 6, CLERIC: 8, MAGICUSER: 4, ASSASSIN: 6,
               DRUID: 8, PALADIN: 10, ILLUSIONIST: 4, RANGER: 8, MONK: 4}

    @staticmethod
    def races_for_class(klass):
        if '|' in klass:
            return dict(Def.races_for_multiclass(klass))
        return dict(Def.races_for_single_class(klass))

    @staticmethod
    def races_for_multiclass(klass):
        m = {
            Def.FIGHTER_THIEF: {Def.ELF: 1, Def.GNOME: 1, Def.HALFELF: 1, Def.HALFLING: 1, Def.HALFORC: 1, Def.DWARF: 1},
            Def.FIGHTER_CLERIC: {Def.HALFELF: 1, Def.HALFORC: 1},
            Def.FIGHTER_MAGICUSER: {Def.ELF: 1, Def.HALFELF: 1},
            Def.FIGHTER_ASSASSIN: {Def.HALFORC: 1},
            Def.FIGHTER_ILLUSIONIST: {Def.GNOME: 1},
            Def.FIGHTER_THIEF_MAGICUSER: {Def.ELF: 1, Def.HALFELF: 1},
            Def.FIGHTER_MAGICUSER_CLERIC: {Def.HALFELF: 1},
            Def.THIEF_MAGICUSER: {Def.ELF: 1, Def.HALFELF: 1},
            Def.THIEF_ILLUSIONIST: {Def.GNOME: 1},
            Def.THIEF_CLERIC: {Def.ELF: 1, Def.HALFELF: 1},
            Def.CLERIC_ASSASSIN: {Def.HALFORC: 1},
            Def.CLERIC_MAGICUSER: {Def.HALFELF: 1},
            Def.CLERIC_RANGER: {Def.HALFELF: 1},
        }
        return m.get(klass, {})

    @staticmethod
    def races_for_single_class(klass):
        if klass == Def.MONK:
            return {Def.HUMAN: 1}
        if klass == Def.PALADIN:
            return {Def.HUMAN: 1}
        if klass == Def.RANGER:
            return {Def.HUMAN: 2, Def.HALFELF: 1}
        if klass == Def.DRUID:
            return {Def.HUMAN: 4, Def.HALFELF: 1}
        if klass == Def.ILLUSIONIST:
            return {Def.HUMAN: 2, Def.GNOME: 1}
        if klass == Def.CLERIC:
            return {Def.HUMAN: 10, Def.HALFORC: 1, Def.HALFELF: 1}
        if klass == Def.MAGICUSER:
            return {Def.HUMAN: 4, Def.ELF: 1, Def.HALFELF: 1}
        if klass == Def.ASSASSIN:
            return {Def.HUMAN: 10, Def.DWARF: 1, Def.GNOME: 1, Def.ELF: 1, Def.HALFORC: 1, Def.HALFELF: 1}
        if klass in (Def.THIEF, Def.FIGHTER):
            return {Def.HUMAN: 12, Def.HALFLING: 1, Def.DWARF: 1, Def.GNOME: 1, Def.ELF: 1, Def.HALFORC: 1, Def.HALFELF: 1}
        return {}

    bonusXPRequirements = {
        FIGHTER: [[STR, 16]],
        THIEF: [[DEX, 16]],
        CLERIC: [[WIS, 16]],
        MAGICUSER: [[INT, 16]],
        DRUID: [[CHA, 16], [WIS, 16]],
        PALADIN: [[CHA, 17], [WIS, 15], [STR, 15]],
    }

    clazzRequirements = {
        FIGHTER: {STR: 9, CON: 7},
        THIEF: {DEX: 9},
        CLERIC: {WIS: 9},
        MAGICUSER: {INT: 9, DEX: 6},
        ASSASSIN: {STR: 12, DEX: 12, INT: 11},
        DRUID: {CHA: 15, WIS: 12},
        PALADIN: {CHA: 17, WIS: 13, STR: 12, INT: 9, CON: 9},
        ILLUSIONIST: {DEX: 16, INT: 15},
        RANGER: {WIS: 14, CON: 14, INT: 13, STR: 13},
        MONK: {STR: 15, WIS: 15, DEX: 15, CON: 11},
    }

    @staticmethod
    def multiclass_requirements(clazz):
        res = {}
        for c in clazz.split("|"):
            for k, v in Def.clazzRequirements[c].items():
                res[k] = max(v, res.get(k, 0))
        return sorted(res.items(), key=lambda kv: kv[1], reverse=True)

    @staticmethod
    def mods(attr, value, percs, mage, verbose):
        short = not verbose

        if attr == Def.STR:
            if value < 4:
                return "Ht-3 Da-1 op.1 bb0%" if short else "to hit adj. -3   dmg adj. -1   open door 1   bend bars 0%"
            if value < 6:
                return "Ht-2 Da-1 op.1 bb0%" if short else "to hit adj. -2   dmg adj. -1   open door 1   bend bars 0%"
            if value < 8:
                return "Ht-1 Da 0 op.1 bb0%" if short else "to hit adj. -1   dmg adj. +0   open door 1   bend bars 0%"
            if value < 10:
                return "Ht0 Da0 op<2 bb1%" if short else "to hit adj. +0   dmg adj. +0   open door 1-2   bend bars 1%"
            if value < 12:
                return "Ht0 Da0 op<2 bb2%" if short else "to hit adj. +0   dmg adj. +0   open door 1-2   bend bars 2%"
            if value < 14:
                return "Ht0 Da0 op<2 bb4%" if short else "to hit adj. +0   dmg adj. +0   open door 1-2   bend bars 4%"
            if value < 16:
                return "Ht0 Da0 op<2 bb7%" if short else "to hit adj. +0   dmg adj. +0   open door 1-2   bend bars 7%"
            if value < 17:
                return "Ht0 Da1 op<3 bb10%" if short else "to hit adj. +0   dmg adj. +1   open door 1-3   bend bars 10%"
            if value < 18:
                return "Ht1 Da1 op<3 bb13%" if short else "to hit adj. +1   dmg adj. +1   open door 1-3   bend bars 13%"
            if (not percs) and value < 19:
                return "Ht1 Da2 op<3 bb16%" if short else "to hit adj. +1   dmg adj. +2   open door 1-3   bend bars 16%"
            if percs is not None and percs < 51:
                return "Ht1 Da3 op<3 bb20%" if short else "to hit adj. +1   dmg adj. +3   open door 1-3   bend bars 20%"
            if percs is not None and percs < 76:
                return "Ht2 Da3 op<4 bb25%" if short else "to hit adj. +2   dmg adj. +3   open door 1-4   bend bars 25%"
            if percs is not None and percs < 91:
                return "Ht2 Da4 op<4 bb30%" if short else "to hit adj. +2   dmg adj. +4   open door 1-4   bend bars 30%"
            if percs is not None and percs < 100:
                return "Ht2 Da5 op<4 bb35%" if short else "to hit adj. +2   dmg adj. +5   open door 1-4   bend bars 35%"
            return "Ht3 Da6 op<5 bb40%" if short else "to hit adj. +3   dmg adj. +6   open door 1-5   bend bars 40%"

        if attr == Def.DEX:
            if value < 4:
                return "rct-3 def +4" if short else "reaction/missile adj. -3   defence adj. +4"
            if value < 5:
                return "rct-2 def +3" if short else "reaction/missile adj. -2   defence adj. +3"
            if value < 6:
                return "rct-1 def +2" if short else "reaction/missile adj. -1   defence adj. +2"
            if value < 7:
                return "rct 0 def +1" if short else "reaction/missile adj. +0   defence adj. +1"
            if value < 15:
                return "rct 0 def 0" if short else "reaction/missile adj. +0   defence adj. +0"
            if value < 16:
                return "rct 0 def -1" if short else "reaction/missile adj. +0   defence adj. -1"
            if value < 17:
                return "rct 1 def -2" if short else "reaction/missile adj. +1   defence adj. -2"
            if value < 18:
                return "rct 2 def -3" if short else "reaction/missile adj. +2   defence adj. -3"
            return "rct 3 def -4" if short else "reaction/missile adj. +3   defence adj. -4"

        if attr == Def.CON:
            if value < 4:
                return "hp-2 sh35% res40%" if short else "hp adj. -2   system shock 35%   res.survival 40%"
            if value < 5:
                return "hp-1 sh40% res45%" if short else "hp adj. -1   system shock 40%   res.survival 45%"
            if value < 6:
                return "hp-1 sh45% res50%" if short else "hp adj. -1   system shock 45%   res.survival 50%"
            if value < 7:
                return "hp-1 sh50% res55%" if short else "hp adj. -1   system shock 50%   res.survival 55%"
            if value < 8:
                return "hp 0 sh55% res60%" if short else "hp adj. +0   system shock 55%   res.survival 60%"
            if value < 9:
                return "hp 0 sh60% res65%" if short else "hp adj. +0   system shock 60%   res.survival 65%"
            if value < 10:
                return "hp 0 sh65% res70%" if short else "hp adj. +0   system shock 65%   res.survival 70%"
            if value < 11:
                return "hp 0 sh70% res75%" if short else "hp adj. +0   system shock 70%   res.survival 75%"
            if value < 12:
                return "hp 0 sh75% res80%" if short else "hp adj. +0   system shock 75%   res.survival 80%"
            if value < 13:
                return "hp 0 sh80% res85%" if short else "hp adj. +0   system shock 80%   res.survival 85%"
            if value < 14:
                return "hp 0 sh85% res90%" if short else "hp adj. +0   system shock 85%   res.survival 90%"
            if value < 15:
                return "hp 0 sh88% res92%" if short else "hp adj. +0   system shock 88%   res.survival 92%"
            if value < 16:
                return "hp 1 sh91% res94%" if short else "hp adj. +1   system shock 91%   res.survival 94%"
            if value < 17:
                return "hp 2 sh95% res96%" if short else "hp adj. +2   system shock 95%   res.survival 96%"
            if value < 18:
                n = '2' if percs is None else '3'
                return ("hp " + n + " sh97% res98%") if short else ("hp adj. +" + n + "   system shock 97%   res.survival 98%")
            ns = '2' if percs is None else '4'
            nv = '2' if percs is None else '3'
            return ("hp " + ns + " sh99% res100%") if short else ("hp adj. +" + nv + "   system shock 99%   res.survival 100%")

        if attr == Def.INT:
            if value < 8:
                return "lng 0" if short else "add. languages 0"
            if value < 9:
                return "lng 1" if short else "add. languages 1"
            if value < 10:
                return ("lng 1 " + ('knw.35% #sp.6' if mage else '')) if short else ("add. languages 1 " + ('know spell 35%   max# spells 6' if mage else ''))
            if value < 11:
                return ("lng 2 " + ('knw.45% #sp.7' if mage else '')) if short else ("add. languages 2 " + ('know spell 45%   max# spells 7' if mage else ''))
            if value < 12:
                return ("lng 2 " + ('knw.45% #sp.7' if mage else '')) if short else ("add. languages 2 " + ('know spell 45%   max# spells 7' if mage else ''))
            if value < 13:
                return ("lng 3 " + ('knw.45% #sp.7' if mage else '')) if short else ("add. languages 3 " + ('know spell 45%   max# spells 7' if mage else ''))
            if value < 14:
                return ("lng 3 " + ('knw.55% #sp.9' if mage else '')) if short else ("add. languages 3 " + ('know spell 55%   max# spells 9' if mage else ''))
            if value < 15:
                return ("lng 4 " + ('knw.55% #sp.9' if mage else '')) if short else ("add. languages 4 " + ('know spell 55%   max# spells 9' if mage else ''))
            if value < 16:
                return ("lng 4 " + ('knw.65% #sp.11' if mage else '')) if short else ("add. languages 4 " + ('know spell 65%   max# spells 11' if mage else ''))
            if value < 17:
                return ("lng 5 " + ('knw.65% #sp.11' if mage else '')) if short else ("add. languages 5 " + ('know spell 65%   max# spells 11' if mage else ''))
            if value < 18:
                return ("lng 6 " + ('knw.75% #sp.14' if mage else '')) if short else ("add. languages 6 " + ('know spell 75%   max# spells 14' if mage else ''))
            return ("lng 7 " + ('knw.85% #sp.18' if mage else '')) if short else ("add. languages 7 " + ('know spell 85%   max# spells 18' if mage else ''))

        if attr == Def.WIS:
            if value < 4:
                return "wil adj -3" if short else "mental save adj. -3"
            if value < 5:
                return "wil adj -2" if short else "mental save adj. -2"
            if value < 8:
                return "wil adj -1" if short else "mental save adj. -1"
            if value < 15:
                return "wil adj +0" if short else "mental save adj. +0"
            if value < 16:
                return "wil adj +1" if short else "mental save adj. +1"
            if value < 17:
                return "wil adj +2" if short else "mental save adj. +2"
            if value < 18:
                return "wil adj +3" if short else "mental save adj. +3"
            return "wil adj +4" if short else "mental save adj. +4"

        if attr == Def.CHA:
            if value < 4:
                return "hn#1 loy-30% rct-25%" if short else "max# henchmen 1   loyalty -30%   reaction adj. -25%"
            if value < 5:
                return "hn#1 loy-25% rct-20%" if short else "max# henchmen 1   loyalty -25%   reaction adj. -20%"
            if value < 6:
                return "hn#2 loy-20% rct-15%" if short else "max# henchmen 2   loyalty -20%   reaction adj. -15%"
            if value < 7:
                return "hn#2 loy-15% rct-10%" if short else "max# henchmen 2   loyalty -15%   reaction adj. -10%"
            if value < 8:
                return "hn#3 loy-10% rct-5%" if short else "max# henchmen 3   loyalty -10%   reaction adj. -5%"
            if value < 9:
                return "hn#3 loy-5% rct0%" if short else "max# henchmen 3   loyalty -5%   reaction adj. +0%"
            if value < 10:
                return "hn#4 loy0% rct0%" if short else "max# henchmen 4   loyalty +0%   reaction adj. +0%"
            if value < 11:
                return "hn#4 loy0% rct0%" if short else "max# henchmen 4   loyalty +0%   reaction adj. +0%"
            if value < 12:
                return "hn#4 loy0% rct0%" if short else "max# henchmen 4   loyalty +0%   reaction adj. +0%"
            if value < 13:
                return "hn#5 loy0% rct0%" if short else "max# henchmen 5   loyalty +0%   reaction adj. +0%"
            if value < 14:
                return "hn#5 loy0% rct5%" if short else "max# henchmen 5   loyalty +0%   reaction adj. +5%"
            if value < 15:
                return "hn#6 loy5% rct10%" if short else "max# henchmen 6   loyalty +5%   reaction adj. +10%"
            if value < 16:
                return "hn#7 loy15% rct15%" if short else "max# henchmen 7   loyalty +15%   reaction adj. +15%"
            if value < 17:
                return "hn#8 loy20% rct20%" if short else "max# henchmen 8   loyalty +20%   reaction adj. +20%"
            if value < 18:
                return "hn#10 loy30% rct25%" if short else "max# henchmen 10  loyalty +30%   reaction adj. +25%"
            return "hn#15 lo.40% rct30%" if short else "max# henchmen 15   loyalty +40%   reaction adj. +30%"
        return ""

    CLASSWEAPONS_MAIN = {
        FIGHTER: [["longsword", 10, "d8/d12"], ["battleaxe", 3, "d8/d8"], ["halberd", 2, "d10/2d6"], ["morningstar", 3, "2d4/d6+1"], ["spear", 2, "d6/d8"], ["broadsword", 4, "2d4/d6+1"], ["bastardsword", 4, "2d4/2d8"], ["2h-sword", 4, "d10/3d6"]],
        THIEF: [["shortsword", 10, "d6/d8"], ["broadsword", 3, "2d4/d6+1"], ["longsword", 2, "d8/d12"]],
        CLERIC: [["mace", 10, "d6+1/d6"], ["flail", 3, "d6+1/2d4"], ["staff", 2, "d6/d6"]],
        MAGICUSER: [["dagger", 10, "d4/d3"], ["staff", 3, "d6/d6"]],
        DRUID: [["scimitar", 10, "d8/d8"], ["spear", 3, "d6/d8"], ["staff", 2, "d6/d6"]],
        ASSASSIN: [["longsword", 10, "d8/d12"], ["shortsword", 3, "d6/d8"], ["broadsword", 2, "2d4/d6+1"]],
        MONK: [["handaxe", 1, "d6/d4"], ["spear", 1, "d6/d8"], ["staff", 1, "d6/d6"], ["falchion", 1, "d8/d8"]],
    }

    CLASSWEAPONS_SCND = {
        FIGHTER: [["handaxe", 1, "d6/d4"], ["bardiche", 1, "2d4/3d4"], ["dagger", 1, "d4/d3"], ["flail", 1, "d6+1/2d4"], ["lance", 1, "2d4+1/3d6"], ["pick", 1, "d6+1/2d4"], ["scimitar", 1, "d8/d8"], ["trident", 1, "d6+1/3d4"]],
        THIEF: [["dagger", 5, "d4/d3"], ["club", 1, "d6/d3"]],
        CLERIC: [["club", 1, "d6/d3"], ["hammer", 3, "d4+1/d4"]],
        MAGICUSER: [["dagger", 10, "d4/d3"], ["staff", 3, "d6/d6"]],
        DRUID: [["club", 1, "d6/d3"], ["dagger", 1, "d4/d3"]],
        ASSASSIN: [["garrot", 1, "d4/d6"], ["dagger", 1, "d4/d3"], ["club", 2, "d6/d3"]],
        MONK: [["handaxe", 1, "d6/d4"], ["spear", 1, "d6/d8"], ["staff", 1, "d6/d6"], ["falchion", 1, "d8/d8"]],
    }

    CLASSWEAPONS_DIST = {
        FIGHTER: [["longbow", 2, "d6/d6", 2], ["bow", 1, "d6/d6", 2], ["javelin", 1, "d6/d6", 1], ["crossbow", 1, "d4+1/d4+2", 0.5], ["comp.bow", 2, "d6/d6", 2]],
        THIEF: [["dagger(thr)", 2, "d4/d3", 2], ["club(thr)", 1, "d6/d3", 1], ["dart", 1, "d3/d2", 3], ["sling", 2, "d4+1/d6+1", 1], ["hand crossbow", 1, "d3/d2", 1], ["bow", 3, "d6/d6", 2]],
        CLERIC: [["club(thr)", 1, "d6/d3", 1], ["hammer(thr)", 2, "d4+1/d4", 1], ["staff sling", 1, "d4+1/d6+1", 1]],
        MAGICUSER: [["dart", 1, "d3/d2", 3], ["sling", 2, "d4+1/d6+1", 1], ["dagger(thr)", 1, "d4/d3", 2]],
        DRUID: [["club(thr)", 1, "d6/d3", 1], ["dagger(thr)", 1, "d4/d3", 2]],
        ASSASSIN: [["dagger(thr)", 2, "d4/d3", 2], ["blowgun", 1, "1/1", 2], ["lasso", 1, "-/-", 1], ["bolas", 1, "-/-", 1], ["crossbow", 2, "d4+1/d4+2"]],
        MONK: [["handaxe(thr)", 1, "d6/d4", 1], ["crossbow", 1, "d4+1/d4+2", 0.5], ["dagger(thr)", 1, "d4/d3", 2], ["javelin", 1, "d6/d6", 1], ["lasso", 1, "-/-", 1]],
    }

    TWO_HANDS = ["halberd", "2h-sword", "staff", "bardiche", "garrot", "longbow", "bow", "crossbow", "comp.bow", "staff sling", "blowgun", "lasso"]

    CLASSARMOR = {
        FIGHTER: [["plate mail", 14, 7], ["splint mail", 2, 6], ["banded mail", 4, 6], ["scale mail", 1, 4]],
        THIEF: [["studded leather", 2, 3], ["leather", 1, 2], ["padded", 1, 2]],
    }

    ARMOR_MOD = {"plate mail": 7, "splint mail": 6, "banded mail": 6, "scale mail": 4, "studded leather": 3, "leather": 2, "padded": 2}

    ITEMS_WPNS = {
        CLERIC: [["mace", 12]],
        DRUID: [["dagger", 10], ["scimitar", 7], ["spear", 10]],
        FIGHTER: [["longsword", 10], ["broadsword", 10], ["shortsword", 10], ["battleaxe", 7], ["spear", 8], ["bow", 1]],
        PALADIN: [["longsword", 10], ["broadsword", 10], ["shortsword", 10], ["battleaxe", 10], ["spear", 8]],
        RANGER: [["longsword", 10], ["broadsword", 9], ["shortsword", 9], ["battleaxe", 7], ["spear", 10], ["bow", 10], ["longbow", 10]],
        MAGICUSER: [["dagger", 15], ["staff", 10]],
        ILLUSIONIST: [["dagger", 15]],
        THIEF: [["dagger", 12], ["longsword", 11], ["shortsword", 10]],
        ASSASSIN: [["dagger", 10], ["longsword", 5], ["shortsword", 5], ["battleaxe", 5], ["spear", 5]],
        MONK: [["dagger", 5], ["spear", 2]],
    }

    ITEMS_ARMR = {
        CLERIC: [["shield", 10], ["plate", 5], ["banded mail", 6], ["chain mail", 8], ["ring o.protection.", 2]],
        DRUID: [["leather", 8], ["ring o.prot.", 5]],
        FIGHTER: [["shield", 10], ["plate", 6], ["banded mail", 8], ["chain mail", 10], ["ring o.protection.", 2]],
        PALADIN: [["shield", 10], ["plate", 6], ["banded mail", 8], ["chain mail", 10], ["ring o.protection.", 2]],
        RANGER: [["shield", 8], ["plate", 5], ["banded mail", 7], ["chain mail", 15], ["ring o.protection.", 2]],
        MAGICUSER: [["ring o.protection.", 15], ["bracers ", 5]],
        ILLUSIONIST: [["ring o.protection.", 15], ["bracers ", 5]],
        THIEF: [["leather", 10], ["ring o.protection.", 4]],
        ASSASSIN: [["shield", 8], ["leather", 10], ["ring o.protection.", 4]],
    }

    ITEMS_PROTSC = [["protection-demons"], ["protection-devil"], ["protection-element."], ["protection-magic"], ["protection-petrify"], ["protection-possess."], ["protection-undead"]]

    OPEN_HAND_DMG = [["d3", None], ["d4", None], ["d6", None],
                     ["d6", "5/4"], ["d6+1", "5/4"], ["2d4", "3/2"],
                     ["2d4+1", "3/2"], ["2d6", "3/2"], ["3d4", "2"],
                     ["2d6+1", "2"], ["3d4+1", "5/2"], ["4d4", "5/2"]]

    MONK_AC = [0, 1, 2, 3, 3, 4, 5, 6, 7, 7, 8, 9, 10]

    THACO_BASE = {
        FIGHTER: [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9],
        CLERIC: [20, 20, 20, 18, 18, 18, 16, 16, 16, 14, 14, 14],
        THIEF: [20, 20, 20, 20, 19, 19, 19, 19, 16, 16, 16, 16],
        MAGICUSER: [20, 20, 20, 20, 20, 19, 19, 19, 19, 19, 16, 16],
    }

    @staticmethod
    def base_thaco(char):
        res = 20
        if Def.FIGHTER in char.clazz:
            res = min(res, Def.THACO_BASE[Def.FIGHTER][char.class_level(Def.FIGHTER) - 1])
        if Def.PALADIN in char.clazz:
            res = min(res, Def.THACO_BASE[Def.FIGHTER][char.class_level(Def.PALADIN) - 1])
        if Def.RANGER in char.clazz:
            res = min(res, Def.THACO_BASE[Def.FIGHTER][char.class_level(Def.RANGER) - 1])
        if Def.CLERIC in char.clazz:
            res = min(res, Def.THACO_BASE[Def.CLERIC][char.class_level(Def.CLERIC) - 1])
        if Def.DRUID in char.clazz:
            res = min(res, Def.THACO_BASE[Def.CLERIC][char.class_level(Def.DRUID) - 1])
        if Def.MONK in char.clazz:
            res = min(res, Def.THACO_BASE[Def.CLERIC][char.class_level(Def.MONK) - 1])
        if Def.THIEF in char.clazz:
            res = min(res, Def.THACO_BASE[Def.THIEF][char.class_level(Def.THIEF) - 1])
        if Def.ASSASSIN in char.clazz:
            res = min(res, Def.THACO_BASE[Def.THIEF][char.class_level(Def.ASSASSIN) - 1])
        if Def.MAGICUSER in char.clazz:
            res = min(res, Def.THACO_BASE[Def.MAGICUSER][char.class_level(Def.MAGICUSER) - 1])
        if Def.ILLUSIONIST in char.clazz:
            res = min(res, Def.THACO_BASE[Def.MAGICUSER][char.class_level(Def.ILLUSIONIST) - 1])
        return res

    @staticmethod
    def add_equipment(char):
        res = []
        clazz = char.clazz

        if Def.FIGHTER in clazz:
            res.append(Table({"": 1, "crowbar": 1, "shovel": 1, "flagon of rum": 1, "signal horn": 1, "horse": 1, "tooth gap": 1, "ugly scar": 1, "tattoo": 1, "medal": 1, "manacles": 1}).roll())
        if Def.RANGER in clazz:
            res.append(Table({"": 1, "pocket warmer": 1, "hunting horn": 2, "oilskin": 2, "lice": 1, "bear trap": 1, "spyglass": 1, "hunting dog": 1, "horse": 1, "fishing pole": 1}).roll())
        if Def.PALADIN in clazz:
            res.append("holy symbol")
            if char.class_level(Def.PALADIN) > 3:
                res.append("heavy warhorse")
            res.append(Table({"": 1, "shaving brush&blade": 1, "whetstone": 1, "romantic novel": 1, "medaillon with portrait": 1, "holy water": 1, "picture of saint": 1, "medal": 1}).roll())
        if Def.CLERIC in clazz:
            res.append("holy symbol")
            res.append(Table({"": 2, "tonsure": 1, "icon of saint": 1, "letter of indulgence": 1, "holy water": 2, "holy scriptures": 1, "ritual robes": 1}).roll())
        if Def.DRUID in clazz:
            res.append("mistletoe")
            res.append(Table({"": 1, "catnip": 1, "dog treats": 1, "bag of nuts": 1, "waterflask": 2, "owl companion": 1,
                              "bottle of wine": 1, "trained rat": 1, "bottle of cider": 1, "pet boar": 1, "wolf companion": 1}).roll())
        if Def.THIEF in clazz:
            res.append("thieves tools")
            res.append(Table({"": 1, "loaded dice": 1, "stink bomb": 1, "bag of marbles": 1, "gambling dice": 1, "pole (10 foot)": 2, "deck of cards": 1, "iron mirror": 1, "burning oil": 2, "tripwire": 1, "caltrops": 1, "ear trumpet": 1, "felt slippers": 1, "counterfeit coins": 1, "lice": 1, "counterfeit pedigree": 1}).roll())
        if Def.ASSASSIN in clazz:
            res.append("thieves tools")
            lvl = char.class_level(Def.ASSASSIN)
            if lvl > 6:
                res.append("ingestive poison B" if Table.roll_die(2) > 1 else "blade poison B")
            if lvl > 4:
                res.append("ingestive poison C" if Table.roll_die(2) > 1 else "blade poison C")
            if lvl > 2:
                res.append("ingestive poison D" if Table.roll_die(2) > 1 else "blade poison D")
            res.append(Table({"burning oil": 1, "tripwire (roll)": 1, "ear trumpet": 1, "caltrops": 1, "fake signet ring": 1, "felt slippers": 1, "poisoned dog treats": 1, "wig&false beard": 1, "hair tinting lotion": 1}).roll())
        if Def.MAGICUSER in clazz:
            res.append("component pouch")
            res.append(Table({"": 1, "notebook": 1, "vial of acid": 1, "chalk": 1, "writing utensils": 1, "crystal ball (mundane)": 1, "caltrops": 1, "Garweez' Bestiarium": 1, "treatise on necromancy": 1}).roll())
        if Def.ILLUSIONIST in clazz:
            res.append("component pouch")
            res.append(Table({"": 1, "meerschaum pipe&weed": 1, "pocket bottle": 1, "writing utensils": 1, "lodestone": 1, "glass prism": 1, "fireworks": 1}).roll())
        if Def.MONK in clazz:
            res.append(Table({"": 1, "hand fan": 1, "gong": 1, "sound bowl": 1, "flute": 1, "yoga mat": 1, "sitting pillow": 1}).roll())

        res.append(Table({"lantern": 3, "torches": 2, "bullseye lantern": 1, "oil lamp": 1, "candles": 1}).roll())
        res.append(Table({"rope": 3, "rope&grappling hook": 2, "hammer&pitons": 2, "rope ladder": 1}).roll())
        res.append(Table({"waterskin": 4, "waterflask": 3, "bottle of wine": 2, "bottle of schnapps": 1}).roll())

        return res

    @staticmethod
    def echantment_bonus(wpn):
        m = re.search(r'\+(\d)$', wpn)
        return int(m.group(1)) if m else 0

    @staticmethod
    def missile_bonus(dex):
        if dex > 15:
            return dex - 15
        if dex < 6:
            return 6 - dex
        return 0

    @staticmethod
    def strength_bonus(strv, percs):
        if strv < 8:
            return math.ceil((strv - 8) / 2)
        if strv > 16:
            if not percs or percs < 50:
                return 1
            if percs < 100:
                return 2
            return 3
        return 0

    @staticmethod
    def strength_damage_bonus(strv, percs):
        if strv < 6:
            return -1
        if strv > 15:
            if strv < 18:
                return 1
            if not percs or percs < 1:
                return 2
            if percs < 76:
                return 3
            if percs < 91:
                return 4
            if percs < 100:
                return 5
            return 6
        return 0

    @staticmethod
    def rof_of(num):
        if num == 0.5:
            return "1/2"
        if num == 1:
            return "1"
        if num == 1.5:
            return "3/2"
        if num == 2:
            return "2"
        if num == 2.5:
            return "5/2"
        return ""

    @staticmethod
    def find_weapon(clazz, name):
        for tbl in (Def.CLASSWEAPONS_MAIN, Def.CLASSWEAPONS_SCND, Def.CLASSWEAPONS_DIST):
            for wpn in tbl.get(clazz, []):
                if wpn[0] == name:
                    return wpn
        return None

    SAVES = {
        FIGHTER: [[14, 15, 16, 17, 17], [13, 14, 15, 16, 16], [11, 12, 13, 13, 14], [10, 11, 12, 12, 13], [8, 9, 10, 9, 11], [7, 8, 9, 8, 10]],
        CLERIC: [[10, 13, 14, 16, 15], [9, 12, 13, 15, 14], [7, 10, 11, 13, 12], [6, 9, 10, 12, 11]],
        MAGICUSER: [[14, 13, 11, 15, 12], [13, 11, 9, 13, 10], [11, 9, 7, 11, 8]],
        THIEF: [[13, 12, 14, 16, 15], [12, 11, 12, 15, 13], [11, 10, 10, 14, 11]],
    }


# ==========================================================================
# Table - weighted random selection
# ==========================================================================
class Table:
    def __init__(self, data=None):
        self.entries = []
        self.max = 0
        if data is None:
            data = {}
        if isinstance(data, dict):
            items = list(data.items())
        else:
            items = [(x[0], x[1]) for x in data]
        for k, v in items:
            w = v if v else 1
            self.entries.append((k, w))
            self.max += w

    @staticmethod
    def roll_die(sides):
        return math.floor(sides * _rand() + 1)

    def roll(self):
        r = math.floor(self.max * _rand())
        prog = 0
        for k, v in self.entries:
            prog += v
            if r < prog:
                return k
        return None

    def roll_idx(self):
        r = math.floor(self.max * _rand())
        idx = 0
        prog = 0
        for k, v in self.entries:
            prog += v
            if r < prog:
                return idx
            idx += 1
        return None

    def multiply(self, mod):
        new_entries = []
        for k, v in self.entries:
            if k in mod:
                new_entries.append((k, v * mod[k]))
            else:
                new_entries.append((k, v))
        self.entries = new_entries
        return self


# ==========================================================================
# Spells - spell lists and spells-per-level tables
# ==========================================================================
class Spells:
    SPELLS_MU = {
        1: [["affect normal fire", 1], ["alarm", 1], ["armor", 2],
            ["burning hands", 1], ["charm person", 3], ["comprehend language", 1],
            ["dancing light", 1], ["detect magic", 2], ["enlarge", 1],
            ["enrage", 1], ["feather fall", 1], ["find familiar", 1],
            ["firewater", 1], ["friends", 1], ["grease", 2],
            ["hold portal", 1], ["identify", 1], ["jump", 1],
            ["light", 1], ["magic missile", 3], ["melt", 1],
            ["mending", 1], ["message", 1], ["mount", 1],
            ["magic aura", 1], ["precipitation", 1], ["protection from evil", 2],
            ["push", 1], ["write", 1], ["run", 1],
            ["shield", 2], ["shocking grasp", 1], ["sleep", 3],
            ["spider climb", 2], ["taunt", 1], ["floating disc", 1],
            ["unseen servant", 1], ["ventriloquism", 1], ["wizard mark", 1]],
        2: [["audible glamer", 1], ["blind", 1], ["continual light", 2],
            ["darkness 15'radius", 2], ["deeppockets", 1], ["detect evil", 1],
            ["detect invisible", 1], ["ESP", 2], ["flaming sphere", 2],
            ["fools gold", 1], ["forget", 1], ["invisibility", 3],
            ["irritation", 1], ["knock", 2], ["know alignment", 1],
            ["levitate", 3], ["locate object", 1], ["magic mouth", 1],
            ["acid arrow", 2], ["mirror image", 3], ["preserve", 1],
            ["pyrotechnics", 2], ["ray of enfeeblement", 1], ["rope trick", 1],
            ["scare", 1], ["shatter", 1], ["stinking cloud", 3],
            ["strength", 1], ["uncontrollable laughter", 2], ["vocalize", 1],
            ["web", 3], ["whip", 1], ["wizard lock", 1],
            ["zephyr", 1]],
        3: [["blink", 1], ["clairaudience", 1], ["clairvoyance", 1],
            ["cloudburst", 1], ["detect illusion", 1], ["dispel magic", 3],
            ["explosive runes", 2], ["feign death", 1], ["fireball", 3],
            ["flame arrow", 2], ["fly", 3], ["gust of wind", 1],
            ["haste", 2], ["hold person", 3], ["infravision", 1],
            ["invisibility 15' radius", 2], ["tiny hut", 1], ["lightning bolt", 3],
            ["material", 1], ["minute meteor", 2], ["monster summon 1", 2],
            ["phantasmal force", 2], ["protection from evil 10'", 2], ["protection from missiles", 2],
            ["secret page", 1], ["snake sigil", 1], ["slow", 3],
            ["suggestion", 2], ["tongues", 2], ["water breathing", 1],
            ["wind wall", 1]],
        4: [["charm monster", 3], ["confusion", 3], ["dig", 1],
            ["dimension door", 2], ["dispel illusion", 1], ["enchanted weapon", 1],
            ["black tentacles", 2], ["extension 1", 1], ["fear", 3],
            ["fire charm", 1], ["fire shield", 2], ["fire trap", 1],
            ["fumble", 2], ["hallucinatory terrain", 1], ["ice storm", 3],
            ["secure shelter", 2], ["magic mirror", 2], ["massmorph", 1],
            ["minor globe of invuln.", 2], ["resilient sphere", 2],
            ["plant growth", 1], ["polymorph other", 3], ["polymorph self", 3],
            ["mnemonic enhancer", 1], ["remove curse", 2], ["shout", 1],
            ["stoneskin", 3], ["ultravision", 1], ["wall of fire", 3],
            ["wall of ice", 2], ["wizard eye", 2]],
        5: [["airy water", 2], ["animal growth", 2], ["animate dead", 2],
            ["avoidance", 2], ["interposing hand", 3], ["cloudkill", 3],
            ["conjure elemental", 3], ["cone of cold", 3], ["contact other plane", 1],
            ["dismissal", 1], ["distance distortion", 1], ["dolor", 1],
            ["extension II", 1], ["fabricate", 1], ["feeblemind", 1],
            ["hold monster", 3], ["secret chest", 1], ["magic jar", 2],
            ["monster summoning 3", 3], ["faithful hound", 1], ["passwall", 2],
            ["sending", 1], ["stone shape", 2], ["telekinesis", 1],
            ["teleport", 1], ["rock to mud", 2], ["wall of force", 2],
            ["wall of iron", 2], ["wall of stone", 2]],
        6: [["anti magic shell", 2], ["forceful hand", 3], ["death spell", 3],
            ["enchant item", 3], ["geas", 2], ["disintegrate", 2],
            ["control weather", 1], ["invisible stalker", 2], ["legend lore", 2],
            ["glassee", 1], ["guards & wards", 1], ["lower water", 1],
            ["move earth", 1], ["freezing sphere", 2], ["project image", 2],
            ["reincarnation", 1], ["repulsion", 1], ["spiritwrack", 1],
            ["stone to flesh", 3], ["globe of invulnerability", 3], ["monster summoning 4", 3]],
    }

    SPELLS_CL = {
        1: [["bless", 1], ["combine", 1], ["command", 3],
            ["create water", 1], ["ceremony", 1], ["cure light wounds", 3],
            ["detect evil", 1], ["detect magic", 2], ["endure cold/heat", 1],
            ["invisibility to undead", 1], ["light", 2], ["magic stone", 1],
            ["penetrate disguise", 1], ["portent", 1], ["precipitation", 1],
            ["protection from evil", 2], ["purify food&drink", 1], ["remove fear", 1],
            ["resist cold", 2], ["sanctuary", 2]],
        2: [["aid", 1], ["augury", 2], ["chant", 1],
            ["detect charm", 1], ["detect life", 1], ["dust devil", 1],
            ["enthrall", 1], ["find traps", 3], ["hold person", 3],
            ["holy symbol", 1], ["know alignment", 2], ["messenger", 1],
            ["resist fire", 2], ["silence 15' radius", 3], ["slow poison", 2],
            ["snake charm", 1], ["speak with animals", 2], ["spiritual hammer", 2],
            ["withdraw", 1], ["wyvern watch", 2]],
        3: [["animate dead", 2], ["cloudburst", 2], ["continual light", 2],
            ["create food&water", 1], ["cure blindness", 2], ["cure disease", 2],
            ["death's door", 1], ["dispel magic", 3], ["feign death", 1],
            ["flame walk", 1], ["glyph of warding", 1], ["locate object", 2],
            ["magical vestment", 1], ["meld into stone", 1], ["negative plane protection", 2],
            ["prayer", 2], ["remove curse", 3], ["remove paralysis", 1],
            ["speak with dead", 2], ["water walk", 1]],
        4: [["abjure", 1], ["cloak of fear", 1], ["cure serious wounds", 3],
            ["detect lie", 2], ["divination", 2], ["exorcise", 2],
            ["giant insect", 1], ["imbue with spell ability", 1], ["lower water", 1],
            ["neutralize poison", 3], ["protection from evil 15'", 3], ["speak with plants", 1],
            ["spell immunity", 1], ["spike stones", 1], ["sticks to snakes", 1],
            ["tongues", 2]],
        5: [["air walk", 2], ["animate dead monster", 3], ["atonement", 1],
            ["commune", 1], ["cure critical wounds", 3], ["dispel evil", 3],
            ["flame strike", 3], ["golem", 1], ["insect plague", 2],
            ["magic font", 1], ["plane shift", 3], ["quest", 2],
            ["rainbow", 1], ["raise dead", 3], ["spike growth", 1],
            ["true seeing", 3]],
    }

    SPELLS_DR = {
        1: [["animal friend.", 3], ["ceremony", 1], ["detect balance", 1],
            ["detect magic", 2], ["detect poison", 1], ["detect snares&pits", 2],
            ["entangle", 3], ["faery fire", 1], ["invisibility to animals", 1],
            ["locate animals", 1], ["pass without trace", 1], ["precipitation", 2],
            ["predict weather", 1], ["purify water", 1], ["shillelagh", 1],
            ["speak with animals", 2]],
        2: [["barkskin", 1], ["charm person/mammal", 3], ["create water", 1],
            ["cure light wounds", 2], ["feign death", 1], ["fire trap", 1],
            ["flame blade", 1], ["goodberry", 3], ["heat metal", 3],
            ["locate plants", 1], ["obscurement", 1], ["produce flame", 1],
            ["reflecting pool", 3], ["slow poison", 3], ["trip", 1],
            ["warp wood", 2]],
        3: [["call lightning", 3], ["cloudburst", 1], ["cure disease", 2],
            ["hold animal", 2], ["know alignment", 1], ["neutral. poison", 3],
            ["plant growth", 1], ["protection from fire", 2], ["pyrotechnics", 2],
            ["snare", 1], ["spike growth", 1], ["starshine", 2],
            ["stone shape", 2], ["summon insect", 1], ["tree", 2],
            ["water breathing", 2]],
        4: [["animal summoning 1", 2], ["call woodland beings", 3], ["control temp.", 1],
            ["cure serious wounds", 3], ["dispel magic", 3], ["hallucinatory forest", 1],
            ["hold plant", 2], ["plant door", 2], ["produce fire", 2],
            ["protection from lightning", 2], ["repel insects", 1], ["speak with plants", 2]],
        5: [["animal growth", 2], ["animal summoning 2", 3], ["anti-plant shell", 2],
            ["commune with nature", 1], ["control winds", 1], ["insect plague", 2],
            ["moonbeam", 2], ["passplant", 1], ["spike stones", 2],
            ["sticks to snakes", 1], ["rock to mud", 2], ["wall of fire", 3]],
    }

    SPELLS_IL = {
        1: [["audible glamor", 1], ["change self", 2], ["chromatic orb", 2],
            ["color spray", 3], ["dancing lights", 1], ["darkness", 2],
            ["detect illusion", 1], ["detect invisib.", 1], ["gaze reflection", 2],
            ["hypnotism", 2], ["light", 1], ["phantasmal force", 3],
            ["phantom armor", 1], ["wall of fog", 1], ["spook", 2]],
        2: [["alter self", 2], ["blindness", 1], ["blur", 2],
            ["deafness", 1], ["detect magic", 2], ["fascinate", 1],
            ["fog cloud", 1], ["hypnotic pattern", 2], ["improved phantasmal force", 3],
            ["invisibility", 3], ["magic mouth", 1], ["mirror image", 3],
            ["misdirection", 1], ["ultravision", 1], ["ventriloquism", 1],
            ["whispering wind", 1]],
        3: [["continual darkness", 2], ["continual light", 2], ["delude", 2],
            ["dispel illusion", 1], ["fear", 2], ["hallucinatory terrain", 1],
            ["illusionary script", 1], ["invisibility 10' radius", 3], ["non-detection", 2],
            ["paralyzation", 2], ["phantom steed", 2], ["phantom wind", 1],
            ["rope trick", 2], ["spectral force", 3], ["suggestion", 2],
            ["wraithform", 3]],
        4: [["confusion", 3], ["dispel exhaustion", 1], ["dispel magic", 3],
            ["emotion", 1], ["improved invisibility", 3], ["massmorph", 1],
            ["minor creation", 1], ["phantasmal killer", 3], ["rainbow pattern", 2],
            ["shadow monster", 2], ["solid fog", 1], ["vacancy", 1]],
        5: [["advanced illusion", 3], ["chaos", 3], ["demi-shadow monster", 2],
            ["dream", 1], ["magic mirror", 3], ["major creation", 2],
            ["maze", 2], ["projected image", 2], ["shadow door", 2],
            ["shadow magic", 2], ["summon shadow", 2], ["tempus fugit", 2]],
    }

    @staticmethod
    def spell_tables(char):
        res = []
        if Def.MAGICUSER in char.clazz:
            res.append(Spells.SPELLS_MU)
        if Def.CLERIC in char.clazz:
            res.append(Spells.SPELLS_CL)
        if Def.DRUID in char.clazz:
            res.append(Spells.SPELLS_DR)
        if Def.ILLUSIONIST in char.clazz:
            res.append(Spells.SPELLS_IL)
        return res

    @staticmethod
    def spells_per_paladin_level(lvl):
        if lvl < 9:
            return None
        if lvl < 10:
            return [1]
        if lvl < 11:
            return [2]
        return [2, 1]

    @staticmethod
    def spells_per_ranger_druid_level(lvl):
        if lvl < 8:
            return None
        if lvl < 10:
            return [1]
        if lvl < 12:
            return [2]
        return [2, 1]

    @staticmethod
    def spells_per_ranger_mage_level(lvl):
        if lvl < 9:
            return None
        if lvl < 11:
            return [1]
        if lvl < 13:
            return [2]
        return [2, 1]

    @staticmethod
    def add_bonus_spells(per_lvl, wis):
        if wis > 12 and len(per_lvl) > 0:
            per_lvl[0] += 1
        if wis > 13 and len(per_lvl) > 0:
            per_lvl[0] += 1
        if wis > 14 and len(per_lvl) > 1:
            per_lvl[1] += 1
        if wis > 15 and len(per_lvl) > 1:
            per_lvl[1] += 1
        if wis > 16 and len(per_lvl) > 2:
            per_lvl[2] += 1
        if wis > 17 and len(per_lvl) > 2:
            per_lvl[2] += 1

    @staticmethod
    def spells_per_cleric_level(lvl):
        if lvl < 2:
            return [1]
        if lvl < 3:
            return [2]
        if lvl < 4:
            return [2, 1]
        if lvl < 5:
            return [3, 2]
        if lvl < 6:
            return [3, 3, 1]
        if lvl < 7:
            return [3, 3, 2]
        if lvl < 8:
            return [3, 3, 2, 1]
        if lvl < 9:
            return [3, 3, 3, 2]
        if lvl < 10:
            return [4, 4, 3, 2, 1]
        if lvl < 11:
            return [4, 4, 3, 3, 2]
        return [5, 4, 4, 3, 2, 1]

    @staticmethod
    def spells_per_druid_level(lvl):
        if lvl < 2:
            return [2]
        if lvl < 3:
            return [2, 1]
        if lvl < 4:
            return [3, 2, 1]
        if lvl < 5:
            return [4, 2, 2]
        if lvl < 6:
            return [4, 3, 2]
        if lvl < 7:
            return [4, 3, 2, 1]
        if lvl < 8:
            return [4, 4, 3, 1]
        if lvl < 9:
            return [4, 4, 3, 2]
        if lvl < 10:
            return [5, 4, 3, 2, 1]
        if lvl < 11:
            return [5, 4, 3, 3, 2]
        return [5, 5, 3, 3, 2, 1]

    @staticmethod
    def spells_per_mage_level(lvl):
        if lvl < 2:
            return [1]
        if lvl < 3:
            return [2]
        if lvl < 4:
            return [2, 1]
        if lvl < 5:
            return [3, 2]
        if lvl < 6:
            return [4, 2, 1]
        if lvl < 7:
            return [4, 2, 2]
        if lvl < 8:
            return [4, 3, 2, 1]
        if lvl < 9:
            return [4, 3, 3, 2]
        if lvl < 10:
            return [4, 3, 3, 2, 1]
        if lvl < 11:
            return [4, 4, 3, 2, 2]
        return [4, 4, 4, 3, 3]

    @staticmethod
    def spells_per_illu_level(lvl):
        if lvl < 2:
            return [1]
        if lvl < 3:
            return [2]
        if lvl < 4:
            return [2, 1]
        if lvl < 5:
            return [3, 2]
        if lvl < 6:
            return [4, 2, 1]
        if lvl < 7:
            return [4, 3, 1]
        if lvl < 8:
            return [4, 3, 2]
        if lvl < 9:
            return [4, 3, 2, 1]
        if lvl < 10:
            return [5, 3, 3, 2]
        if lvl < 11:
            return [5, 4, 3, 2, 1]
        return [5, 4, 3, 3, 2]


# ==========================================================================
# Character
# ==========================================================================
class Character:
    keywords = ["seed", "xp", "lvl", "name"]

    # ---- attribute helpers (dynamic get/set by name) ------------------
    def _get(self, attr):
        return getattr(self, attr, None)

    def _set(self, attr, val):
        setattr(self, attr, val)

    # ---- construction --------------------------------------------------
    def __init__(self, attrs, cl):
        for a in Def.ATTRIBUTES:
            setattr(self, a, None)
        self.percs = None
        self.skills = None
        self.weapons = []
        self.armor = None
        self.ac = None
        self.ac_shield = None
        self.hasShield = None
        self.arcaneSpellsPerLevel = None
        self.arcaneBook = None
        self.illusionsPerLevel = None
        self.illusionsBook = None
        self.druidSpellsPerLevel = None
        self.preparedDruidSpells = None
        self.clericSpellsPerLevel = None
        self.preparedClericSpells = None

        self.params = Character.parse_params(cl)

        self.name = self.params.get("name") or Character.roll_name()

        if attrs:
            attrs.sort()

        self.items = []

        self.error = self.make(self.params, attrs)

    @classmethod
    def generate(cls, command_line=""):
        params = cls.parse_params(command_line)
        if params.get("seed") is not None:
            set_seed(params.get("seed"))
        attrs = cls.roll_sr_attributes()
        return cls(attrs, command_line)

    # ---- attribute rolling --------------------------------------------
    @staticmethod
    def roll_attribute():
        res = 0
        low = 7
        for _ in range(4):
            rolled = math.floor(6 * _rand()) + 1
            low = min(low, rolled)
            res += rolled
        return res - low

    @staticmethod
    def roll_name():
        return ""

    @staticmethod
    def roll_sr_attributes():
        return [Character.roll_attribute() for _ in Def.ATTRIBUTES]

    # ---- aptitude calculation -----------------------------------------
    @staticmethod
    def bonus_xp_aptitude(clazz, race, s_attrs):
        bon = Def.bonusXPRequirements.get(clazz)
        if not bon:
            return 0
        mods = Def.race_mods(race)
        match = True
        for r in range(len(bon)):
            match = match and (bon[r][1] <= (_at(s_attrs, r) + (mods.get(bon[r][0]) or 0)))
        if not match:
            return 0
        return 14 if race == Def.HUMAN else 3

    @staticmethod
    def class_race_aptitude(clazz, race, s_attrs, char):
        mods = Def.race_mods(race)
        cmb = Def.multiclass_requirements(clazz)
        of = 0
        for r in range(len(cmb)):
            ex = char._get(cmb[r][0]) if char else None
            if ex:
                if ex < cmb[r][1]:
                    return 0
                of += 1
            elif cmb[r][1] > (_at(s_attrs, r - of) + (mods.get(cmb[r][0]) or 0)):
                return 0
        return 10 if race == Def.HUMAN else 1

    @staticmethod
    def class_aptitude(clazz, s_attrs, char):
        res = {}
        for r in Def.races_for_class(clazz).keys():
            if not char.race or char.race == r:
                apt = Character.class_race_aptitude(clazz, r, s_attrs, char)
                apt = max(apt, Character.bonus_xp_aptitude(clazz, r, s_attrs))
                res[r] = apt
        return res

    @staticmethod
    def switch_or_take(cur, mn, rmod, avail):
        if cur and cur >= mn:
            return cur
        if cur and cur < mn:
            avail.insert(0, cur)
        idx = -1
        for i, x in enumerate(avail):
            val = (x + rmod) if rmod is not None else NAN
            if val >= mn:
                idx = i
                break
        if idx == -1:
            return avail.pop(-1)
        return avail.pop(idx)

    def distribute_required(self, srt, clazz):
        srt.sort()  # ascending
        req = Def.multiclass_requirements(clazz)
        rmods = Def.race_mods(self.race)
        for pair in req:
            self._set(pair[0], Character.switch_or_take(self._get(pair[0]), pair[1], rmods.get(pair[0]), srt))
        return srt

    @staticmethod
    def tweak_race(params):
        clazz = params.get("class")
        rc = params.get("race")
        if clazz:
            if rc in Def.races_for_class(clazz):
                return rc
            return None
        # No class specified: honour a valid race so the class is rolled
        # from the classes that allow that race (see class_aptitude).
        if rc in Def.RACES:
            return rc
        return None

    @staticmethod
    def tweak_attributes(srt, char):
        req = Def.multiclass_requirements(char.clazz)
        mods = Def.race_mods(char.race or "")
        for pair in req:
            cur = char._get(pair[0])
            if cur and cur < pair[1]:
                srt.append(cur - (mods.get(pair[0]) or 0))
                char._set(pair[0], None)
        srt.sort(reverse=True)  # descending
        idx = 0
        for pair in req:
            if not char._get(pair[0]) and _at(srt, idx) < pair[1]:
                if 0 <= idx < len(srt):
                    srt[idx] = pair[1]
                idx += 1
            else:
                idx += 1
        return srt

    @staticmethod
    def claz_table(apts):
        res = {}
        for k, v in apts.items():
            val = max(v.values()) if v else 0
            if val > 0:
                res[k] = val
        return res

    def prep_proto(self, params, proto):
        if not params:
            return proto
        for k in Def.ATTRIBUTES:
            val = params.get(k)
            if val and proto and len(proto) > 0:
                idx = Table.roll_die(len(proto))
                if idx < len(proto):
                    proto.pop(idx)
            if isinstance(val, int):
                if val < 3:
                    params[k] = 3
                if val > 18:
                    params[k] = 18
        self.set_param_attributes(params)
        return proto

    def make(self, params, proto):
        proto = self.prep_proto(params, proto)

        if proto:
            proto.sort(reverse=True)

        srt = proto if proto is not None else self.get_or_create_sorted_attributes(params, proto)

        # if params want forbidden combo the race param is ignored, class wins
        self.race = Character.tweak_race(params)

        apts = {}
        for c in Def.ALLCLASSES:
            apts[c] = Character.class_aptitude(c, srt, self)

        claz = Character.claz_table(apts)

        self.clazz = params.get("class") or Table(claz).roll()

        srt = Character.tweak_attributes(srt, self)

        asrc = Character.alignment_of_class(self.clazz)
        self.alignment = Table(asrc).roll()

        self.race = self.race or Table(apts.get(self.clazz)).roll()

        srt = self.distribute_required(srt, self.clazz)
        srt = self.distribute_desired(srt, params)
        self.distribute_remaining(srt)

        self.apply_racial_mods(params)

        self.set_stats(params.get("xp") or 0)

        return self

    # ---- skills --------------------------------------------------------
    def set_skills(self):
        table = [[30, 25, 20, 15, 10, 10, 85, 0],
                 [35, 29, 25, 21, 15, 10, 86, 0],
                 [40, 33, 30, 27, 20, 15, 87, 0],
                 [45, 37, 35, 33, 25, 15, 88, 20],
                 [50, 42, 40, 40, 31, 20, 90, 25],
                 [55, 47, 45, 47, 37, 20, 92, 30],
                 [60, 52, 50, 55, 43, 25, 94, 35],
                 [65, 57, 55, 62, 49, 25, 96, 40],
                 [70, 62, 60, 70, 56, 30, 98, 45],
                 [80, 67, 65, 78, 63, 30, 99, 50]]

        if Def.THIEF in self.clazz:
            self.skills = list(table[Character.clazz_level(Def.THIEF, self) - 1])
        elif Def.ASSASSIN in self.clazz:
            self.skills = list(table[max(0, Character.clazz_level(Def.ASSASSIN, self) - 3)])
        elif Def.MONK in self.clazz:
            self.skills = list(table[Character.clazz_level(Def.MONK, self) - 1])

        if not self.skills:
            return

        s = self.skills
        if self.race == Def.DWARF:
            s[1] += 10; s[2] += 15; s[6] -= 10; s[7] -= 5
        elif self.race == Def.ELF:
            s[0] += 5; s[1] -= 5; s[3] += 5; s[4] += 10; s[5] += 5
        elif self.race == Def.GNOME:
            s[1] += 5; s[2] += 10; s[3] += 5; s[4] += 5; s[5] += 10; s[6] -= 15
        elif self.race == Def.HALFELF:
            s[0] += 10; s[4] += 5
        elif self.race == Def.HALFLING:
            s[0] += 5; s[1] += 5; s[2] += 5; s[3] += 10; s[4] += 15; s[5] += 5; s[6] -= 15; s[7] -= 5
        elif self.race == Def.HALFORC:
            s[0] -= 5; s[1] += 5; s[2] += 5; s[5] += 5; s[6] += 5; s[7] -= 10

        dex = self.DEX
        if dex == 9:
            s[0] -= 15; s[1] -= 10; s[2] -= 10; s[3] -= 20; s[4] -= 10
        if dex == 10:
            s[0] -= 10; s[1] -= 5; s[2] -= 10; s[3] -= 15; s[4] -= 5
        if dex == 11:
            s[0] -= 5; s[2] -= 5; s[3] -= 10
        if dex == 12:
            s[3] -= 5
        if dex == 16:
            s[1] += 5
        if dex == 17:
            s[0] += 5; s[1] += 10; s[3] += 5; s[4] += 5
        if dex == 18:
            s[0] += 10; s[1] += 15; s[2] += 5; s[3] += 10; s[4] += 10

    # ---- level limits and levels --------------------------------------
    @staticmethod
    def level_limit(clazz, char):
        race = char.race
        if race == Def.ELF:
            if clazz == Def.FIGHTER:
                return 7 - min(3, 18 - char.STR)
            elif clazz == Def.MAGICUSER:
                return 11 - min(2, 18 - char.INT)
            elif clazz == Def.CLERIC:
                return 7
            elif clazz == Def.ASSASSIN:
                return 10
        elif race == Def.HALFELF:
            if clazz == Def.FIGHTER or clazz == Def.RANGER:
                return 8 - min(2, 18 - char.STR)
            elif clazz == Def.MAGICUSER:
                return 8 - min(2, 18 - char.INT)
            elif clazz == Def.CLERIC:
                return 5
            elif clazz == Def.ASSASSIN:
                return 11
        elif race == Def.DWARF:
            if clazz == Def.ASSASSIN:
                return 9
            elif clazz == Def.FIGHTER:
                return 9 - min(2, 18 - char.STR)
            elif clazz == Def.CLERIC:
                return 8
        elif race == Def.GNOME:
            if clazz == Def.ASSASSIN:
                return 8
            elif clazz == Def.FIGHTER:
                return 6 - (0 if char.STR > 17 else 1)
            elif clazz == Def.ILLUSIONIST:
                if char.INT + char.DEX == 36:
                    return 7
                if char.INT == 17 and char.DEX == 17:
                    return 6
                return 5
            elif clazz == Def.CLERIC:
                return 7
        elif race == Def.HALFORC:
            if clazz == Def.THIEF:
                return 8 - min(2, 18 - char.DEX)
            elif clazz == Def.CLERIC:
                return 4
            elif clazz == Def.FIGHTER:
                return 10
        elif race == Def.HALFLING:
            if clazz == Def.FIGHTER:
                return 6 - min(2, 18 - char.STR)
            if clazz == Def.DRUID:
                return 6
        return 10

    @staticmethod
    def clazz_level(clazz, char):
        lvl = Character.class_level_xp(clazz, char.xps.get(clazz))
        singleclass = 0 if '|' in char.clazz else 2
        return min(lvl, Character.level_limit(clazz, char) + singleclass)

    @staticmethod
    def class_level_xp(clazz, xp):
        if not xp:
            return 1
        dat = []
        if clazz == Def.CLERIC:
            dat = [1500, 3000, 6000, 13000, 27500, 55000, 110000, 225000, 450000, 675000]
        elif clazz == Def.DRUID:
            dat = [2000, 4000, 7500, 12500, 20000, 35000, 60000, 90000, 125000, 200000]
        elif clazz == Def.FIGHTER:
            dat = [2000, 4000, 8000, 18000, 35000, 70000, 125000, 250000, 500000, 750000]
        elif clazz == Def.PALADIN:
            dat = [2750, 5500, 12000, 24000, 45000, 95000, 175000, 350000, 700000, 1050000]
        elif clazz == Def.RANGER:
            dat = [2250, 4500, 10000, 20000, 40000, 90000, 150000, 225000, 325000, 650000]
        elif clazz == Def.MAGICUSER:
            dat = [2500, 5000, 10000, 22500, 40000, 60000, 90000, 135000, 250000, 375000]
        elif clazz == Def.ILLUSIONIST:
            dat = [2250, 4500, 9000, 18000, 35000, 60000, 95000, 145000, 220000, 440000]
        elif clazz == Def.THIEF:
            dat = [1250, 2500, 5000, 10000, 20000, 42500, 70000, 110000, 160000, 220000]
        elif clazz == Def.ASSASSIN:
            dat = [1500, 3000, 6000, 12000, 25000, 50000, 100000, 200000, 300000, 425000]
        elif clazz == Def.MONK:
            dat = [2250, 4750, 10000, 22500, 47500, 98000, 200000, 350000, 500000, 700000]

        idx = next((i for i, v in enumerate(dat) if xp < v), -1)
        return 1 + (9 if idx < 0 else idx)

    def bonus_for_class(self, clazz):
        res = True
        bon = Def.bonusXPRequirements.get(clazz)
        if not bon:
            return False
        for rq in bon:
            res = res and (self._get(rq[0]) >= rq[1])
        return res

    # ---- weapons -------------------------------------------------------
    @staticmethod
    def initial_weapons(clazz):
        if Def.FIGHTER in clazz:
            return 4
        if Def.ASSASSIN in clazz or Def.PALADIN in clazz or Def.RANGER in clazz:
            return 3
        if Def.CLERIC in clazz or Def.DRUID in clazz or Def.THIEF in clazz:
            return 2
        return 1

    @staticmethod
    def levels_per_weapon(clazz):
        if Def.MONK in clazz:
            return 2
        if Def.FIGHTER in clazz or Def.PALADIN in clazz or Def.RANGER in clazz:
            return 3
        if Def.THIEF in clazz or Def.ASSASSIN in clazz or Def.CLERIC in clazz:
            return 4
        if Def.DRUID in clazz:
            return 5
        return 6

    def weapon_count(self):
        res = 0
        for clz in self.xps:
            res += Character.initial_weapons(clz) + math.floor(Character.clazz_level(clz, self) / Character.levels_per_weapon(clz))
        return res

    def weapon_table_class(self, it):
        used = self.clazz
        multi = (it > 3) and (len(self.xps) > 1)
        roll = math.floor(len(self.xps) * _rand()) if multi else 0
        if multi and roll > 0:
            used = "|".join(self.clazz.split("|")[:roll])
        if it == 1 and (Def.THIEF in used or Def.ASSASSIN in used):
            return Def.THIEF
        if Def.FIGHTER in used or Def.PALADIN in used or Def.RANGER in used:
            return Def.FIGHTER
        if Def.ASSASSIN in used:
            return Def.ASSASSIN
        if Def.THIEF in used:
            return Def.THIEF
        if Def.CLERIC in used:
            return Def.CLERIC
        if Def.MAGICUSER in used or Def.ILLUSIONIST in used:
            return Def.MAGICUSER
        if Def.MONK in used:
            return Def.MONK
        if Def.DRUID in used:
            return Def.DRUID
        return "err"

    def weapon_table(self, it):
        d = (it % 3) + 1
        if d <= 1:
            return Def.CLASSWEAPONS_MAIN
        if d == 2:
            return Def.CLASSWEAPONS_DIST
        if d == 3:
            return Def.CLASSWEAPONS_SCND
        return Def.CLASSWEAPONS_MAIN

    def set_weapons(self):
        wpns = []
        c = min(5, self.weapon_count())
        tables = []
        for x in range(1, c + 1):
            tables.append(self.weapon_table(x))
        for i, t in enumerate(tables):
            cl = t.get(self.weapon_table_class(i))
            if not cl:
                continue
            idx = Table(cl).roll_idx()
            bl = next((w for w in wpns if w[0] == cl[idx][0]), None)
            if not bl:
                wpns.append(copy.deepcopy(cl[idx]))
                if "lance" in cl[idx][0]:
                    self.items.append("light warhorse")
        self.weapons = list(wpns)

    # ---- spellbook -----------------------------------------------------
    def class_level(self, clz):
        x = self.xps.get(clz)
        if x is None:
            return 0
        return Character.clazz_level(clz, self)

    def make_spell_table(self, spelltable, lvl, spells):
        res = {}
        map_lvl = {k: v for k, v in spelltable.get(lvl)}
        for name in spells:
            chance = map_lvl.get(name)
            res[name] = chance * chance
        return Table(res)

    def memorize_spells(self, spelltable, spellsperlevel, book):
        res = {}
        for lvl, spls in book.items():
            table = self.make_spell_table(spelltable, lvl, spls)
            mems = {}
            x = spellsperlevel[lvl - 1]
            while x > 0:
                x -= 1
                # the JS dedup condition (string > 2) is always false, so a single pick
                name = table.roll()
                mems[name] = mems.get(name, "") + "\u00d8"
            res[lvl] = [name + " " + _pad_end(mems.get(name, ""), 3, "O") for name in spls]
        return res

    def get_book_spells(self, spelltable, spellsperlevel):
        res = {}
        for lvl, mem in enumerate(spellsperlevel):
            count = (3 if lvl == 0 else 0)
            count += (2 if mem > 1 else 1)
            if lvl > 0 or mem > 1:
                count += Table.roll_die(mem + 1) - 1
            tbl = Table(spelltable.get(lvl + 1))
            names = []
            while count > 0:
                count -= 1
                name = tbl.roll()
                if name in names:
                    self.items.append("scroll:" + name)
                else:
                    names.append(name)
            res[lvl + 1] = names
        return res

    def get_prepared_spells(self, spelltable, spellsperlevel):
        res = {}
        for lvl, mem in enumerate(spellsperlevel):
            count = mem
            tbl = Table(spelltable.get(lvl + 1))
            names = {}
            sub = []
            while count > 0:
                count -= 1
                name = tbl.roll()
                names[name] = 1 + names.get(name, 0)
            for k, v in names.items():
                sub.append(_pad_end(k + " ", len(k) + v + 1, "O"))
            res[lvl + 1] = sub
        return res

    def set_mage_spells(self):
        self.arcaneSpellsPerLevel = None
        if Def.MAGICUSER in self.clazz:
            self.arcaneSpellsPerLevel = Spells.spells_per_mage_level(self.class_level(Def.MAGICUSER))
        elif Def.RANGER in self.clazz:
            self.arcaneSpellsPerLevel = Spells.spells_per_ranger_mage_level(self.class_level(Def.RANGER))
        if self.arcaneSpellsPerLevel:
            book = self.get_book_spells(Spells.SPELLS_MU, self.arcaneSpellsPerLevel)
            self.arcaneBook = self.memorize_spells(Spells.SPELLS_MU, self.arcaneSpellsPerLevel, book)

    def set_illu_spells(self):
        self.illusionsPerLevel = None
        if Def.ILLUSIONIST in self.clazz:
            self.illusionsPerLevel = Spells.spells_per_illu_level(self.class_level(Def.ILLUSIONIST))
        if self.illusionsPerLevel:
            book = self.get_book_spells(Spells.SPELLS_IL, self.illusionsPerLevel)
            self.illusionsBook = self.memorize_spells(Spells.SPELLS_IL, self.illusionsPerLevel, book)

    def set_druid_spells(self):
        self.druidSpellsPerLevel = None
        if Def.DRUID in self.clazz:
            self.druidSpellsPerLevel = Spells.spells_per_druid_level(self.class_level(Def.DRUID))
        elif Def.RANGER in self.clazz:
            self.druidSpellsPerLevel = Spells.spells_per_ranger_druid_level(self.class_level(Def.DRUID))
        if self.druidSpellsPerLevel:
            Spells.add_bonus_spells(self.druidSpellsPerLevel, self.WIS)
            self.preparedDruidSpells = self.get_prepared_spells(Spells.SPELLS_DR, self.druidSpellsPerLevel)

    def set_cleric_spells(self):
        self.clericSpellsPerLevel = None
        if Def.CLERIC in self.clazz:
            self.clericSpellsPerLevel = Spells.spells_per_cleric_level(self.class_level(Def.CLERIC))
        elif Def.PALADIN in self.clazz:
            self.clericSpellsPerLevel = Spells.spells_per_paladin_level(self.class_level(Def.PALADIN))
        if self.clericSpellsPerLevel:
            Spells.add_bonus_spells(self.clericSpellsPerLevel, self.WIS)
            self.preparedClericSpells = self.get_prepared_spells(Spells.SPELLS_CL, self.clericSpellsPerLevel)

    def set_spellbook(self):
        self.set_mage_spells()
        self.set_illu_spells()
        self.set_druid_spells()
        self.set_cleric_spells()

    # ---- armor ---------------------------------------------------------
    def dex_mod(self, dex):
        if dex < 7:
            return dex - 7
        if dex > 14:
            return dex - 14
        return 0

    def set_armor(self):
        ac = None
        if Def.FIGHTER in self.clazz or Def.PALADIN in self.clazz or Def.RANGER in self.clazz or Def.CLERIC in self.clazz:
            ac = Def.FIGHTER
        if Def.DRUID in self.clazz or Def.THIEF in self.clazz or Def.ASSASSIN in self.clazz:
            ac = Def.THIEF

        if ac:
            amap = {}
            for entry in Def.CLASSARMOR[ac]:
                amap[entry[0]] = entry[1]

            has_shield = Def.THIEF not in self.clazz

            wpn_shld = next((w for w in self.weapons if (w[0] not in Def.TWO_HANDS) and len(w) < 4), None)
            has_shield = has_shield and (wpn_shld is not None)

            if ac == Def.FIGHTER:
                if self.xps:
                    vals = list(self.xps.values())
                    if vals and vals[0] < 1:
                        amap["plate mail"] = 1

            self.armor = Table(amap).roll()
            self.ac = 10 - Def.ARMOR_MOD[self.armor] - self.dex_mod(self.DEX)
            self.ac_shield = (self.ac - 1) if has_shield else None
        else:
            is_monk = Def.MONK in self.clazz
            monkmod = _at_elem(Def.MONK_AC, Character.clazz_level(Def.MONK, self) - 1) if is_monk else 0
            if monkmod is None:
                monkmod = 0
            self.armor = "none"
            self.ac = 10 - (monkmod if is_monk else self.dex_mod(self.DEX))
            self.ac_shield = None

    # ---- potions / scrolls / magic ------------------------------------
    def potion_chance(self):
        if Def.DRUID in self.clazz:
            return [11 * self.class_level(Def.DRUID), 2]
        if Def.MAGICUSER in self.clazz:
            return [10 * self.class_level(Def.MAGICUSER), 3]
        if Def.ILLUSIONIST in self.clazz:
            return [10 * self.class_level(Def.ILLUSIONIST), 2]
        if Def.THIEF in self.clazz:
            return [9 * self.class_level(Def.THIEF), 2]
        if Def.FIGHTER in self.clazz:
            return [8 * self.class_level(Def.FIGHTER), 1]
        if Def.RANGER in self.clazz:
            return [7 * self.class_level(Def.RANGER), 1]
        if Def.CLERIC in self.clazz:
            return [6 * self.class_level(Def.CLERIC), 1]
        if Def.PALADIN in self.clazz:
            return [6 * self.class_level(Def.PALADIN), 1]
        if Def.ASSASSIN in self.clazz:
            return [5 * self.class_level(Def.ASSASSIN), 1]
        if Def.MONK in self.clazz:
            return [0, 0]
        return None

    def scroll_chance(self):
        if Def.MAGICUSER in self.clazz:
            return 15 * self.class_level(Def.MAGICUSER)
        if Def.ILLUSIONIST in self.clazz:
            return 12 * self.class_level(Def.ILLUSIONIST)
        if Def.CLERIC in self.clazz:
            return 8 * self.class_level(Def.CLERIC)
        if Def.DRUID in self.clazz:
            return 7 * self.class_level(Def.DRUID)
        if Def.FIGHTER in self.clazz:
            return 6 * self.class_level(Def.FIGHTER)
        if Def.THIEF in self.clazz:
            return 6 * self.class_level(Def.THIEF)
        if Def.RANGER in self.clazz:
            return 5 * self.class_level(Def.RANGER)
        if Def.PALADIN in self.clazz:
            return 4 * self.class_level(Def.PALADIN)
        if Def.ASSASSIN in self.clazz:
            return 3 * self.class_level(Def.ASSASSIN)
        return None

    def set_potions(self):
        if self.xp < 1:
            return
        pc = self.potion_chance() or 0
        if Table.roll_die(100) < pc[0]:
            count = Table.roll_die(pc[1])
            while count > 0:
                count -= 1
                table = ["climbing", "diminution", "extra healing", "fire resistance", "flying", "gaseous form", "growth", "healing", "invisibility", "polymorph self"]
                self.items.append("potion:" + table[Table.roll_die(len(table)) - 1])

    def set_scrolls(self):
        r = Table.roll_die(100)
        sc = self.scroll_chance()
        if sc is not None and r < sc:
            count = Table.roll_die(3)
            while count > 0:
                count -= 1
                if Def.ILLUSIONIST in self.clazz:
                    table = Spells.SPELLS_IL.get(Table.roll_die(4))
                elif Def.MAGICUSER in self.clazz:
                    table = Spells.SPELLS_MU.get(Table.roll_die(6))
                elif Def.CLERIC in self.clazz:
                    table = Spells.SPELLS_CL.get(Table.roll_die(4))
                else:
                    table = [[spl, 1] for spl in Def.ITEMS_PROTSC]
                    count = 0
                tbl = [[spl[0], 1] for spl in table]
                self.items.append("scroll:" + str(Table(tbl).roll()))

    def set_magic_weapon(self):
        if self.xp < 1:
            return
        tgt = None
        wname = None
        replace = None
        roll = 0
        better = 0

        for c in self.clazz.split("|"):
            if tgt is None:
                arr = Def.ITEMS_WPNS.get(c)
                wdx = Table(arr).roll_idx()
                wname = arr[wdx][0]
                roll = arr[wdx][1]

                for idx, val in enumerate(self.weapons):
                    if val[0] == wname:
                        replace = idx
                        break

                found = Def.find_weapon(self.weapon_table_class(0), wname)
                tgt = copy.deepcopy(found) if found is not None else None

                lvl = self.class_level(c)
                roll *= lvl
                better = lvl + max(0, roll - 90)

        dr = Table.roll_die(100)

        if tgt and dr < roll:
            res = ["+2", 2] if dr < better else ["+1", 1]
            Character.enchant(tgt, res)
            if replace is not None:
                self.weapons[replace] = tgt
            else:
                self.weapons.append(tgt)

    def set_magic_armor(self):
        if self.xp < 1:
            return
        tgt = None
        rol = 0
        better = 0

        for c in self.clazz.split("|"):
            if tgt is None:
                arr = Def.ITEMS_ARMR.get(c)
                if arr:
                    if self.armor:
                        for ar in arr:
                            rol = ar[1]
                            if ar[0] == self.armor:
                                tgt = ar
                                break
                    if not tgt and self.hasShield:
                        for ar in arr:
                            rol = ar[1]
                            if ar[0] == "shield":
                                tgt = ar
                                break
                    rl = Table.roll_die(2)
                    if not tgt:
                        pref = "bracers" if rl > 1 else "ring o.protection"
                        for ar in arr:
                            rol = ar[1]
                            if ar[0].startswith(pref):
                                tgt = ar
                                break
                    if not tgt:
                        pref = "ring o.protection" if rl > 1 else "bracers"
                        for ar in arr:
                            rol = ar[1]
                            if ar[0].startswith(pref):
                                tgt = ar
                                break
                lvl = self.class_level(c)
                rol *= lvl
                better = lvl + max(0, rol - 90)

        dr = Table.roll_die(100)

        if tgt and dr < rol:
            item = tgt[0]
            bracers = 1 if item.startswith("bracers") else 0
            res = ["+2", "AC4", -2, -6] if dr < better else ["+1", "AC6", -1, -4]

            item += res[0 + bracers]

            if item.startswith("shield") or item.startswith("ring"):
                self.items.append(item)
            else:
                self.armor = item

            self.ac += res[2 + bracers]
            if self.ac_shield is not None:
                self.ac_shield += res[2 + bracers]

    # ---- levels & stats ------------------------------------------------
    def set_levels(self, xp):
        self.xp = xp
        self.xps = {}
        clz = self.clazz.split("|")
        div = 0.0
        shares = []
        for c in clz:
            shr = 1.1 if self.bonus_for_class(c) else 1.0
            div += shr
            shares.append([c, shr])
        for sh in shares:
            self.xps[sh[0]] = math.floor(sh[1] * xp / div)

    def set_stats(self, xp):
        self.set_levels(xp)
        self.set_hitpoints()
        self.set_skills()
        self.set_weapons()
        self.set_armor()
        self.set_spellbook()
        self.set_magic_armor()
        self.set_magic_weapon()
        self.set_scrolls()
        self.set_potions()
        self.set_misc()
        self.set_equipment()

    def roll_hitpoints(self, clazz, level):
        res = []
        c = level
        spec = clazz in (Def.RANGER, Def.MONK)
        hd = Def.HITDICE[clazz]
        mn = (hd + 1) if spec else (hd + 2) / 2
        while c > 0:
            c -= 1
            roll = math.floor(hd * _rand() + 1)
            if spec and c == 0:
                roll += math.floor(hd * _rand() + 1)
            res.append(max(roll, mn) if c == 0 else roll)
        return res

    def set_hitpoints(self):
        con = min(max(0, self.CON - 14), 5 if self.is_fighter() else 2)
        con_hp = 0
        self.hps = {}
        for clz in self.xps:
            lvl = Character.clazz_level(clz, self)
            con_hp += lvl * con
            self.hps[clz] = self.roll_hitpoints(clz, lvl)
        thp = 0.0
        for rld in self.hps.values():
            for dr in rld:
                thp += dr
        self.hp = js_round((thp + con_hp) / len(self.xps) * 10) / 10

    def is_fighter(self):
        return Def.FIGHTER in self.clazz or Def.RANGER in self.clazz or Def.PALADIN in self.clazz

    def is_multiclass(self):
        return "|" in self.clazz

    def get_hitpoints(self):
        if self.is_multiclass():
            return str(js_round(self.hp))
        return str(int(self.hp)) if float(self.hp).is_integer() else str(self.hp)

    def get_levels(self):
        if not self.is_multiclass():
            return self.class_level(self.clazz)
        res = [Character.clazz_level(clz, self) for clz in self.xps]
        return "[" + "|".join(str(x) for x in res) + "]"

    @staticmethod
    def alignment_of_class(clazzz):
        clazz = clazzz
        if Def.RANGER in clazz:
            clazz = Def.RANGER
        elif Def.ASSASSIN in clazz:
            clazz = Def.ASSASSIN
        elif Def.THIEF in clazz:
            clazz = Def.THIEF

        if clazz == Def.DRUID:
            return {Def.NN: 1}
        if clazz == Def.RANGER:
            return {Def.LG: 1, Def.CG: 1, Def.NG: 1}
        if clazz == Def.PALADIN:
            return {Def.LG: 1}
        if clazz == Def.THIEF:
            return {Def.LN: 4, Def.LE: 3, Def.CN: 4, Def.CE: 3, Def.NG: 2, Def.NE: 3}
        if clazz == Def.ASSASSIN:
            return {Def.LE: 1, Def.CE: 1, Def.NE: 1}
        if clazz == Def.MONK:
            return {Def.LG: 1, Def.LN: 1, Def.LE: 1}
        return {Def.LG: 3, Def.LN: 2, Def.LE: 1,
                Def.CG: 3, Def.CN: 2, Def.CE: 1,
                Def.NN: 2, Def.NG: 3, Def.NE: 1}

    # ---- misc / equipment ---------------------------------------------
    def set_misc(self):
        max_lvl = 0
        for clz in self.xps:
            max_lvl = Character.clazz_level(clz, self)

        sd = 1 + max(0, math.floor((max_lvl - 3) / 2))
        count = Table.roll_die(sd) - 1

        while count > 0:
            count -= 1
            table = ["ring o.feath.fall", "ring o.warmth", "ring o.waterwalk", "wand o.negation", "wand o.wonder", "bag o.holding",
                     "folding boat", "brooch o.shielding", "cloak o.elvenkind", "boots o.elvenkind", "2 javelin o.lightning",
                     "2 javelin o.piercing", "necklace o.adaptation", "robe o.useful items", "rope o.climbing", "trident o.warning",
                     "wings o.flying", "boots o.levitation"]
            item = table[Table.roll_die(len(table)) - 1]
            if item not in self.items:
                self.items.append(item)

    def set_equipment(self):
        res = [v for v in Def.add_equipment(self) if v != ""]

        iset = []
        for v in res:
            if v not in iset:
                iset.append(v)

        max_lvl = 0
        for clz in self.xps:
            max_lvl = max(max_lvl, Character.clazz_level(clz, self))

        iset.append("gold: " + str(max_lvl * max_lvl * Table.roll_die(20)))

        self.items.extend(iset)

        if self.race in (Def.DWARF, Def.HALFLING, Def.GNOME):
            self.items = [v.replace("horse", "pony") for v in self.items]

    # ---- attribute distribution ---------------------------------------
    @staticmethod
    def create_sorted_attributes():
        res = [Character.roll_attribute() for _ in Def.ATTRIBUTES]
        res.sort(reverse=True)
        return res

    def get_or_create_sorted_attributes(self, params, proto):
        self.set_param_attributes(params)
        res = self.roll_attributes()
        res.sort(reverse=True)
        return res

    def set_param_attributes(self, params):
        if not params:
            return
        for a in Def.ATTRIBUTES:
            v = params.get(a)
            if v:
                self._set(a, int(v))

    def roll_attributes(self):
        res = []
        has_nine = False
        for a in Def.ATTRIBUTES:
            t = self._get(a)
            if t is None:
                res.append(Character.roll_attribute())
                t = res[-1]
            has_nine = has_nine or (t > 8)
        if not has_nine:
            if len(res) > 0:
                res[0] = 9
            else:
                self._set([Def.DEX, Def.WIS][math.floor(2 * _rand())], 9)
        return res

    @staticmethod
    def normalize_class(s):
        if not s:
            return None
        comp = s.split("|")
        for clz in Def.ALLCLASSES:
            hits = 0
            for c in comp:
                if c in clz:
                    hits += 1
            if hits == len(comp) and hits == len(clz.split("|")):
                return clz
        return None

    @staticmethod
    def parse_params(s):
        res = {}
        if not s.strip():
            return res
        pieces = re.split(r'\s+', s)
        for l in pieces:
            if not l:
                continue
            m = re.match(r'([^\d^=]+)=?(\d{0,7})?(\D{2,64})?', l)
            if m and m.group(1):
                g1 = m.group(1)
                if g1.lower() == "name":
                    res["name"] = m.group(3)
                elif g1.lower() in Character.keywords:
                    res[g1] = int(m.group(2))
                elif g1.lower() in Def.RACES:
                    res["race"] = g1.lower()
                elif g1.upper() in Def.ATTRIBUTES:
                    res[g1] = (m.group(2) or "").upper()
                else:
                    cl = Character.normalize_class(g1.lower())
                    if cl:
                        res["class"] = cl
        return res

    @staticmethod
    def desired_attributes(clazz, attrs):
        v1 = math.floor(2 * _rand())
        v2 = math.floor(3 * _rand())

        if clazz == Def.MONK:
            return [Def.DEX, Def.CON if v1 else Def.STR, Def.STR if v1 else Def.CON]
        if clazz == Def.PALADIN:
            return [Def.CON if v1 else Def.STR, Def.STR if v1 else Def.CON, Def.DEX]
        if clazz == Def.RANGER:
            return [Def.CON if v1 else Def.STR, Def.STR if v1 else Def.CON, Def.DEX]
        if clazz == Def.DRUID:
            return [Def.WIS, Def.CON]
        if clazz == Def.ILLUSIONIST:
            return [Def.INT, Def.CON if v1 else Def.DEX, Def.DEX if v1 else Def.CON]
        if clazz == Def.CLERIC:
            return [Def.WIS, Def.CON]
        if clazz == Def.MAGICUSER:
            return [Def.INT, Def.CON if v1 else Def.DEX, Def.DEX if v1 else Def.CON]
        if clazz == Def.ASSASSIN:
            return [Def.DEX, Def.CON if v1 else Def.STR, Def.STR if v1 else Def.CON, Def.INT]
        if clazz == Def.FIGHTER:
            return [Def.CON if v1 else Def.STR, Def.STR if v1 else Def.CON, Def.DEX]
        if clazz == Def.THIEF:
            return [Def.DEX, Def.CON, Def.INT]
        if clazz == Def.FIGHTER_THIEF:
            return [Def.STR if v1 else Def.DEX, Def.DEX if v1 else Def.STR, Def.CON, Def.INT]
        if clazz == Def.FIGHTER_CLERIC:
            return [Def.WIS if v1 else Def.STR, Def.STR if v1 else Def.WIS, Def.CON]
        if clazz == Def.FIGHTER_MAGICUSER:
            return [Def.STR if v1 else Def.INT, Def.INT if v1 else Def.STR, Def.CON]
        if clazz == Def.FIGHTER_ASSASSIN:
            return [Def.STR if v1 else Def.DEX, Def.DEX if v1 else Def.STR, Def.CON, Def.INT]
        if clazz == Def.FIGHTER_ILLUSIONIST:
            return [Def.STR if v1 else Def.INT, Def.INT if v1 else Def.STR, Def.CON]
        if clazz == Def.FIGHTER_THIEF_MAGICUSER:
            if v2 < 1:
                return [Def.STR, Def.DEX, Def.INT]
            if v2 < 2:
                return [Def.DEX, Def.INT, Def.STR]
            return [Def.INT, Def.STR, Def.DEX]
        if clazz == Def.FIGHTER_MAGICUSER_CLERIC:
            if v2 < 1:
                return [Def.STR, Def.WIS, Def.INT]
            if v2 < 2:
                return [Def.WIS, Def.INT, Def.STR]
            return [Def.INT, Def.STR, Def.WIS]
        if clazz in (Def.THIEF_MAGICUSER, Def.THIEF_ILLUSIONIST):
            return [Def.DEX if v1 else Def.INT, Def.INT if v1 else Def.DEX, Def.CON]
        if clazz in (Def.THIEF_CLERIC, Def.CLERIC_ASSASSIN):
            return [Def.DEX if v1 else Def.WIS, Def.WIS if v1 else Def.DEX, Def.CON]
        if clazz == Def.CLERIC_RANGER:
            return [Def.STR if v1 else Def.WIS, Def.WIS if v1 else Def.STR, Def.CON]
        return []

    def distribute_desired(self, srt, params):
        srt.sort(reverse=True)
        wnt = Character.desired_attributes(self.clazz, srt)
        rmod = Def.race_mods(self.race)
        for w in wnt:
            if not params.get(w):
                cur = self._get(w)
                mod = rmod.get(w) or 0
                if len(srt) > 0 and (not cur or (cur + mod) < srt[0]):
                    self._set(w, srt.pop(0))
                    if cur:
                        idx = next((i for i, v in enumerate(srt) if v < cur), -1)
                        srt.insert(len(srt) if idx < 0 else idx, cur)
        return srt

    def apply_racial_mods(self, params):
        for k, v in Def.race_mods(self.race).items():
            if not params.get(k):
                self._set(k, self._get(k) + v)

    def distribute_remaining(self, srt):
        Character.shuffle(srt)
        for a in Def.ATTRIBUTES:
            if self._get(a) is None:
                self._set(a, srt.pop(0))
        if Def.FIGHTER in self.clazz or Def.RANGER in self.clazz or Def.PALADIN in self.clazz:
            self.percs = Table.roll_die(100) if self.STR >= 18 else 0

    @staticmethod
    def shuffle(array):
        cur = len(array)
        while cur > 0:
            cur -= 1
            rand = math.floor(_rand() * (cur + 1))
            array[cur], array[rand] = array[rand], array[cur]

    @staticmethod
    def enchant(wpn, lvl):
        res = []
        for dmg in wpn[2].split("/"):
            if "+1" in dmg:
                res.append(dmg.replace("+1", "+" + str(1 + lvl[1])))
            else:
                res.append(dmg + lvl[0])
        wpn[0] += lvl[0]
        wpn[2] = "/".join(res)

    @staticmethod
    def saves(char):
        res = [20, 20, 20, 20, 20, 20]
        for clz in char.clazz.split("|"):
            tmp = []
            if clz == Def.FIGHTER:
                tmp = Def.SAVES[Def.FIGHTER][math.ceil(Character.clazz_level(Def.FIGHTER, char) / 2) - 1]
            elif clz == Def.PALADIN:
                tmp = Def.SAVES[Def.FIGHTER][math.ceil(Character.clazz_level(Def.PALADIN, char) / 2) - 1]
            elif clz == Def.RANGER:
                tmp = Def.SAVES[Def.FIGHTER][math.ceil((Character.clazz_level(Def.RANGER, char) / 2) - 1)]
            elif clz == Def.CLERIC:
                tmp = Def.SAVES[Def.CLERIC][math.ceil((Character.clazz_level(Def.CLERIC, char) / 3) - 1)]
            elif clz == Def.DRUID:
                tmp = Def.SAVES[Def.CLERIC][math.ceil((Character.clazz_level(Def.DRUID, char) / 3) - 1)]
            elif clz == Def.THIEF:
                tmp = Def.SAVES[Def.THIEF][math.ceil((Character.clazz_level(Def.THIEF, char) / 4) - 1)]
            elif clz == Def.ASSASSIN:
                tmp = Def.SAVES[Def.THIEF][math.ceil((Character.clazz_level(Def.ASSASSIN, char) / 4) - 1)]
            elif clz == Def.MONK:
                tmp = Def.SAVES[Def.THIEF][math.ceil((Character.clazz_level(Def.MONK, char) / 4) - 1)]
            elif clz == Def.MAGICUSER:
                tmp = Def.SAVES[Def.MAGICUSER][math.ceil((Character.clazz_level(Def.MAGICUSER, char) / 5) - 1)]
            elif clz == Def.ILLUSIONIST:
                tmp = Def.SAVES[Def.MAGICUSER][math.ceil((Character.clazz_level(Def.ILLUSIONIST, char) / 5) - 1)]

            ring = next((v for v in char.items if v.startswith("ring o.protection")), "") if char.items else ""
            bonus = (2 if ring.endswith("+2") else 1) if ring else 0

            res = [min(v, res[i]) - bonus for i, v in enumerate(tmp)]
        return res

    def racial_bonus(self):
        if self.race in (Def.DWARF, Def.HALFLING, Def.GNOME):
            return math.floor(self.CON / 3.5)
        return None

    # ---- text sheet rendering -----------------------------------------
    def to_text_sheet_header(self):
        res = []
        lm = "  "
        res.append(lm + _pad_end("Name:", 12) + (self.name or ""))
        res.append(lm + _pad_end("Race:", 12) + (self.race or ""))
        res.append(lm + _pad_end("Class:", 12) + (self.clazz or ""))
        res.append(lm + _pad_end("Level:", 12) + str(self.get_levels()))
        res.append(lm + _pad_end("Alignment:", 12) + (self.alignment or ""))
        res.append(lm + _pad_end("Hitpoints:", 12) + self.get_hitpoints())
        res.append(lm + _pad_end("Experience:", 12) + "[" + "/".join(str(x) for x in self.xps.values()) + "]\n")
        return "\n".join(res)

    def number_of_attacks(self):
        lvl = 0
        cc = None
        for clz in (Def.FIGHTER, Def.PALADIN, Def.RANGER):
            lvl = Character.clazz_level(clz, self)
            if lvl > 1:
                cc = clz
                break
        if not cc:
            return ""
        no_rng = cc != Def.RANGER
        if lvl > 14:
            return "At#:2"
        if lvl > 12 and no_rng:
            return "At#:2"
        if lvl > 7:
            return "At#:3/2"
        if lvl > 6 and no_rng:
            return "At#:3/2"
        return ""

    def to_text_sheet_weapons(self):
        lm = "  "
        res = "_________________________________________________________________________________\n"
        res += lm + "Weapons:\n"
        monk = Def.MONK in self.clazz
        monklvl = self.class_level(Def.MONK) if monk else 0
        hand = _at_elem(Def.OPEN_HAND_DMG, monklvl) if monk else None
        if monk and hand is None:
            monk = False
        b = [11, len(hand[0]), len(hand[1] or "")] if monk else [11, 0, 0]

        if self.weapons:
            for w in self.weapons:
                b[0] = max(b[0], len(w[0]))
                b[1] = max(b[1], len(w[2]))
                if len(w) > 3 and w[3] is not None:
                    b[2] = max(b[2], len(Def.rof_of(w[3])))

            for w in self.weapons:
                missile = len(w) > 3

                aggro = Def.base_thaco(self)

                if self.race == Def.ELF:
                    if "longsword" in w[0] or "shortsword" in w[0] or ("bow" in w[0] and "cross" not in w[0]):
                        aggro -= 1

                if not monk:
                    aggro -= Def.missile_bonus(self.DEX) if missile else Def.strength_bonus(self.STR, self.percs)

                aggro -= Def.echantment_bonus(w[0])

                damage = 0 if missile else Def.strength_damage_bonus(self.STR, self.percs)

                if monk:
                    damage = math.floor(monklvl / 2)

                d = w[2].split("/")
                while len(d) < 2:
                    d.append("")

                ms = re.search(r'\+(\d)', d[0])
                smal = ms.group(1) if ms else "0"
                ml = re.search(r'\+(\d)', d[1])
                larg = ml.group(1) if ml else "0"

                if smal != "0":
                    d[0] = d[0].replace("+" + smal, "")
                if larg != "0":
                    d[1] = d[1].replace("+" + larg, "")

                smal = int(smal) + damage
                larg = int(larg) + damage

                d[0] += ("+" + str(smal)) if smal > 0 else (str(smal) if smal < 0 else "")
                d[1] += ("+" + str(larg)) if larg > 0 else (str(larg) if larg < 0 else "")

                w[2] = "/".join(d)

                thaco = " THACO:" + _pad_start(str(aggro), 2) + "  "
                dmg = " DMG:" + _pad_end(w[2], b[1] + 2)
                if (len(w) <= 3) or (w[3] is None):
                    rof = _pad_start(" " + self.number_of_attacks(), b[2])
                else:
                    rof = _pad_start(" RoF:" + Def.rof_of(w[3]), b[2])
                res += lm + _pad_end(w[0], min(14, b[0])) + thaco + dmg + rof + "\n"

        if monk:
            aggro = Def.base_thaco(self)
            dmg = " DMG:" + _pad_end(hand[0], b[1])
            rof = _pad_start(" At#:" + hand[1], b[2]) if hand[1] else ""
            res += lm + _pad_end("open hand", min(14, b[0])) + " THACO:" + _pad_start(str(aggro), 2) + "  " + dmg + rof + "\n"

        return res

    def to_text_sheet_attributes(self):
        res = []
        res.append("_________________________________________________________________________________")
        for attr in Def.ATTRIBUTES:
            lm = "  "
            perc_ = ""
            if self.percs:
                if self.percs < 1:
                    perc_ = ""
                elif self.percs == 100:
                    perc_ = "00"
                else:
                    perc_ = _pad_start(str(self.percs), 2, "0")
            no = str(self._get(attr)) + ("." + perc_ if (self.percs and self.percs > 0 and attr == Def.STR) else "")
            mage = self.arcaneBook or self.illusionsBook
            res.append(lm + attr + ": " + _pad_start(no, 5) + "  " + Def.mods(attr, self._get(attr), self.percs, mage, True))
        return "\n".join(res) + "\n"

    def to_text_sheet_armor(self):
        res = "_________________________________________________________________________________\n"
        res += "  Armor:\n"
        res += "  " + _pad_end(self.armor, 14) + " AC: " + str(self.ac) + (" (+shield): " + str(self.ac_shield) if self.ac_shield else "") + "\n"
        return res

    def to_text_sheet_skills(self):
        if not self.skills:
            return ""
        res = "_________________________________________________________________________________\n"
        lm = "  "
        is_monk = Def.MONK in self.clazz
        names = ["Pick Pockets........", "Open Locks..........", "Find&Remove Traps...", "Move Silent.........",
                 "Hide in Shadow......", "Hear Noise..........", "Climb Wall..........", "Read Language......."]
        if is_monk:
            names = names[1:1 + (len(names) - 2)]
        for i, n in enumerate(names):
            res += lm + n + _pad_start(str(self.skills[i + (1 if is_monk else 0)]), 2) + ("% " if (i + 1) % 3 else "% \n")
        return res + "\n"

    def to_text_sheet_racial_abilities(self):
        if self.race == Def.HUMAN:
            return ""
        lm = "  "
        ab = ""
        res = "_________________________________________________________________________________\n"
        res += lm + self.race + " abilities: \n"
        if self.race == Def.DWARF:
            ab = (lm + "saves vs. poison/magic/rod,staff,wand +" + str(self.racial_bonus()) + " / infravision 60'\n" +
                  lm + "+1 vs.goblinoid / giantkin hit -4 / detect slopes 75% sliding walls 66%\n" +
                  lm + "stonetraps/depth 50%\n")
        if self.race == Def.ELF:
            ab = (lm + "90% resistance to sleep&charm / find secret (1in6) or concealed doors (3in6)\n" +
                  lm + "infravision 60' / surprise monsters (4in6) when alone\n")
        if self.race == Def.GNOME:
            ab = (lm + "saves vs. magic/rod,staff,wand +" + str(self.racial_bonus()) + " / infravision 60'\n" +
                  lm + "+1 vs.kobolds&goblins / speak with small burrowing animals\n" +
                  lm + "giantkin hit -4 / detect slopes 80% sliding walls 70% depth 60% direction 50%\n")
        if self.race == Def.HALFELF:
            ab = (lm + "30% resistance to sleep&charm / find secret (1in6) or concealed doors (3in6)\n" +
                  lm + "infravision 60'\n")
        if self.race == Def.HALFLING:
            ab = (lm + "saves vs. poison/magic/rod,staff,wand +" + str(self.racial_bonus()) + " / infravision 60' / surprise 4in6\n" +
                  lm + "detect slopes 75% direction 50%\n")
        if self.race == Def.HALFORC:
            ab = lm + "infravision 60'\n"
        return res + ab

    def to_text_sheet_saves(self):
        lm = "  "
        sv = Character.saves(self)
        res = "_________________________________________________________________________________\n"
        res += lm + "Saving throws:\n"
        res += lm + "Paralyze/Poison/Death." + _pad_start(str(sv[0]), 2, ".") + "  Rod/Staff/Wand........" + _pad_start(str(sv[2]), 2, ".") + "  Spells ..............." + _pad_start(str(sv[4]), 2, ".") + "\n"
        res += lm + "Petrify/Polymorph....." + _pad_start(str(sv[1]), 2, ".") + "  Breath Weapon........." + _pad_start(str(sv[3]), 2, ".") + "  \n"
        return res

    def spell_array_to_string(self, arr):
        if len(arr) < 1:
            return ""
        return "[" + "/".join(str(x) for x in arr) + "]"

    def to_text_sheet_spells(self, book, title, per_level, oo=False):
        if not book or not per_level:
            return ""
        lm = "  "
        lo = "O" if oo else " "
        res = "_________________________________________________________________________________\n"
        res += lm + title + ": " + self.spell_array_to_string(per_level) + "\n\n"
        regex = re.compile(r'\s([O\u00d8]{1,4})$')

        for lvl, spells in book.items():
            for idx, spell in enumerate(spells):
                mem = regex.search(spell)
                name = regex.sub("", spell)
                marks = mem.group(1) if mem else ""
                if idx % 2 == 0:
                    res += lm + (("Lvl" + str(lvl) + ": ") if idx == 0 else "      ") + _pad_end(marks, 4, lo) + _pad_end(name, 24) + ("\n" if idx == len(spells) - 1 else "")
                else:
                    res += lm + _pad_end(marks, 4, lo) + " " + _pad_end(name, 23) + "\n"
        return res

    def to_text_sheet_items(self):
        if not self.items:
            return ""
        lm = "  "
        res = "_________________________________________________________________________________\n"
        res += lm + "Equipment:\n\n"
        for idx, it in enumerate(self.items):
            last = (idx % 2) != 0
            res += lm + _pad_end(it, 36) + ("\n" if last else "")
        return res

    def to_text_sheet(self):
        res = self.to_text_sheet_header()
        res += self.to_text_sheet_attributes()
        res += self.to_text_sheet_racial_abilities()
        res += self.to_text_sheet_saves()
        res += self.to_text_sheet_weapons()
        res += self.to_text_sheet_armor()
        res += self.to_text_sheet_skills()
        res += self.to_text_sheet_spells(self.preparedDruidSpells, "Memorized Druid Spells ", self.druidSpellsPerLevel)
        res += self.to_text_sheet_spells(self.preparedClericSpells, "Memorized Cleric Spells ", self.clericSpellsPerLevel)
        res += self.to_text_sheet_spells(self.illusionsBook, "Book of Illusions ", self.illusionsPerLevel)
        res += self.to_text_sheet_spells(self.arcaneBook, "Arcane Spellbook ", self.arcaneSpellsPerLevel)
        res += self.to_text_sheet_items()
        return res


# ==========================================================================
# CLI
# ==========================================================================
def print_usage():
    print("""rollhero - generate an AD&D-1e style character sheet

Usage:
  python rollhero.py [params...]

Params (all optional, space separated):
  <class>        fighter, thief, cleric, magicuser, assassin, druid,
                 paladin, illusionist, ranger, monk
                 multiclass joined with '|', e.g. "fighter|thief"
  <species>      human, halfling, dwarf, gnome, elf, half-orc, half-elf
  xp<number>     experience points, e.g. xp12000
  seed<number>   deterministic generation
  name=<text>    set the character name
  STR=<n> ...    force an attribute (UPPERCASE), e.g. STR=17

Examples:
  python rollhero.py fighter xp12000
  python rollhero.py "fighter|thief" elf xp40000 name=Bob
  python rollhero.py magicuser xp60000""")


def main(argv):
    args = argv[1:]

    if "-h" in args or "--help" in args:
        print_usage()
        return 0

    command_line = " ".join(args)

    try:
        char = Character.generate(command_line)
    except Exception as err:  # noqa: BLE001
        import traceback
        sys.stderr.write("character generation failed: " + str(err) + "\n")
        traceback.print_exc()
        return 1

    sys.stdout.write(char.to_text_sheet())
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
