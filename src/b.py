# b.py - Distributed Bug Tracker Extention for Mercurial
#
# Copyright 2010-2011 Michael Diamond <michael@digitalgemstones.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.
# http://www.gnu.org/licenses/licenses.html
# http://www.gnu.org/licenses/gpl.html

""" A lightweight distributed bug tracker for Mercurial based projects

"The only way to make your bug list prettier is to fix some damn bugs."

b is a lightweight distributed bug tracker.  Stripped of many of the
enterprise level bloat features common in larger bug systems, b
lets you track issues, bugs, and features without being bogged down
in extra metadata that is ultimately completely unhelpful.

b has functionality to add, rename, list, resolve and reopen bugs
and keep everything as simple as a single line of text describing each one.

But if and when you need more than that, b scales cleanly to allow
you to add details that can't be properly contained in a concise title
such as stack traces, line numbers, and the like, and allows you to
add comments to bugs as time goes on.

b also works with teams, allowing you to assign bugs to different users
and keep track of bugs assigned to you.

However, b is a lightweight tool, and if there are additional features
you know you need but aren't described here, it may not be the tool for you.
See the README file for more details on what you can, and can't, do with b.
"""

#
# Imports
#
import errno
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import date, datetime
from operator import itemgetter
from mercurial.error import Abort
from mercurial.i18n import _
from mercurial import hg, commands, registrar

#
# Version Info
#
_version_num = (0, 7, 0)
_build_date = date(2018, 10, 19)


#
# Exceptions
#
class Error(Exception):
    """Base class for exceptions in this module."""

    def __init__(self, msg):
        super(Error, self).__init__(msg)
        self.msg = msg


class RequiresPrefix(Error):
    """Raised by CLI when a prefix is required."""

    def __init__(self):
        super(RequiresPrefix, self).__init__(_(
            "You need to provide an issue prefix. "
            "Run list to get a unique prefix for the bug you are looking for."))


class UnknownPrefix(Error):
    """Raised when trying to use a prefix that does not match any tasks."""

    def __init__(self, prefix):
        super(UnknownPrefix, self).__init__(_(
            "The provided prefix (%s) could not be found in the bugs database.")
                                            % prefix)
        self.prefix = prefix


class AmbiguousPrefix(Error):
    """Raised when trying to use a prefix that could identify multiple tasks."""

    def __init__(self, prefix):
        super(AmbiguousPrefix, self).__init__(_(
            "The provided prefix - %s - is ambiguous, and could point to "
            "multiple bugs. Run list to get a unique prefix for the bug you "
            "are looking for.") % prefix)
        self.prefix = prefix


class AmbiguousUser(Error):
    """Raised when trying to use a prefix that could identify multiple users."""

    def __init__(self, user, matched):
        super(AmbiguousUser, self).__init__(
            _("The provided user - %s - matched more than one user: %s") % (
                user, ', '.join(matched)))
        self.user = user
        self.matched = matched


class UnknownUser(Error):
    """Raised when trying to use a user prefix that does not match any users."""

    def __init__(self, user):
        super(UnknownUser, self).__init__(_(
            "The provided user - %s - did not match any users in the system. "
            "Use -f to force the creation of a new user.") % user)
        self.user = user


class AmbiguousCommand(Error):
    """Indicates the given command prefix matches more than one command."""

    def __init__(self, cmds):
        super(AmbiguousCommand, self).__init__(
            _("Command ambiguous between: %s") % ', '.join(cmds))
        self.cmds = cmds


class UnknownCommand(Error):
    """Raised when trying to run an unknown command."""

    def __init__(self, cmd):
        super(UnknownCommand, self).__init__(_("No such command '%s'") % cmd)
        self.cmd = cmd


class InvalidCommand(Error):
    """Raised when command invocation is invalid, e.g. incorrect options."""

    def __init__(self, reason):
        super(InvalidCommand, self).__init__(_("Invalid command: %s") % reason)
        self.reason = reason


class InvalidInput(Error):
    """Raised when the input to a command is somehow invalid - for example,
    a username with a | character will cause problems parsing the bugs file."""

    def __init__(self, reason):
        super(InvalidInput, self).__init__(_("Invalid input: %s") % reason)
        self.reason = reason


