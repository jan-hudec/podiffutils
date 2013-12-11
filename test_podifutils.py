#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

import podiffutils

from translate.misc.wStringIO import StringIO
from translate.storage.pypo import pofile

def test_set_matcher3():
    """Simple test for the set matcher."""
    base = ['a', 'b', 'c', 'd']
    local = ['a', 'c', 'b', 'e', '~d']
    remote = ['b', 'c', '~d', '~a']

    def keyfunc(x):
        return x[1:] if x.startswith('~') else x
    def deletedfunc(x):
        return x.startswith('~')

    merger = podiffutils.SetMatcher3(base, local, remote, keyfunc,
            deletedfunc)
    
    exp = [
            ('a', 'a', '~a'),
            ('c', 'c', 'c'),
            ('b', 'b', 'b'),
            (None, 'e', None),
            ('d', '~d', '~d'),
            ]
    res = list(merger.match())
    assert exp == res

def do_test_po_merge(basetext, localtext, remotetext, expectedtext,
        expectedconflicts=0):
    differ = podiffutils.get_differ(pofile)()

    def load_string(string):
        stream = StringIO(string)
        return differ.load_storage(stream)

    out, c = differ.merge(base=load_string(basetext),
            local=load_string(localtext),
            remote=load_string(remotetext))
    assert expectedtext == str(out)
    assert expectedconflicts == c

def test_po_add():
    """Test different additions in the same place."""
    do_test_po_merge(
'''msgid "foo"
msgstr "foo"
''',
'''msgid "foo"
msgstr "foo"

msgid "bar"
msgstr "bar"
''',
'''msgid "foo"
msgstr "foo"

msgid "baz"
msgstr "baz"
''',
'''msgid "foo"
msgstr "foo"

msgid "baz"
msgstr "baz"

msgid "bar"
msgstr "bar"
''')

def test_po_change_translation():
    """Test changing translation on one or the other side."""
    do_test_po_merge(
'''msgid "original"
msgstr "translation"
''',
'''msgid "original"
msgstr "translation"
''',
'''msgid "original"
msgstr "modified"
''',
'''msgid "original"
msgstr "modified"
''')
    do_test_po_merge(
'''msgid "original"
msgstr "translation"
''',
'''msgid "original"
msgstr "modified"
''',
'''msgid "original"
msgstr "translation"
''',
'''msgid "original"
msgstr "modified"
''')

def test_po_conflict():
    """Test basic conflict in translations."""
    do_test_po_merge(
'''msgid "foo"
msgstr "bar"
''',
'''msgid "foo"
msgstr "baz"
''',
'''msgid "foo"
msgstr "qyzzy"
''',
r'''#, fuzzy
msgid "foo"
msgstr ""
"#-#-#-#-#  local (???)  #-#-#-#-#\n"
"baz\n"
"#-#-#-#-#  remote (???)  #-#-#-#-#\n"
"qyzzy\n"
''',
1)

def test_po_delete():
    """Test full deletion."""
    do_test_po_merge(
'''msgid "foo"
msgstr "FOO"

msgid "bar"
msgstr "bar"
''',
'''msgid "foo"
msgstr "FOO"

msgid "bar"
msgstr "BAR"
''',
'''msgid "foo"
msgstr "FOO"
''',
'''msgid "foo"
msgstr "FOO"

#~ msgid "bar"
#~ msgstr "BAR"
''')

def test_po_obsolete():
    """Test obsolescense."""
    do_test_po_merge(
'''msgid "foo"
msgstr "FOO"
''',
'''#~ msgid "foo"
#~ msgstr "FOO"
''',
'''#, fuzzy
msgid "foo"
msgstr "Foo!"
''',
'''#, fuzzy
#~ msgid "foo"
#~ msgstr "Foo!"
''')

def test_po_resurrect():
    '''Test resurrection.'''
    do_test_po_merge(
'''#~ msgid "foo"
#~ msgstr "Foo"
''',
'''msgid "foo"
msgstr "Foo"
''',
'''#~ msgid "foo"
#~ msgstr "FOO"
''',
'''msgid "foo"
msgstr "FOO"
''')

def test_po_prefer_nonfuzzy():
    """Test prefering non-fuzzy translation."""
    do_test_po_merge(
'''msgid "foo"
msgstr ""
''',
'''#, fuzzy
msgid "foo"
msgstr "Foo"
''',
'''msgid "foo"
msgstr "FOO"
''',
'''msgid "foo"
msgstr "FOO"
''')

def test_po_markfuzzy():
    """Change to fuzzy vs. no change is change to fuzzy.

    It still has to be proper 3-way merge!
    """
    do_test_po_merge(
'''msgid "foo"
msgstr "FOO"
''',
'''#, fuzzy
msgid "foo"
msgstr "Foo"
''',
'''msgid "foo"
msgstr "FOO"
''',
'''#, fuzzy
msgid "foo"
msgstr "Foo"
''')

def test_locations():
    """Test combining locations."""
    do_test_po_merge(
'''#: here:4 there:5
msgid "foo"
msgstr "bar"
''',
'''#: there:5 here:8
msgid "foo"
msgstr "bar"
''',
'''#: here:4 there:8
msgid "foo"
msgstr "bar"
''',
'''#: there:8
#: here:8
msgid "foo"
msgstr "bar"
''')

def test_comments():
    """Test combining comments."""
    do_test_po_merge(
'''# this is a
# rather silly
# comment
#. Translator, please
#. make a silly comment.
msgid "foo"
msgstr "bar"
''',
'''# this is a
# rather silly comment
#. Translator, please
#. make a silly comment.
msgid "foo"
msgstr "bar"
''',
'''# a really silly
# comment
#. Translator, please
#. DON'T make silly comments.
msgid "foo"
msgstr "bar"
''',
'''# a really silly
# rather silly comment
#. Translator, please
#. DON'T make silly comments.
msgid "foo"
msgstr "bar"
''')

