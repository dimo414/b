#!/usr/bin/env python

"""
Simple bug tracking system for Mercurial
Based off and built using Steve Losh's t
http://stevelosh.com/projects/t/
"""
version = "Bugs 0.1.0"

#
# Imports
#
import os, re, sys, hashlib, random

#
# Exceptions
#
class NotInRepo(Exception):
    """Raised when the cwd is not inside a Mercurial repo."""
    pass

class NoDetails(Exception):
    def __init__(self,prefix):
        """Raised when user requests details on a bug with no details"""
        super().__init__()
        self.prefix = prefix

class InvalidDetailsFile(Exception):
    def __init__(self,prefix):
        """Raised when a bug's details file is invalid (is a dir)"""
        super().__init__()
        self.prefix = prefix

class InvalidTaskfile(Exception):
    """Raised when the path to a task file already exists as a directory."""
    pass

class AmbiguousPrefix(Exception):
    """Raised when trying to use a prefix that could identify multiple tasks."""
    def __init__(self, prefix):
        super().__init__()
        self.prefix = prefix
    

class UnknownPrefix(Exception):
    """Raised when trying to use a prefix that does not match any tasks."""
    def __init__(self, prefix):
        super().__init__()
        self.prefix = prefix

#       
# Helper Methods - often straight from t
#
def _hash(text):
    """Return a hash of the given text for use as an id.
    
    Currently SHA1 hashing is used.  It should be plenty for our purposes.
    
    """
    return hashlib.sha1(text.encode('utf-8')).hexdigest()

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
    if '|' in taskline:
        text, _, meta = taskline.partition('|')
        task = { 'text': text.strip() }
        for piece in meta.strip().split(','):
            label, data = piece.split(':')
            task[label.strip()] = data.strip()
    else:
        text = taskline.strip()
        task = { 'id': _hash(text), 'text': text }
    return task

def _tasklines_from_tasks(tasks):
    """Parse a list of tasks into tasklines suitable for writing to a file."""
    
    tasklines = []
    tlen = max(map(lambda t: len(t['text']), tasks)) if tasks else 0
    
    for task in tasks:
        meta = [m for m in task.items() if m[0] != 'text']
        meta_str = ', '.join('%s:%s' % m for m in meta)
        tasklines.append('%s | %s\n' % (task['text'].ljust(tlen), meta_str))
    
    return tasklines

def _prefixes(ids):
    """Return a mapping of ids to prefixes in O(n) time.
    
    This is much faster than the naitive t function, which
    takes O(n^2) time.
    
    Each prefix will be the shortest possible substring of the ID that
    can uniquely identify it among the given group of IDs.
    
    If an ID of one task is entirely a substring of another task's ID, the
    entire ID will be the prefix.
    """
    pre = {}
    for id in ids:
        id_len = len(id)
        for i in range(1, id_len+1):
            """ identifies an empty prefix slot, or a singular collision """
            prefix = id[:i]
            if (not prefix in pre) or (pre[prefix] != ':' and prefix != pre[prefix]):
                break
        if prefix in pre:
            """ if there is a collision """
            collide = pre[prefix]
            for j in range(i,id_len+1):
                if collide[:j] == id[:j]:
                    pre[id[:j]] = ':'
                else:
                    pre[collide[:j]] = collide
                    pre[id[:j]] = id
                    break
            else:
                pre[collide[:id_len+1]] = collide
                pre[id] = id
        else:
            """ no collision, can safely add """
            pre[prefix] = id
    pre = dict(zip(pre.values(),pre.keys()))
    if ':' in pre:
        del pre[':']
    return pre

#
# Primary Class
#
class BugsDict(object):
    """A set of bugs, issues, and tasks, both finished and unfinished, for a given repository.
    
    The list's file is read from disk when initialized. The items
    can be written back out to disk with the write() function.
    
    You can specify any taskdir you want, but the intent is to work from the cwd
    and therefore anything calling this class ought to handle that change
    (normally to the repo root)
    """
    def __init__(self, bugsdir='.bugs'):
        """Initialize by reading the task files, if they exist."""
        self.file = 'bugs'
        self.bugsdir = bugsdir
        self.bugs = {}
        path = os.path.join(os.path.expanduser(self.bugsdir), self.file)
        if os.path.isdir(path):
            raise InvalidTaskfile
        if os.path.exists(path):
            with open(path, 'r') as tfile:
                tls = [tl.strip() for tl in tfile if tl]
                tasks = map(_task_from_taskline, tls)
                for task in tasks:
                    self.bugs[task['id']] = task
    
    def add_bug(self, text):
        """Adds a bug with no owner to the task list"""
        pass
    
    def rename_bug(self, id, text):
        """Renames the bug"""
        pass
    
    def assign_bug(self, id, user,force=False):
        """Specifies a new owner of the bug.  Warns if the owner doesn't exist"""
        pass
    
    def details_bug(self, id):
        """Returns the details of a specified bug if they exist"""
        pass
    
    def edit_bug(self, id):
        """Allows the user to edit the details of the specified bug"""
        pass
    
    def comment_bug(self, id, comment):
        """Allows the user to add a comment to the bug without launching an editor"""
        pass
    
    def resolve_bug(self, id):
        """Marks a bug as resolved"""
        pass
    
    def reopen_bug(self, id):
        """Reopens a bug that was previously resolved"""
        pass
    
    def list_bugs(self,open=True,owner='',grep='',verbose=False,quiet=False):
        """Lists all bugs, applying the given filters"""
        pass
#
# Mercurial Extention Methods
# These are used to allow the tool to work as a Hg Extention
#


#
# Mercurial Replacement Methods
# These are used to allow this tool to work without being a Hg Extension
# And are not called when run as part of Hg
#
