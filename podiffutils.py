#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2013 Jan Hudec
#
# This file is not yet part of the Translate Toolkit.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

"""Diff, patch and 3-way merge for translation catalogs.

Variants of diffutils diff, patch and diff3/merge tuned to work on
translation catalogs by:

 - matching the entries on id, ignoring position if necessary
 - ignoring conflicts in the less important parts like location comments

Conflicts are marked msgcat way and marked fuzzy. The program optionally
exits with success even on conflicts since they can be considered valid for
many purposes. This is mainly useful to po editors like weblate that need
accepted resolution to work on.
"""

#########################################################################
# The implementation classes, to become translate.tools.difutils

from copy import deepcopy
import difflib
from itertools import chain
import re
import time

from translate.misc.multistring import multistring
from translate.storage import factory, poheader, pypo

class _Item(object):
    """Auxiliary class that holds info about merging state"""
    __slots__ = ('done',)

    def __init__(self):
        self.done = False

class _Item2(_Item):
    """Class holding two translation units for diff (old, new)"""
    __slots__ = ('old', 'new')

    def __init__(self):
        super(_Item2, self).__init__()
        self.old = None
        self.new = None

class _Item3(_Item):
    """Class holding three translation units for merge (base, local, remote)"""
    __slots__ = ('base', 'local', 'remote')

    def __init__(self):
        super(_Item3, self).__init__()
        self.base = None
        self.local = None
        self.remote = None

class _Walker(object):
    """Helper for complex iteration over iterable.

    The iteration that orders units needs to repeatedly check first element
    of iterator, so this combines iterator with current element and finished
    flag."""
    __slots__ = ('_iter', '_current', '_valid')

    def __init__(self, it):
        self._iter = iter(it)
        self._valid = True
        self.next()

    def valid(self):
        return self._valid

    def get(self):
        return self._current

    def next(self):
        if self._valid:
            try:
                self._current = next(self._iter)
            except StopIteration:
                self._current = None
                self._valid = False

class _SetMatcherBase:
    """Utilities for use with SetMatcher[23]"""
    def _fill_item_map(self, field, units):
        for unit in units:
            key = self.keyfunc(unit)
            if key in self.item_map:
                item = self.item_map[key]
            else:
                item = self.item_type()
                self.item_map[key] = item
            setattr(item, field, unit)

    def _item(self, unit):
        return self.item_map[self.keyfunc(unit)]

class SetMatcher2(_SetMatcherBase):
    """Takes two sets and generates set of pairs to be compared together,
    trying to preserve ordering as much as possible."""

    item_type = _Item2

    def __init__(self, old, new, keyfunc = (lambda x: x),
            deletedfunc = (lambda x: False)):
        self.old = old
        self.new = new
        self.keyfunc = keyfunc
        self.deletedfunc = deletedfunc
        self.item_map = dict()

    def match(self):
        self._fill_item_map('old', self.old)
        self._fill_item_map('new', self.new)

        ow = _Walker(self.old)
        nw = _Walker(self.new)

        def not_old(unit):
            i = self._item(unit)
            return i.old is None or (
                    self.deletedfunc(i.old) and
                    not self.deletedfunc(i.new))

        while ow.valid() and nw.valid():
            # we emit new units that don't exist in old if all preceeding
            # units were already emitted
            if nw.valid() and not_old(nw.get()):
                i = self._item(nw.get())
                assert not i.done
                yield (i.old, i.new)
                i.done = True
                nw.next()
            # any other units are emitted in order they appear in old
            elif ow.valid():
                i = self._item(ow.get())
                assert not i.done
                yield (i.old, i.new)
                i.done = True
                ow.next()
            # and skip emitted units in both iterators
            while nw.valid() and self._item(nw.get()).done:
                nw.next()
            while ow.valid() and self._item(ow.get()).done:
                ow.next()

        # verify we processed everything
        assert not ow.valid()
        assert not nw.valid()
        assert not [i for i in self.item_map.itervalues() if not i.done]