#
# Helper Methods - often straight from t
#
def _datetime(timestamp=None):
    """Returns a formatted string of the time from a timestamp,
    or now if called with no arguments"""
    if timestamp:
        t = datetime.fromtimestamp(float(timestamp))
    else:
        t = datetime.now()
    return t.strftime("%A, %B %d %Y %I:%M%p")


def _hash(*args):
    """Return a hash of the given text for use as an id.
    
    Currently SHA1 hashing is used.  It should be plenty for our purposes.
    
    """
    return hashlib.sha1(''.join(args).encode('utf-8')).hexdigest()


if 'HG_B_SIMPLE_HASHING' in os.environ:
    def _hash(*args):
        """Hashes only the first argument"""
        return hashlib.sha1(args[0].encode('utf-8')).hexdigest()


def _mkdir_p(path):
    """ race condition handling recursive mkdir -p call
    http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
    """
    try:
        os.makedirs(path)
    except OSError, exc:
        if exc.errno == errno.EEXIST:
            pass
        else:
            raise


def _truth(s):
    """ Indicates the truth of a string """
    return s == 'True' or s == 'true'


def _task_from_taskline(taskline):
    """Parse a taskline (from a task file) and return a task.
    
    A taskline should be in the format:
    
        summary text ... | meta1:meta1_value,meta2:meta2_value,...
    
    The task returned will be a dictionary such as:
    
        { 'id': <hash id>,
          'text': <summary text>,
           ... other metadata ... }
    
    A taskline can also consist of only summary text, in which case the id
    and other metadata will be generated when the line is read.  This is
    supported to enable editing of the taskfile with a simple text editor.
    """
    try:
        if '|' in taskline:
            text, meta = taskline.rsplit('|', 1)
            task = {'text': text.strip()}
            for piece in meta.strip().split(','):
                label, data = piece.split(':', 1)
                task[label.strip()] = data.strip()
        else:
            text = taskline.strip()
            task = {'id': _hash(text, str(time.time())),
                    'text': text,
                    'owner': '',
                    'open': 'True',
                    'time': time.time()
                    }
        return task
    except Exception:
        raise IOError(errno.EIO,
                      _("Failed to parse task; perhaps a missplaced '|'?\n"
                        "Line is: %s") % taskline)


def _tasklines_from_tasks(tasks):
    """Parse a list of tasks into tasklines suitable for writing to a file."""

    tasklines = []

    for task in tasks:
        meta = [m for m in task.items() if m[0] != 'text']
        meta_str = ', '.join('%s:%s' % m for m in meta)
        tasklines.append('%s | %s\n' % (task['text'].ljust(60), meta_str))

    return tasklines


def _prefixes(elements):
    """Return a mapping of elements to their unique prefix in O(n) time.
    
    This is much faster than the native t function, which takes O(n^2) time.
    
    Each prefix will be the shortest possible substring of the element that
    can uniquely identify it among the given group of elements.
    
    If an element is entirely a substring of another, the whole string will be
    the prefix.
    """
    pre = {}
    for e in elements:
        e_len = len(e)
        i, prefix = None, None  # should always be overwritten
        for i in range(1, e_len + 1):
            # Identifies an empty prefix slot, or a singular collision
            prefix = e[:i]
            if prefix not in pre or (
                    pre[prefix] != ':' and prefix != pre[prefix]):
                break
        if prefix in pre:
            # Handle collisions
            collide = pre[prefix]
            for j in range(i, e_len + 1):
                if collide[:j] == e[:j]:
                    pre[e[:j]] = ':'
                else:
                    pre[collide[:j]] = collide
                    pre[e[:j]] = e
                    break
            else:
                pre[collide[:e_len + 1]] = collide
                pre[e] = e
        else:
            # No collision, can safely add
            pre[prefix] = e

    # Invert mapping and clear placeholder key
    pre = dict(zip(pre.values(), pre.keys()))
    if ':' in pre:
        del pre[':']
    return pre


def _describe_print(num, is_open, owner, filter_by):
    """ Helper function used by list to describe the data just displayed """
    type_name = 'open' if is_open else 'resolved'
    out = _("Found %s %s bug%s") % (num, type_name, '' if num == 1 else 's')
    if owner != '*':
        out = out + (_(" owned by %s") % ('Nobody' if owner == '' else owner))
    if filter_by:
        out = out + _(" whose title contains %s") % filter_by
    return out


