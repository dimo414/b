# `b`, a distributed bug tracker extension for Mercurial

Version 0.6.0

## Introduction:
    
Based off and built using Steve Losh's brilliantly simple task manager
[`t`](http://stevelosh.com/projects/t/) the fundamental principle is 
'Get things done, not organized', and tries to follow `t`'s message,
"the only way to make your bug list prettier is to fix some damn bugs."
    
That said, `b` has many powerful additions to `t`, without any of the bloat
and burden of setting up, maintaining, or using a traditional bug tracker.
    
You can use `b` exactly like `t`, add, rename, resolve, and list work almost
exactly like `t` out of the box, with the added benefit that wherever you are in
a repository, you maintain a single bugs database in the root of the repository.

But you can do more with `b`.  You can reopen issues, the edit, details, and
comment commands allow you to track additional information about the bugs,
like stack traces and expected results, and whatever other information you'd
like.  The details file is a plain text file, and can contain any content you desire.

You can also assign bugs to specific individuals - either based on their
Mercurial commit names or not - and list lets you filter by owner to see what
tasks are in your care.

`b` is powerful enough to support several different workflow complexities,
from an individual just tracking tasks in a repository, all the way up to a
small, distributed team of managers and developers who need to be able to
report, manage, and assign bugs, tasks, and issues, share details, and
express their opinions.

However, `b` is not intended to be be a replacement for large scale
bug trackers like Jira, Bugzilla, and the upcoming Bugs Everywhere.  Most
notably, (at present) `b` is just a command line tool.  There is no
centralized bug list or web access, nor any GUI interface, and many of the
features in such larger projects are lacking, notably any kind of warning or
notification when a bug is reassigned, and the ability to categorize bugs and
to provide resolution reasons, like fixed or duplicate - of course these could
all be done manually, but there is no such built in functionality.

If you need the power of something like Bugzilla, you're going to find `b`
limited.  However if you find many of the extra "features" in these larger
tools to be unhelpful bloat, and you don't want to waste time organizing,
categorizing, and sorting and instead want a quick, easy way to track issues
with your project with minimal setup and configuration, then `b` is the tool to use!

### Some Suggested Use Cases:

A single developer, working on a small project, can turn that into a version
controlled project with a simple 'hg init'.  With `b` installed, he (or she) also
gets a fully functional bug tracker to boot, no additional setup required!
As soon as you install `b`, every repository on your machine now has issue
tracking functionality ready to use.

Working on a website, you could very easily (and I might do this myself 
soon enough) write a little PHP script which takes bug reports and
logs them to `b`.  I often find the closer to my workflow a tool is
the easier it is to use, so integrating it right into the website
makes a lot of sense.

Working on a small project with a few other team members is ideal for `b`,
it's powerful enough to let everyone track what they need to do, and allow
everyone to contribute what they can to any of the bugs on file.  They can
search titles for matching bugs, and even grep through the details directory
to find details matching what they're looking for.

Working on a larger project with lots of team members starts getting questionable,
as many of the powerful features larger projects provide start to really show
their worth.  However in my experience several large companies I've worked for
or with have drastically underutilized the power of their bug trackers, to the 
point where all the complexity and extra metadata is just wasted space and fluff.
That's not to say that `b` is necessarily a good alternative for a large company,
but it's worth asking yourself if you really benefit from all the extra tools;
many organizations could get by just fine with the features `b` provides.

## Installing `b`:
    
Like any Mercurial Extension, to install `b` edit a Mercurial config file
and add the following:
    
    [extensions]
    b=/path/to/b.py
    
See the Mercurial wiki (http://mercurial.selenic.com/wiki/UsingExtensions)
for more details on installing extensions.

`b` is a zero-configuration tool - as soon as it is installed, every single
repository is ready to start tracking issues, without any additional setup.
You may find it helpful to specify a username for yourself in your `~/.hgrc`
file, however this is absolutely not necessary to work with `b`.

## Config Options:
        
`b` has two configuration settings, both of which are optional, and should
be put in the `[bugs]` section of any Mercurial config file.

* `user`

    You can specify a user name for bug tracking, or 'hg.user' if you wish
    to use your commit name.  The bug tracker will work absolutely fine
    without this setting, but it is recommended if you will be working
    with multiple people.
    
* `dir`

    Allows you to specify (relative to the repo root) where the bugs
    database should go.  The default is '.bugs'
        
Using `b`:
    
You're encouraged to read the documentation on [`t`](http://stevelosh.com/projects/t/)
before using `b` - much of the functionality and usage philosophy of `t` is
carried over here. 

All `b` commands take the form `hg b command [options/parameters]`.  You
can see a full list and command signatures by running `hg help b`.

When you're anywhere within a repository with the `b` extension enabled
you can use `b`.  To file a new bug, all you have to do is say:

    % hg b add 'This is a new bug'

And you can confirm it's been added by calling:

    % hg b list

Which will show you your new bug, along with an ID to refer to it by.  These
IDs are actually prefixes of the full bug ID, and will get longer as more bugs
are added.  If you need a permanent reference to a bug, you can pass a prefix to

    % hg b id ID

This will return the full ID of the bug.  You'll likely only ever need the first
eight or so characters - a database of 20,000+ bugs only used the first four or five
in most cases.

To rename a bug, you can call:

    % hg b rename ID 'NEW NAME HERE'

And like `t`'s edit command, you can use sed style replacements if you so desire.

When you're finished with a bug, simply call

    % hg b resolve ID

and it will be marked resolved and no longer (by default) show up in your bug list.
Use 'reopen' in the same fashion if you decide to reopen a closed bug.

If you need to record more detail than just a title, edit

    % hg b edit ID

will launch your default commit editor with a pre-populated set of sections you can
fill out.  Nothing is mandatory, and you can create or delete new sections as you'd
like.  Comments (see below) are appended to the end of the file, so it is suggested
you leave the comments section last.

To view the details of a bug you call:

    % hg b details ID

This provides some basic metadata like date filed and owner, along with the contents
of the details file, if it exists.  Any sections (denoted by text in square brackets)
which are empty are not displayed by the details command to simplify the output.

If you want to add a comment to a bug, like feedback or an update on its status,

    % hg b comment ID 'COMMENT TEXT'

will append your comment to the details file along with the date and, if set,
your username (see below)

To manage multi-user projects, you can set a bug username (see the Config Options
section above for how to do that) to associate with bugs, and say something like

    % hg b assign ID 'John Cleese'

If the specified username can't be found in the database, you'll be prompted to 
confirm that is the name you want to use, with the '-f' flag.  For ease of
assigning bugs, you can use a prefix of a user's name, and as long as it's not
ambiguous, `b` will assign it to the matching username, and let you know
who it was ultimately assigned to so you can double check.  Assuming no other
users named John, calling:

    % hg b assign ID john

would have the same effect as the call above.  The special name 'me' will
assign the bug to your username, and the special name 'Nobody' will mark the bug
as unassigned.

To see a list of all users `b` is currently aware of, and the number of open
bugs assigned to them, you can call:

    % hg b users

Finally, `list` has some advanced functionality that's worth knowing.


* `-r` will list resolved bugs, instead of open bugs.
* `-o` takes a username (or a username prefix) and lists bugs owned by the
  specified user.
* `-g` will list bugs which contain the specified text in their title.
* `-a` will sort issues alphabetically, and
* `-c` will sort them chronologically.

These flags can be used together for fairly granular browsing of your
bugs database.  In addition, you can use the `-T` flag to truncate
output that would otherwise overflow beyond one line.


The read-only commands (`list`, `details`, `users`, and `id`) have an additional `--rev`
option that can be used to run that command against a committed revision of the bug
database.  To see the list of issues open at the time of this release for
instance, you could run 

    hg b list --rev 6.0-rc-2
    
## FAQ:

* How well does `b` scale?
 
    Basic benchmarks indicate that `b` performs well even with very large lists.
    test bug lists of more than 50,000 records have been constructed and `b` 
    responds very quickly, taking just a second or two to add a record,
    and even less time to list bugs, especially filtering by owner or by 
    grep. Of course, you would have to work very hard to ever reach a bug
    list even close to that number, and long before you get there you'll
    likely discover you need to switch to something more powerful, so for
    all intents and purposes `b` should handle everything you can throw at it.
        
* I would really like to be able to categorize my bugs, or detail how the bug
  was resolved, why isn't that possible?
  
    `b` is philosophically opposed to tracking this sort of data, and is not
    trying to replace large scale, metadata driven bug trackers.
    If you find yourself wishing it had these sorts of features, you may
    very well be looking at the wrong product.  However, you could certainly
    add such data to the details file, or add flags like P1 or BLOCKING to
    issue titles if you felt the need to do so.  Users have reported finding
    this workflow - combined with list's -g flag, fairly satisfactory.
    
* Can I use standard Mercurial commands inside the `.bugs` directory?
 
    Absolutely.  Everything in the `.bugs` directory is a standard text file,
    enabling easy merging, diffing, grepping, annotating, browsing, and data
    mining.  If you feel so inclined, you can even edit any of the files in
    the .bugs directory manually.
    
* Why doesn't `b` commit my changes?
 
    `b` does not commit after bugs are filed or changed intentionally.  
    The hope is that `b` acts completely transparently to the underlying 
    repository, and that commits are never solely about bugs (unless the
    user chooses so).  This allows the repository structure and the commit 
    messages to remain concerned with the source code, and not have it fill
    up with uninformative messages about every little thing you do with `b`.
    It does however automatically add everything located in the bugs directory
    so you shouldn't have to worry about ever leaving anything untracked.
    Be careful that you don't accidentally check in .orig or .rej files that
    Mercurial sometimes creates in the bugs directory, they would also be
    added automatically.

* Is `b` ever going to work with other DVCS?
 
    `b` was built to be as compartmentalized from the Mercurial API
    calls as possible, and while there are no plans at present to
    expand `b` to work with other DVCS, the structure to do so exists.
    
* Does `b` work with unicode or other encodings beyond ASCII?
 
    There is an open bug (bug 286b) to improve `b`'s handling of
    non-ASCII character sets, however at present you may run into trouble
    tracking issues in other languages or encodings.  Ensuring that
    issues created and updated in arbitrary encodings continue to be
    editable and viewable on machines with other encodings is a
    non-trivial task, and likely cannot be fully resolved until
    a future release of Mercurial provides more robust encoding
    transformation utilities.  Patches to improve this issue are
    very welcome.
    
* Can I use `b` in a corporate environment?
 
    `b` is released under GPL2+ so yes, you may.  However you may
    not distribute `b` or any derived works under any other license 
    than the GPL2+.  If you're unsure of what you can or cannot do,
    there's lots of information on the details of this license online,
    and you are welcome to contact me with questions.

* I have an idea for a feature, or a bug to report, what should I do?
 
    `b` is released as open source software, so experiment, make or
    fix it yourself if you feel so inclined.  You're also welcome
    to email me with suggestions, questions or code changes.  Or
    even pull the repository, file a bug there, and serve it up
    somewhere for me to pull it back!  How's that for dogfooding?
        
I hope you find `b` useful!

## Copyright

Copyright 2010-2012 Michael Diamond

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.