class SetMatcher3(_SetMatcherBase):
    """Takes three sets and generates set of tripples to be merged together,
    trying to preserve ordering as much as possible."""

    item_type = _Item3

    def __init__(self, base, local, remote, keyfunc = (lambda x: x),
            deletedfunc = (lambda x: False)):
        self.base = base
        self.local = local
        self.remote = remote
        self.keyfunc = keyfunc
        self.deletedfunc = deletedfunc
        self.item_map = dict()

    def match(self):
        self._fill_item_map('base', self.base)
        self._fill_item_map('local', self.local)
        self._fill_item_map('remote', self.remote)

        bw = _Walker(self.base)
        lw = _Walker(self.local)
        rw = _Walker(self.remote)

        def not_local(unit):
            i = self._item(unit)
            return i.local is None or (
                    self.deletedfunc(i.local) and
                    not self.deletedfunc(i.remote))

        while lw.valid() or rw.valid():
            # we emit remote units that don't exist in local if all
            # preceeding units were already emitted
            if rw.valid() and not_local(rw.get()):
                i = self._item(rw.get())
                assert not i.done
                yield (i.base, i.local, i.remote)
                i.done = True
                rw.next()
            # any other units are emitted in order they appear in local
            elif lw.valid():
                i = self._item(lw.get())
                assert not i.done
                yield (i.base, i.local, i.remote)
                i.done = True
                lw.next()
            # and skip emitted units in both iterators
            while rw.valid() and self._item(rw.get()).done:
                rw.next()
            while lw.valid() and self._item(lw.get()).done:
                lw.next()

        # emit remaining units from base
        while bw.valid():
            i = self._item(bw.get())
            if not i.done:
                yield (i.base, i.local, i.remote)
                i.done = True
            i.done = True
            bw.next()

        # verify we processed everything
        assert not lw.valid()
        assert not rw.valid()
        assert not bw.valid()
        assert not [i for i in self.item_map.itervalues() if not i.done]

class DiffUtils:
    """Abstract base class for differs. Implements comparing and merging
    stores.

    Some implementation details depend on specific storage class. Correct
    implementation can be obtained from get_differ."""

    # FIXME: Take options in __init__

    def load_storage(self, storefile):
        store = factory.getobject(storefile, classes_str=_file_classes)
        if not isinstance(store, self.FileClass):
            raise ValueError('All files have to be in format the same format %s, but %s is in %s' % (
                self.FileClass.Name, store.filename, store.Name))
        return store

    # todo load_patch

    def merge(self, base, local, remote):
        out = self.FileClass()
        conflicts = 0
        del out.units[:] # delete header; we'll create it if the inputs have it
        matcher = SetMatcher3(base.units, local.units, remote.units,
                keyfunc=base.UnitClass.getid,
                deletedfunc=base.UnitClass.isobsolete)
        headers = []
        normal = []
        obsolete = []
        for bu, lu, ru in matcher.match():
            u, c = self.merge_unit(bu, lu, ru)
            if u is not None:
                assert isinstance(u, out.UnitClass)
                if u.isheader():
                    headers.append(u)
                elif u.isobsolete():
                    obsolete.append(u)
                else:
                    normal.append(u)
            conflicts += c
        # the set matcher might occasionally produce incorrect order, so
        # force it
        for u in chain(headers, normal, obsolete):
            out.addunit(u)
        return out, conflicts

    def clone_unit(self, unit):
        return deepcopy(unit)

    # abstract empty_unit(self, template)

    # abstract _merge_unit(self, base, local, remote)

    def merge_unit(self, base, local, remote):
        # Handle deletion and creation generically.
        # This only concerns the case where the unit does not exist at all;
        # cases where the unit is merely obsolete is handled by treating
        # obsolete as just another property!
        # FIXME: Special treatment for header needed!
        assert base is not None or local is not None or remote is not None
        if base is None: # creation
            if remote is None:
                return self.clone_unit(local), 0
            if local is None:
                return self.clone_unit(remote), 0
            return self._merge_unit(self.empty_unit(local), local, remote)
        if remote is None: # deletion
            u = self.clone_unit(local)
            if not base.isobsolete():
                u.makeobsolete() # only if not resurrected in local
            return u, 0
        if local is None:
            u = self.clone_unit(remote)
            if not base.isobsolete():
                u.makeobsolete()
            return u, 0
        # None of them is None. They can be obsolete, but that has to be
        # handled as part of translation handling while comments and stuff
        # still need to be merged.
        return self._merge_unit(base, local, remote)

    def merge_simple(self, base, local, remote):
        """Merges scalar where there cannot be conflict.

        There are two important cases where conflict cannot occur:

         - Boolean flag.
         - Element in merged set, which while having some value, it is only
           either present or absent in each side and thus only one non-None
           value is posible.
        """
        if base == remote:
            return local
        if base == local:
            return remote
        if local == remote: # both sides did the same change
            return local
        raise ValueError("merge_simple does not handle conflicts (%r, %r, %r)" % (
            base, local, remote))

    def merge_list(self, base, local, remote):
        "Merges list as set in a simple wey where complete value iskey."
        matcher = SetMatcher3(base, local, remote)
        return [o for o in (self.merge_simple(b, l, r) for b, l, r in
            matcher.match()) if o is not None]