#
# b's business logic and programatic API
#
class BugsDict(object):
    """A set of bugs, issues, and tasks, both finished and unfinished, for a
    given repository.
    
    The list's file is read from disk when initialized. The items
    can be written back out to disk with the write() function.
    
    You can specify any taskdir you want, but the intent is to work from the cwd
    and therefore anything calling this class ought to handle that change
    (normally to the repo root)
    """

    def __init__(self, bugsdir='.bugs', user='', fast_add=False):
        """Initialize by reading the task files, if they exist."""
        self.bugsdir = bugsdir
        self.user = user
        self.fast_add = fast_add
        self.file = 'bugs'
        self.detailsdir = 'details'
        self.last_added_id = None
        self.bugs = {}
        # this is the default contents of the bugs directory.  If you'd like,
        # you can modify this variable's contents.  Be sure to leave [comments]
        # as the last field. Remember that storing metadata like [reporter] in
        # the details file is not secure. it is recommended that you use
        # Mercurial's excellent data-mining tools such as log and annotate to
        # get such information.
        self.init_details = '\n'.join([
            "# Lines starting with '#' and sections without content",
            "# are not displayed by a call to 'details'",
            "#",
            # "[reporter]",
            # "The user who created this file",
            # "# This field can be edited, and is just a convenience",
            # "%s" % self.user,
            # ""
            "[paths]",
            "# Paths related to this bug.",
            "# suggested format: REPO_PATH:LINENUMBERS",
            ""
            "",
            "[details]",
            "# Additional details",
            "",
            "",
            "[expected]\n# The expected result",
            "",
            "",
            "[actual]",
            "# What happened instead",
            "",
            "",
            # "[stacktrace]",
            # "# A stack trace or similar diagnostic info",
            # "",
            # "",
            "[reproduce]",
            "# Reproduction steps",
            "",
            "",
            "[comments]",
            "# Comments and updates - leave your name"
        ])

        path = os.path.join(os.path.expanduser(self.bugsdir), self.file)
        if os.path.exists(path):
            with open(path, 'r') as tfile:
                tlns = tfile.readlines()
                tls = [tl.strip() for tl in tlns if tl.strip()]
                tasks = map(_task_from_taskline, tls)
                for task in tasks:
                    self.bugs[task['id']] = task

    def write(self):
        """Flush the finished and unfinished tasks to the files on disk."""
        _mkdir_p(self.bugsdir)
        path = os.path.join(os.path.expanduser(self.bugsdir), self.file)
        tasks = sorted(self.bugs.values(), key=itemgetter('id'))
        with open(path, 'w') as tfile:
            for taskline in _tasklines_from_tasks(tasks):
                tfile.write(taskline)

    def __getitem__(self, prefix):
        """Return the task with the given prefix.
        
        If more than one task matches the prefix an AmbiguousPrefix exception
        will be raised, unless the prefix is the entire ID of one task.
        
        If no tasks match the prefix an UnknownPrefix exception will be raised.
        
        """
        matched = [item for item in self.bugs.keys() if item.startswith(prefix)]
        if len(matched) == 1:
            return self.bugs[matched[0]]
        elif len(matched) == 0:
            raise UnknownPrefix(prefix)
        else:
            matched = [item for item in self.bugs.keys() if item == prefix]
            if len(matched) == 1:
                return self.bugs[matched[0]]
            else:
                raise AmbiguousPrefix(prefix)

    def _get_details_path(self, full_id):
        """Returns the directory and file path to the details specified by id"""
        dirpath = os.path.join(self.bugsdir, self.detailsdir)
        path = os.path.join(dirpath, full_id + ".txt")
        return dirpath, path

    def _make_details_file(self, full_id):
        """ Create a details file for the given id """
        (dirpath, path) = self._get_details_path(full_id)
        if not os.path.exists(dirpath):
            _mkdir_p(dirpath)
        if not os.path.exists(path):
            with open(path, "w+") as f:
                f.write(self.init_details)
        return path

    def _users_list(self):
        """Returns a mapping of usernames to the number of open bugs assigned to
        that user"""
        open_tasks = [item['owner'] for item in self.bugs.values() if
                      _truth(item['open'])]
        closed = [item['owner'] for item in self.bugs.values() if
                  not _truth(item['open'])]
        users = {}
        for user in open_tasks:
            if user in users:
                users[user] += 1
            else:
                users[user] = 1
        for user in closed:
            if user not in users:
                users[user] = 0

        if '' in users:
            users['Nobody'] = users['']
            del users['']
        return users

    def _get_user(self, user, force=False):
        """Given a user prefix, returns the appropriate username, or fails if
        the correct user cannot be identified.
        
        'me' is a special username which maps to the username specified when
        constructing the BugsDict.
        'Nobody' (and prefixes of 'Nobody') is a special username which maps
        internally to the empty string, indicating no assignment.
        If force is true, the user 'Nobody' is used.  This is unadvisable,
        avoid forcing the username 'Nobody'.
        
        If force is true, it assumes user is not a prefix and should be
        assumed to exist already.
        """
        if user == 'me':
            return self.user
        if user == 'Nobody':
            return ''
        users = self._users_list().keys()
        if not force:
            if user not in users:
                usr = user.lower()
                matched = [u for u in users if u.lower().startswith(usr)]
                if len(matched) > 1:
                    raise AmbiguousUser(user, matched)
                if len(matched) == 0:
                    raise UnknownUser(user)
                user = matched[0]
            # Needed twice, since users can also type a prefix of "Nobody"
            if user == 'Nobody':
                return ''
        else:  # we're forcing a new username
            if '|' in user:
                raise InvalidInput(_("Usernames cannot contain '|'."))
        return user

    def id(self, prefix):
        """ Given a prefix, returns the full id of that bug """
        return self[prefix]['id']

    def add(self, text):
        """Adds a bug with no owner to the task list"""
        task_id = _hash(text, self.user, str(time.time()))
        self.bugs[task_id] = {'id': task_id, 'open': 'True', 'owner': self.user,
                              'text': text, 'time': time.time()}
        self.last_added_id = task_id
        if self.fast_add:
            short_task_id = "%s..." % task_id[:10]
        else:
            prefix = _prefixes(self.bugs.keys())[task_id]
            short_task_id = "%s:%s" % (prefix, task_id[len(prefix):10])
        return _("Added bug %s") % short_task_id

    def rename(self, prefix, text):
        """Renames the bug
        
        If more than one task matches the prefix an AmbiguousPrefix exception
        will be raised, unless the prefix is the entire ID of one task.
        
        If no tasks match the prefix an UnknownPrefix exception will be raised.
        
        """
        task = self[prefix]
        if text.startswith('s/') or text.startswith('/'):
            text = re.sub('^s?/', '', text).rstrip('/')
            find, _, repl = text.partition('/')
            text = re.sub(find, repl, task['text'])

        task['text'] = text

    def users(self):
        """Prints a list of users along with their number of open bugs"""
        users = self._users_list()
        if len(users) > 0:
            ulen = max([len(user) for user in users.keys()]) + 1
        else:
            ulen = 0
        out = _("Username: Open Bugs\n")
        for (user, count) in users.items():
            out += _("%s: %s\n") % (user, str(count).rjust(ulen - len(user)))
        return out

    def assign(self, prefix, user, force=False):
        """Specifies a new owner of the bug.  Tries to guess the correct user,
        or warns if it cannot find an appropriate user.

        Using the -f flag will create a new user with that exact name,
        it will not try to guess, or warn the user."""
        task = self[prefix]
        user = self._get_user(user, force)
        task['owner'] = user
        if user == '':
            user = 'Nobody'
        return _("Assigned %s: '%s' to %s" % (prefix, task['text'], user))

    def details(self, prefix):
        """ Provides additional details on the requested bug.
        
        Metadata (like owner, and creation time) which are
        not stored in the details file are displayed along with
        the details.
        
        Sections (denoted by a [text] line) with no content
        are not displayed.
        """
        task = self[prefix]  # confirms prefix does exist
        path = self._get_details_path(task['id'])[1]
        if os.path.exists(path):
            with open(path) as f:
                text = f.read()

            text = re.sub("(?m)^#.*\n?", "", text)

            while True:
                oldtext = text
                retext = re.sub("\[\w+\]\s+\[", "[", text)
                text = retext
                if oldtext == retext:
                    break

            text = re.sub("\[\w+\]\s*$", "", text)
        else:
            text = _('No Details File Found.')

        header = _("Title: %s\nID: %s\n") % (task['text'], task['id'])
        if not _truth(task['open']):
            header = header + _("*Resolved* ")
        if task['owner'] != '':
            header = header + (_("Owned By: %s\n") % task['owner'])
        header = header + (_("Filed On: %s\n\n") % _datetime(task['time']))
        text = header + text

        return text.strip()

    def edit(self, prefix, editor):
        """Allows the user to edit the details of the specified bug"""
        task = self[prefix]  # confirms prefix does exist
        path = self._get_details_path(task['id'])[1]
        if not os.path.exists(path):
            self._make_details_file(task['id'])
        subprocess.call("%s '%s'" % (editor, path), shell=True)

    def comment(self, prefix, comment):
        """Allows the user to add a comment to the bug without launching an editor.
        
        If they have a username set, the comment will show who made it."""
        task = self[prefix]  # confirms prefix does exist
        path = self._get_details_path(task['id'])[1]
        if not os.path.exists(path):
            self._make_details_file(task['id'])

        comment = _("On: %s\n%s") % (_datetime(), comment)

        if self.user != '':
            comment = _("By: %s\n%s") % (self.user, comment)

        with open(path, "a") as f:
            f.write("\n\n" + comment)

    def resolve(self, prefix):
        """Marks a bug as resolved"""
        task = self[prefix]
        task['open'] = 'False'

    def reopen(self, prefix):
        """Reopens a bug that was previously resolved"""
        task = self[prefix]
        task['open'] = 'True'

    def list(self, is_open=True, owner='*', grep='', alpha=False, chrono=False,
             truncate=0):
        """Lists all bugs, applying the given filters"""
        tasks = dict(self.bugs.items())

        prefixes = _prefixes(tasks).items()
        for task_id, prefix in prefixes:
            tasks[task_id]['prefix'] = prefix

        if owner != '*':
            owner = self._get_user(owner)

        small = [task for task in tasks.values()
                 if _truth(task['open']) == is_open
                 and (owner == '*' or owner == task['owner'])
                 and (grep == '' or grep.lower() in task['text'].lower())]
        if len(small) > 0:
            plen = max([len(task['prefix']) for task in small])
        else:
            plen = 0
        out = ''
        if alpha:
            small = sorted(small, key=lambda x: x['text'].lower())
        if chrono:
            small = sorted(small, key=itemgetter('time'))
        for task in small:
            line = _('%s - %s') % (task['prefix'].ljust(plen), task['text'])
            if 0 < truncate < len(line):
                line = line[:truncate - 4] + '...'
            out += line + '\n'
        return out + _describe_print(len(small), is_open, owner, grep)


