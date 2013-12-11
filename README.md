PoDiffUtils
===========

Script for functionality similar to diff/patch/merge specially tailored for
GNU Gettext PO files.

Only the 3-way merge part is implemented so far.

Installation
------------

Requirements:

 - [Python][Python] 2.7 or newer, but not 3.x (Translate Toolkit does not work with 3.x
  yet)
 - [Translate Toolkit][TT] 1.10 or newer

For now just put the podiffutils.py script somewhere and make it executable.

It still keeps it's .py extension, which allows:
 - Importing it as module from other python scripts (it's still the plan to
   integrate it to [Translate Toolkit][TT] eventually).
 - Running it with python on Windows by associating extension.

Usage
-----

So far only 3-way merge is implemented. To merge 3 files, run

     podiffutils.py merge base.po local.po remote.po

Use `-o` option to write the output to file. Use `-U` option to write the result
over second argument (local.po) as git merge driver is expected to.

To use as [Git][Git] merge driver, configure:

     [merge "po"]
     driver = podiffutils.py merge -U %O %A %B

There is special option `-n`/`--no-error` that makes it exit with 0 status
even if there were conflicts. This allows merge to succeed even if there are
conflicts, which is useful in automatically managed repositories like in
Weblate. Conflicts are only produced inside translation and the conflicted
translation is still in valid Gettext PO format, so conflicts can be dealt
with later and even using web or gui based PO editor.

Licence
-------

Like [Translate Toolkit][TT] this script is licensed under
Gnu General Public License [version 2.0][GPL-2.0] [or later][GPL].

Plans
-----

I originally planned to do this in context of [Translate Toolkit][TT]
directly, but it turned out that the internal interfaces need some
improvements to do that properly. So I first publish a stand-alone version
specific to PO files to get it some testing. If it works, I'll try to
generalize it for other formats supported by [Translate Toolkit][TT], which
will unfortunately require extending the interface of `translate.storage.*`
modules.

[Python]: http://www.python.org/
[TT]: http://toolkit.translatehouse.org/
[Git]: http://git-scm.com/
[GPL]: http://www.gnu.org/licenses/gpl.html
[GPL-2.0]: http://www.gnu.org/licenses/old-licenses/gpl-2.0.html