# TODO: This should be mostly added to translate.storage.pypo and in
# a compatible way to other translate.storage.* classes.
class _PoFileDiff(DiffUtils):
    FileClass = pypo.pofile

    def empty_unit(self, template):
        unit = type(template)()
        unit.setsource(template.getsource())
        unit.setcontext(template.getcontext())
        return unit

    def _equal_translation(self, left, right):
        # fuzzy and non-fuzzy are considered different except for blank
        # translation. We can't use istranslated, because it also considers
        # isobsolete and isheader for po files.
        return (left.target == right.target
                and (left.isfuzzy() == right.isfuzzy()
                    or not bool(left.target)))

    # we don't include fuzzy here; it is handled separately
    def _get_types(self, unit):
        return [t for t in
                re.findall(r"\b[-\w]+\b", "\n".join(unit.typecomments))
                if t != "fuzzy"]

    def _set_types(self, unit, types):
        if len(types):
            unit.typecomments = ["#, %s\n" % ", ".join(types)]
        else:
            unit.typecomments = []

    def _merge_unit(self, base, local, remote):
        out = self.empty_unit(local)
        for l in self.merge_list(
                base.getlocations(),
                local.getlocations(),
                remote.getlocations()):
            out.addlocation(l)
        # XXX: The way of merging comments as lists of lines is somewhat
        # strange.
        for n in self.merge_list(
                base.getnotes(origin='developer').split('\n'),
                local.getnotes(origin='developer').split('\n'),
                remote.getnotes(origin='developer').split('\n')):
            out.addnote(n, origin='developer')
        for n in self.merge_list(
                base.getnotes(origin='translator').split('\n'),
                local.getnotes(origin='translator').split('\n'),
                remote.getnotes(origin='translator').split('\n')):
            out.addnote(n, origin='translator')
        self._set_types(out,
                self.merge_list(
                        self._get_types(base),
                        self._get_types(local),
                        self._get_types(remote)))
        if self.merge_simple(base.isobsolete(), local.isobsolete(),
                remote.isobsolete()):
            out.makeobsolete()

        if local.isheader():
            c = self._merge_header(out, base, local, remote)
        else:
            c = self._merge_target(out, base, local, remote)
        return out, c

    _time_pattern = re.compile(r'([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})\s+'
            + r'([0-9]{1,2}):([0-9]{1,2})(?::[0-9]{1,2})?\s*([+-][0-9]{2})([0-9]{2})')

    def _get_time(self, timestr):
        m = self._time_pattern.match(timestr)
        if m:
            t = time.mktime((
                        int(m.group(1)), # year
                        int(m.group(2)), # month
                        int(m.group(3)), # day
                        int(m.group(4)), # hour
                        int(m.group(5)), # minute
                        0, # second
                        0, # weekday
                        0, # yearday
                        0)) # not DST
            t = t + time.timezone # + time.timezone converts TO UTC
            t = t + int(m.group(6)) * 3600 + int(m.group(6)) * {
                    '+': 60, '-': -60 }[m.group(6)[0]]
            return t
        else:
            return 0

    _template_headers = set((
        "Project-Id-Version",
        "Report-Msgid-Bugs-To",
        "POT-Creation-Date",
        "Language-Team",
        ))

    def _merge_header(self, out, base, local, remote):
        def newer(left, right, attribute):
            if self._get_time(left.get(attribute)) >= self._get_time(right.get(attribute)):
                return True
            else:
                return False

        base_dict = poheader.parseheaderstring(base.target)
        local_dict = poheader.parseheaderstring(local.target)
        remote_dict = poheader.parseheaderstring(remote.target)
        out.target = ''
        c = 0

        allkeys = self.merge_list(base_dict.keys(),
                local_dict.keys(), remote_dict.keys())
        for key in allkeys:
            b = base_dict.get(key, None)
            l = local_dict.get(key, None)
            r = remote_dict.get(key, None)
            if b == l:
                res = r
            elif b == r or l == r:
                res = l
            else: # conflict...
                if key in self._template_headers:
                    use_local = newer(local_dict, remote_dict, 'POT-Creation-Date')
                else:
                    use_local = newer(local_dict, remote_dict, 'PO-Revision-Date')
                if use_local:
                    used, other, ofile = local_dict, remote_dict, remote
                else:
                    used, other, ofile = remote_dict, local_dict, local

                res = used.get(key, None)
                out.addnote(u'(conflict) %(file)s (%(project)s): %(key)s: %(value)s' % {
                    'file': getattr(ofile._store, 'filename', ('remote' if use_local else 'local')),
                    'project': other.get('Project-Id-Version', u'???'),
                    'key': key,
                    'value': other.get(key, u'<unset>'),
                    })
                c = 1
            if res is not None:
                out.target += '%s: %s\n' % (key, res)
        out.markfuzzy(
                self.merge_simple(base.isfuzzy(), local.isfuzzy(),
                        remote.isfuzzy()))
        return c

    def _merge_target(self, out, base, local, remote):
        # Comments were easy. Now we have to decide from which side we want
        # the translation from and the other things like previous msgid and
        # fuzzy go with it.
        def set_translation_from(unit):
            out.target = unit.target
            if unit.prev_msgid:
                out.prev_msgctxt = unit.prev_msgctxt
                out.prev_msgid = unit.prev_msgid
                out.prev_msgid_plural = unit.prev_msgid_plural
            out.markfuzzy(unit.isfuzzy())

        # First this is 3-way merge, so change trumphs no change.
        if self._equal_translation(base, local):
            set_translation_from(remote)
        elif self._equal_translation(base, remote):
            set_translation_from(local)
        # Same change on both sides is trivial.
        elif self._equal_translation(local, remote):
            set_translation_from(local)
        # Now starts conflict resolution.
        else:
            lqual = 0 if local.isblank() else 1 if local.isfuzzy() else 2
            rqual = 0 if remote.isblank() else 1 if remote.isfuzzy() else 2
            if lqual > rqual:
                set_translation_from(local)
            elif rqual > lqual:
                set_translation_from(remote)
            else:
                ls = getattr(local.target, "strings", [local.target])
                rs = getattr(remote.target, "strings", [remote.target])
                tmpl = (u"#-#-#-#-#  %s (%s)  #-#-#-#-#\n" +
                        u"%%s\n" +
                        u"#-#-#-#-#  %s (%s)  #-#-#-#-#\n" +
                        u"%%s\n") % (
                                getattr(local._store, 'filename', 'local'),
                                local._store.parseheader().get("Project-Id-Version", u"???"),
                                getattr(remote._store, 'filename', 'remote'),
                                remote._store.parseheader().get("Project-Id-Version", u"???"))
                while len(ls) < len(rs):
                    ls.append(u"")
                while len(rs) < len(ls):
                    rs.append(u"")
                if local.hasplural():
                    out.target = multistring([tmpl % (l, r) for l, r in zip(ls, rs)])
                else:
                    out.target = tmpl % (ls[0], rs[0])
                out.markfuzzy()
                return 1 # conflict
        return 0