#
# Decorators for argument validation
#

def simple_decorator(decorator):
    """Decorator-decorator pattern
    https://wiki.python.org/moin/PythonDecoratorLibrary
    """

    def new_decorator(f):
        g = decorator(f)
        g.__name__ = f.__name__
        g.__doc__ = f.__doc__
        g.__dict__.update(f.__dict__)
        return g

    return new_decorator


class ValidOpts:
    def __init__(self, *valid_opts):
        self.valid_opts = set(valid_opts)

    def __call__(self, f):
        def non_default(key, value):
            if key == 'owner':
                return value != '*'
            return value

        def d(that, args, opts):
            invalid_opts = [o for o in opts
                            if non_default(o, opts[o])
                            and o not in self.valid_opts]
            if invalid_opts:
                raise InvalidCommand(_(
                    "--%s is not a supported flag for this command" %
                    invalid_opts[0]))
            return f(that, args, opts)

        # TODO have @simple_decorator support decorator classes
        d.__name__ = f.__name__
        d.__doc__ = f.__doc__
        d.__dict__.update(f.__dict__)
        return d


@simple_decorator
def zero_args(f):
    def d(self, args, opts):
        if args:
            raise InvalidCommand(
                _("Expected zero arguments, got '%s'" % ' '.join(args)))
        return f(self, opts)

    return d