def test_types():
    """Test combining type flags."""
    do_test_po_merge(
'''#, python-brace-format
msgid "{foo}++"
msgstr "{foo}*"
''',
'''#, java-format
msgid "{foo}++"
msgstr "{foo}*"
''',
'''#, python-brace-format, no-c-sharp-format
msgid "{foo}++"
msgstr "{foo}*"
''',
'''#, no-c-sharp-format, java-format
msgid "{foo}++"
msgstr "{foo}*"
''')

def test_parallel_creation():
    """Test independent creation of the same entries."""
    do_test_po_merge(
'''msgid "foo"
msgstr "Foo"
''',
'''msgid "bar"
msgstr "Bar"

msgid "foo"
msgstr "Foo"
''',
'''msgid "bar"
msgstr "Bar"

msgid "foo"
msgstr "Foo"
''',
'''msgid "bar"
msgstr "Bar"

msgid "foo"
msgstr "Foo"
''')


def test_simple_header():
    """Test simple merging of header."""
    do_test_po_merge(
r'''
# SOME DESCRIPTIVE TITLE.
# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER
# This file is distributed under the same license as the PACKAGE package.
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: 2013-12-11 11:30+0100\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: LANGUAGE <LL@li.org>\n"
"Language: \n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
r'''
# The Project.
# Copyright (C) 2013 A.U.Thor
# This file is distributed under the same license as the PACKAGE package.
# A.U.Thor <author@wherever>, 2013.
msgid ""
msgstr ""
"Project-Id-Version: Package -42\n"
"Report-Msgid-Bugs-To: /dev/null\n"
"POT-Creation-Date: 2013-12-11 11:30+0100\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
r'''
# SOME DESCRIPTIVE TITLE.
# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER
# This file is distributed under the same license as the PACKAGE package.
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: 2013-12-11 11:30+0100\n"
"PO-Revision-Date: 2013-12-11 11:40+0100\n"
"Last-Translator: Trans Lator <trans.lator@wherever>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
r'''# The Project.
# Copyright (C) 2013 A.U.Thor
# This file is distributed under the same license as the PACKAGE package.
# A.U.Thor <author@wherever>, 2013.
msgid ""
msgstr ""
"Project-Id-Version: Package -42\n"
"Report-Msgid-Bugs-To: /dev/null\n"
"POT-Creation-Date: 2013-12-11 11:30+0100\n"
"PO-Revision-Date: 2013-12-11 11:40+0100\n"
"Last-Translator: Trans Lator <trans.lator@wherever>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"

#: test.c:2
msgid "foo"
msgstr ""
''')

def test_header_conflicts():
    """Test conflicts in header."""
    do_test_po_merge(
r'''# The Project.
# Copyright (C) 2013 A.U.Thor
# This file is distributed under the same license as the PACKAGE package.
# A.U.Thor <author@wherever>, 2013.
msgid ""
msgstr ""
"Project-Id-Version: Package -42\n"
"Report-Msgid-Bugs-To: /dev/null\n"
"POT-Creation-Date: 2013-12-11 11:30+0100\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language: \n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
r'''# The Project.
# Copyright (C) 2013 A.U.Thor
# This file is distributed under the same license as the PACKAGE package.
# A.U.Thor <author@wherever>, 2013.
msgid ""
msgstr ""
"Project-Id-Version: Package -41\n"
"Report-Msgid-Bugs-To: /dev/zero\n"
"POT-Creation-Date: 2013-12-11 11:40+0100\n"
"PO-Revision-Date: 2013-12-11 11:50+0100\n"
"Last-Translator: Trans Lator <trans.lator@wherever>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"X-Whatever: this\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
r'''# The Project.
# Copyright (C) 2013 A.U.Thor
# This file is distributed under the same license as the PACKAGE package.
# A.U.Thor <author@wherever>, 2013.
msgid ""
msgstr ""
"Project-Id-Version: Package -40\n"
"Report-Msgid-Bugs-To: /dev/null\n"
"POT-Creation-Date: 2013-12-11 11:50+0100\n"
"PO-Revision-Date: 2013-12-11 11:40+0100\n"
"Last-Translator: Previous Lator <previous.lator@wherever>\n"
"Language: cs_CZ\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"X-Whatever: that\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
r'''# The Project.
# Copyright (C) 2013 A.U.Thor
# This file is distributed under the same license as the PACKAGE package.
# A.U.Thor <author@wherever>, 2013.
# (conflict) local (Package -41): Project-Id-Version: Package -41
# (conflict) local (Package -41): POT-Creation-Date: 2013-12-11 11:40+0100
# (conflict) remote (Package -40): PO-Revision-Date: 2013-12-11 11:40+0100
# (conflict) remote (Package -40): Last-Translator: Previous Lator <previous.lator@wherever>
# (conflict) remote (Package -40): Language: cs_CZ
# (conflict) remote (Package -40): X-Whatever: that
msgid ""
msgstr ""
"Project-Id-Version: Package -40\n"
"Report-Msgid-Bugs-To: /dev/zero\n"
"POT-Creation-Date: 2013-12-11 11:50+0100\n"
"PO-Revision-Date: 2013-12-11 11:50+0100\n"
"Last-Translator: Trans Lator <trans.lator@wherever>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"X-Whatever: this\n"

#: test.c:2
msgid "foo"
msgstr ""
''',
1)