_differs = {
        'pofile': _PoFileDiff
        }

_file_classes = {
        # This is a reason we have custom class list: we can only work with
        # pypo and not cpo and fpo. The reason is that libgettextpo does not
        # provide any method to get list of all type comments. So we use
        # translate.storage.pypo.pyfile explicitly and rely on it's actual
        # properties rather than the incomplete generic interface.
        'po': ('pypo', 'pofile'), 'pot': ('po', 'pofile'),
        }

def get_differ(_class):
    """Return diffutils implementation suitable for working with given file.

    This returns a concrete implementation of DiffUtils interface.
    """
    if _class.__name__ in _differs:
        return _differs[_class.__name__]
    else:
        raise ValueError("DiffUtils is not implemented for %s"
                % (_class.Name))

#########################################################################
# The user-level commadns, to be split in individual commands in
# translate.tools
from argparse import ArgumentParser, FileType
import sys

# FIXME: temporary - the load_storage is messed up
from translate.storage.pypo import pofile

def merge(args):
    """3-way merge translation catalogs.

    Entries are matched by their id/context+source (depending on catalog type).
    Content is preserved as far as possible/practical so that reordering can't
    cause conflicts.
    """
    if args.update:
        args.out = args.local

    # FIXME: Use the auto-detection at least a bit
    differ = get_differ(pofile)() # FIXME: pass options
    base = differ.load_storage(args.base)
    local = differ.load_storage(args.local)
    remote = differ.load_storage(args.remote)

    out, conflicts = differ.merge(base=base, local=local, remote=remote)

    out.savefile(file(args.out, 'w') if args.out else sys.stdout)
    if conflicts and not args.succeed:
        sys.exit(1)

def main():
    parser = ArgumentParser(description=__doc__)

    subparsers = parser.add_subparsers()
    mergeparser = subparsers.add_parser('merge', description=merge.__doc__)
    mergeparser.set_defaults(function=merge)
    mergeparser.add_argument('-n', '--no-error', dest='succeed',
            action='store_true',
            help='exit with 0 status even if there are conflicts')
    outgrp = mergeparser.add_mutually_exclusive_group()
    outgrp.add_argument('-o', '--out', '--output', dest='out',
            help='output file (defaults to standard output)')
    outgrp.add_argument('-U', '--update', dest='update',
            action='store_true', help='write output over local')
    mergeparser.add_argument('base', help='base of the 3-way merge')
    mergeparser.add_argument('local',
            help='the file to be merged to')
    mergeparser.add_argument('remote',
            help='the file to be merged from')

    args = parser.parse_args()
    args.function(args)

if __name__ == '__main__':
    main()