@simple_decorator
def prefix_arg(f):
    def d(self, args, opts):
        if len(args) < 1:
            raise RequiresPrefix()
        elif len(args) > 1:
            raise InvalidCommand(_("Unexpected arguments: %s" % args[1:]))
        else:
            return f(self, args[0], opts)

    return d


@simple_decorator
def prefix_plus_args(f):
    def d(self, args, opts):
        if len(args) < 1:
            raise RequiresPrefix()
        return f(self, args[0], args[1:], opts)

    return d


#
# Mercurial Extention Operations
# These are used to allow the tool to work as a Hg Extention
#
def _track(ui, repo, path):
    """ Adds new files to Mercurial. """
    if os.path.exists(path):
        ui.pushbuffer()
        commands.add(ui, repo, path)
        ui.popbuffer()


def _cat(ui, repo, path, todir, rev=None):
    ui.pushbuffer(error=True)
    success = commands.cat(ui, repo, path, rev=rev,
                           output=os.path.join(todir, path))
    msg = ui.popbuffer()
    if success != 0:
        raise IOError(errno.ENOENT,
                      _("Failed to access %s at rev %s\nDetails: %s") % (
                          path, rev, msg))


class _CLI(object):
    """Command line interface."""

    def __init__(self, ui, repo):
        self.ui = ui
        self.repo = repo
        self.bugsdir = bugs_dir(ui)

        self.user = self.ui.config("bugs", "user", '')
        if self.user == 'hg.user':
            ui.warn(_(
                "No need to set bugs.user=hg.user in your hgrc - "
                "just remove this line\n"))
            self.user = ''
        if not self.user:
            # Use Mercurial username if bugs.user is not set
            # not sure if there's a better way to optionally get the username
            try:
                self.user = self.ui.username()
            except Abort:
                pass

        self._bd = None
        self._revpath = None

    def bd(self, opts):
        if self._bd:
            raise Exception("Don't construct the BugsDict more than once.")

        os.chdir(self.repo.root)

        # handle other revisions
        #
        # The methodology here is to use or create a directory in the user's
        # /tmp directory for the given revision and store whatever files are
        # being accessed there, then simply set path to the temporary repodir
        if opts['rev']:
            # FIXME error on bad rev?
            rev = str(self.repo[opts['rev']])
            tempdir = tempfile.gettempdir()
            self._revpath = os.path.join(tempdir, 'b-' + rev)
            _mkdir_p(os.path.join(self._revpath, self.bugsdir))
            relbugsdir = os.path.join(self.bugsdir, 'bugs')
            revbugsdir = os.path.join(self._revpath, relbugsdir)
            if not os.path.exists(revbugsdir):
                _cat(self.ui, self.repo, relbugsdir, self._revpath, rev)
            os.chdir(self._revpath)

        fast_add = self.ui.configbool("bugs", "fast_add", False)
        self._bd = BugsDict(self.bugsdir, self.user, fast_add)
        return self._bd

    def _cat_rev_details(self, task_id, rev):
        # Try to write the details file for this revision
        # if the lookup fails, we don't need to worry about it, the
        # standard error handling will catch it and warn the user
        fullid = self._bd.id(task_id)
        detfile = os.path.join(self.bugsdir, 'details', fullid + '.txt')
        revdetfile = os.path.join(self._revpath, detfile)
        if not os.path.exists(revdetfile):
            _mkdir_p(os.path.join(self._revpath, self.bugsdir, 'details'))
            os.chdir(self.repo.root)  # TODO rearrange so this isn't necessary
            _cat(self.ui, self.repo, detfile, self._revpath, rev)
            os.chdir(self._revpath)

    def invoke(self, cmd, *args, **opts):
        commands = ['add', 'assign', 'comment', 'details', 'edit', 'help', 'id',
                    'list', 'rename', 'resolve', 'reopen', 'users', 'version']

        candidates = [c for c in commands if c.startswith(cmd)]
        exact_candidate = [c for c in candidates if c == cmd]
        if exact_candidate:
            pass  # already valid command
        elif len(candidates) > 1:
            raise AmbiguousCommand(candidates)
        elif len(candidates) == 1:
            cmd = candidates[0]
        else:
            raise UnknownCommand(cmd)

        getattr(self, cmd, None)(args, opts)

        # Add all new files to Mercurial - does not commit
        if not opts['rev']:
            _track(self.ui, self.repo, self.bugsdir)

    @ValidOpts('edit')
    def add(self, args, opts):
        title = ' '.join(args).strip()
        if not title:
            raise InvalidCommand(_("Must specify issue title"))
        self.ui.write(self.bd(opts).add(title) + '\n')
        self._bd.write()

        self._maybe_edit(self._bd.last_added_id, opts)

    @ValidOpts('edit')
    @prefix_plus_args
    def rename(self, task_id, args, opts):
        title = ' '.join(args).strip()
        if not title:
            raise InvalidCommand(_("Must specify issue title"))
        self.bd(opts).rename(task_id, title)
        self._bd.write()

        self._maybe_edit(task_id, opts)

    @ValidOpts('rev')
    @zero_args
    def users(self, opts):
        self.ui.write(self.bd(opts).users() + '\n')

    @ValidOpts('force', 'edit')
    @prefix_plus_args
    def assign(self, task_id, args, opts):
        if not args:
            raise InvalidCommand(_("Must provide a username to assign"))
        if len(args) > 1:
            raise InvalidCommand(_("Unexpected arguments: %s" % args[1:]))
        self.ui.write(
            self.bd(opts).assign(task_id, args[0], opts['force']) + '\n')
        self._bd.write()

        self._maybe_edit(task_id, opts)

    @ValidOpts('rev')
    @prefix_arg
    def details(self, task_id, opts):
        if opts['rev']:
            self._cat_rev_details(task_id, opts['rev'])
        self.ui.write(self.bd(opts).details(task_id) + '\n')

    @ValidOpts()
    @prefix_arg
    def edit(self, task_id, opts):
        self.bd(opts).edit(task_id, self.ui.geteditor())

    def _maybe_edit(self, task_id, opts):
        if opts['edit']:
            self._bd.edit(task_id, self.ui.geteditor())

    @ValidOpts('edit')
    @prefix_plus_args
    def comment(self, task_id, args, opts):
        comment = ' '.join(args).strip()
        if not comment and not opts['edit']:
            raise InvalidCommand(
                _("Must include comment text in command or use --edit"))
        self.bd(opts).comment(task_id, comment)

        self._maybe_edit(task_id, opts)

    @ValidOpts('edit')
    @prefix_arg
    def resolve(self, task_id, opts):
        self.bd(opts).resolve(task_id)
        self._bd.write()

        self._maybe_edit(task_id, opts)

    @ValidOpts('edit')
    @prefix_arg
    def reopen(self, task_id, opts):
        self.bd(opts).reopen(task_id)
        self._bd.write()

        self._maybe_edit(task_id, opts)

    @ValidOpts('alpha', 'chrono', 'grep', 'owner', 'resolved', 'rev',
               'truncate')
    @zero_args
    def list(self, opts):
        self.ui.write(self.bd(opts).list(
            not opts['resolved'],
            opts['owner'],
            opts['grep'],
            opts['alpha'],
            opts['chrono'],
            self.ui.termwidth() if opts['truncate'] else 0)
                      + '\n')

    @ValidOpts('rev')
    @prefix_arg
    def id(self, task_id, opts):
        self.ui.write(self.bd(opts).id(task_id) + '\n')

    @ValidOpts()
    @zero_args
    def help(self, _opts):
        commands.help_(self.ui, 'b')

    @ValidOpts()
    @zero_args
    def version(self, _opts):
        version_str = "%d.%d.%d" % _version_num
        self.ui.write(
            _("b Version %s - built %s\n") % (version_str, _build_date))


cmdtable = {}
command = registrar.command(cmdtable)
testedwith = '4.7'  # And others circa 2010, before this variable existed
buglink = 'http://hg.mwdiamond.com/b'


#
# Command line processing
#
@command("b|bug|bugs",
         [
             ('f', 'force', False, _('Force this exact username')),
             ('e', 'edit', False,
              _('Launch details editor after running command')),
             ('r', 'resolved', False, _('List resolved bugs')),
             ('o', 'owner', '*', _('Specify an owner to list by')),
             ('g', 'grep', '', _('Filter titles by STRING')),
             ('a', 'alpha', False, _('Sort list alphabetically')),
             ('c', 'chrono', False, _('Sort list chronologically')),
             ('T', 'truncate', False, _('Truncate list output to fit window')),
             ('', 'rev', '',
              _('Run a read-only command against a different revision'))
         ],
         "cmd [args]"
         )
def execute_command(ui, repo, cmd='list', *args, **opts):
    """Distributed Bug Tracker For Mercurial
    
    List of Commands::
    
    add text [-e]
        Adds a new open bug to the database, if user is set in the config files,
        assigns it to user
        
        -e here and elsewhere launches the details editor for the issue upon
        successful execution of the command
        
    rename prefix text [-e]
        Renames The bug denoted by prefix to text.   You can use sed-style
        substitution strings if so desired.
        
    users [--rev rev]
        Displays a list of all users, and the number of open bugs assigned to
        each of them
        
    assign prefix username [-f] [-e]
        Assigns bug denoted by prefix to username.  Username can be a lowercase
        prefix of another username and it will be mapped to that username. To
        avoid this functionality and assign the bug to the exact username
        specified, or if the user does not already exist in the bugs system, use
        the -f flag to force the name.
        
        Use 'me' to assign the bug to the current user,
        and 'Nobody' to remove its assignment.
        
    details [--rev rev] prefix [-e]
        Prints the extended details of the specified bug
        
    edit prefix
        Launches your specified editor to provide additional details 
        
    comment prefix comment [-e]
        Appends comment to the details of the bug, along with the date
        and, if specified, your username without needing to launch an editor
        
    resolve prefix [-e]
        Marks the specified bug as resolved
        
    reopen prefix [-e]
        Marks the specified bug as open
        
    list [--rev rev] [-r] [-o owner] [-g search] [-a|-c]
        Lists all bugs, with the following filters:
        
            -r list resolved bugs.
        
            -o list bugs assigned to owner.  '*' will list all bugs, 'me' will
               list all bugs assigned to the current user, and 'Nobody' will
               list all unassigned bugs.
        
            -g filter by the search string appearing in the title
            
            -a list bugs alphabetically
            
            -c list bugs chronologically
        
    id [--rev rev] prefix [-e]
        Takes a prefix and returns the full id of that bug
    
    version
        Outputs the version number of b being used in this repository
    """
    try:
        try:
            _CLI(ui, repo).invoke(cmd, *args, **opts)
        except Exception:
            if 'HG_B_LOG_TRACEBACKS' in os.environ:
                traceback.print_exc(file=sys.stderr)
                sys.stderr.write("\n")
            raise
    except Error, e:
        ui.warn('%s\n' % e.msg)
        return 1


#
# Programmatic access to b
#

def version(given_version=None):
    """Returns a numerical representation of the version number, or takes a
    version string.

    Can be used for comparison:
        b.version() > b.version("0.7.0")
    
    Note: Before version 0.6.2 this function did not exist. If:
        callable(getattr(b, "version", None))
    returns false, that indicates a version before 0.6.2"""
    if given_version:
        a, b, c = (int(ver) for ver in given_version.split('.') if
                   ver.isdigit())
        return a, b, c
    return _version_num


def bugs_dir(ui):
    """Returns the path to the bugs dir, relative to the repo root"""
    return ui.config("bugs", "dir", ".bugs")


def status(ui, repo, revision='tip', ignore=None):
    """Indicates the state of a revision relative to the bugs database.  In
    essence, this function is a wrapper for `hg stat --change x` which strips
    out changes to the bugs directory.

    A revision either:
    * Does not touch the bugs directory:
      This generally indicates a feature change or other improvement, in any
      case, b cannot draw any conclusions about the revision.
      Returns None.
    * Only touches the bugs directory:
      This would indicate a new bug report, comment, reassignment, or other
      internal b housekeeping.  No external files were touched, no progress is
      being made in the rest of repository.
      Returns an empty list.
    * Touches the bugs directory, and other areas of the repository:
      This is assumed to indicate a bug fix, or progress is being made on a bug.
      Committing unrelated changes to the repository and the bugs database in
      the same revision should be discouraged.
      Returns a list of files outside the bugs directory in the given changeset.
    
    You may pass a list of Mercurial patterns (see `hg help patterns`) relative
    to the repository root to exclude from the returned list.
    """
    # TODO should this just be deleted? It's unused internally and has no tests
    if ignore:
        raise Error("UNIMPLEMENTED")  # TODO this was never implemented
    bugsdir = bugs_dir(ui)
    ui.pushbuffer()
    commands.status(ui, repo, change=revision, no_status=True, print0=True)
    files = ui.popbuffer().split('\0')
    bug_change = False
    ret = []
    for f in files:
        if f.strip():
            if f.startswith(bugsdir):
                bug_change = True
            else:
                ret.append(f)
    ui.write(ret if bug_change else None)
    ui.write('\n')
