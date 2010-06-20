#!/usr/bin/env python


#
# Imports
#
import os, errno, re, hashlib, sys
from operator import itemgetter
from datetime import datetime
from mercurial.i18n import _
from mercurial import hg

"""
HgBugs - A lightweight bug tracker for Mercurial

Version 0.1.0

Based off and built using Steve Losh's brilliantly simple task manager t
(http://stevelosh.com/projects/t/) the fundamental principle is 
'Get things done, not organized', and like t, 
"the only way to make your bug list prettier is to finish some damn tasks."
"""

#
# Exceptions
#
class NotInRepo(Exception):
    """Raised when the cwd is not inside a Mercurial repo."""
    pass

class NoDetails(Exception):
    def __init__(self,prefix):
        """Raised when user requests details on a bug with no details"""
        super(NoDetails, self).__init__()
        self.prefix = prefix

class InvalidDetailsFile(Exception):
    def __init__(self,prefix):
        """Raised when a bug's details file is invalid (is a dir)"""
        super(InvalidDetailsFile, self).__init__()
        self.prefix = prefix

class InvalidTaskfile(Exception):
    """Raised when the path to a task file already exists as a directory."""
    pass

class AmbiguousPrefix(Exception):
    """Raised when trying to use a prefix that could identify multiple tasks."""
    def __init__(self, prefix):
        super(AmbiguousPrefix, self).__init__()
        self.prefix = prefix
    

class UnknownPrefix(Exception):
    """Raised when trying to use a prefix that does not match any tasks."""
    def __init__(self, prefix):
        super(UnknownPrefix, self).__init__()
        self.prefix = prefix

#       
# Helper Methods - often straight from t
#
def _timestamp():
        now = datetime.now()
        return now.strftime("%A, %B %d %Y %I:%M%p")

def _hash(text):
    """Return a hash of the given text for use as an id.
    
    Currently SHA1 hashing is used.  It should be plenty for our purposes.
    
    """
    return hashlib.sha1(text.encode('utf-8')).hexdigest()

def _mkdir_p(path):
    """ race condition handling recursive mkdir call
    http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
    """
    try:
        os.makedirs(path)
    except OSError, exc:
        if exc.errno == errno.EEXIST:
            pass
        else: raise

def _truth(str,bool):
    return bool and (str == 'True') or not bool and (str != 'True')

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
        task = { 'id': _hash(text), 'text': text, 'owner': '', 'open': 'True' }
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

def _describe_print(num,type,owner,filter):
    typeName = 'open' if type else 'resolved'
    out = "Found %s %s bug%s" % (num, typeName, '' if num==1 else 's')
    if owner != '*':
        out = out+(" owned by %s" % ('Nobody' if owner=='' else owner))
    if filter != '':
        out = out+" whose title contains %s" % filter
    return out

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
    def __init__(self, autodetails=True,bugsdir='.bugs'):
        """Initialize by reading the task files, if they exist."""
        self.autodetail = autodetails
        self.file = 'bugs'
        self.bugsdir = bugsdir
        self.detailsdir = 'details'
        self.bugs = {}
        self.init_details = ("Details for '%s'\nID: %s\nFiled: %s\n\n"
        "[paths]\n# Paths related to this bug.\n# suggested format: REPO_PATH:LINENUMBERS\n\n\n"
        "[details]\n# Additional details\n\n\n"
        "[expected]\n# The expected result\n\n\n"
        "[actual]\n# What happened instead\n\n\n"
        "[reproduce]\n# Reproduction steps\n\n\n"
        "[comments]\n# Comments and updates - leave your name\n")
        path = os.path.join(os.path.expanduser(self.bugsdir), self.file)
        if os.path.isdir(path):
            raise InvalidTaskfile
        if os.path.exists(path):
            tfile = open(path, 'r')
            tlns = tfile.readlines()
            tls = [tl.strip() for tl in tlns if tl]
            tasks = map(_task_from_taskline, tls)
            for task in tasks:
                self.bugs[task['id']] = task
            tfile.close()
    
    def write(self):
        """Flush the finished and unfinished tasks to the files on disk."""
        path = os.path.join(os.path.expanduser(self.bugsdir), self.file)
        if os.path.isdir(path):
            raise InvalidTaskfile
        tasks = sorted(self.bugs.values(), key=itemgetter('id'))
        tfile = open(path, 'w')
        for taskline in _tasklines_from_tasks(tasks):
            tfile.write(taskline)
        tfile.close()
    
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
            
    def _make_details_file(self,id):
        dirpath = os.path.join(self.bugsdir,self.detailsdir)
        path = os.path.join(dirpath,id+".txt")
        if not os.path.exists(dirpath):
            _mkdir_p(dirpath)
        if os.path.isdir(path):
            raise InvalidDetailsFile(id)
        if not os.path.exists(path):
            f = open(path, "w+")
            f.write(self.init_details % (self.bugs[id]['text'],self.bugs[id]['id'],_timestamp()))
            f.close()
        return path
    
    def add(self, text):
        """Adds a bug with no owner to the task list"""
        task_id = _hash(text)
        self.bugs[task_id] = {'id': task_id, 'open': 'True', 'owner': '', 'text': text}
        if self.autodetail:
            self._make_details_file(task_id)
    
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
        
        path = os.path.join(self.bugsdir,self.detailsdir,self[prefix]['id']+".txt")
        if os.path.exists(path):
            print("At present, the details file for this bug shows the original name still.  "
                  "This is a known bug, but you'll need to edit the details manually.")
    
    def assign(self, prefix, user,force=False):
        """Specifies a new owner of the bug.  Warns if the owner doesn't exist"""
        print "UNIMPLEMENTED"
    
    def details(self, prefix):
        path = os.path.join(self.bugsdir,self.detailsdir,self[prefix]['id']+".txt")
        if (not os.path.exists(path)):
            raise NoDetails(prefix)
        if os.path.isdir(path):
            raise InvalidDetailsFile(prefix)
        
        f = open(path)
        text = f.read()
        f.close()
        
        text = re.sub("(?m)^#.*\n", "", text)
        
        while True:
            oldtext = text
            retext = re.sub("\[\w+\]\s+\[", "[", text)
            text = retext
            if oldtext == retext:
                break
        
        text = re.sub("\[\w+\]\s*$", "", text)
        
        print(text.strip())
    
    def edit(self, prefix, editor='notepad'):
        """Allows the user to edit the details of the specified bug"""
        print "UNIMPLEMENTED"
    
    def comment(self, prefix, comment):
        """Allows the user to add a comment to the bug without launching an editor"""
        print "UNIMPLEMENTED"
    
    def resolve(self, prefix):
        """Marks a bug as resolved"""
        task = self[prefix]
        task['open'] = 'False'
    
    def reopen(self, prefix):
        """Reopens a bug that was previously resolved"""
        task = self[prefix]
        task['open'] = 'True'
    
    def list(self,open=True,owner='*',grep=''):
        """Lists all bugs, applying the given filters"""
        tasks = dict(self.bugs.items())
        
        prefixes = _prefixes(tasks).items()
        for task_id, prefix in prefixes:
            tasks[task_id]['prefix'] = prefix
        
        small = [task for task in tasks.values() if _truth(task['open'],open) and (owner == '*' or owner == task['owner']) and grep.lower() in task['text'].lower()]
        if len(small) > 0:
            prefs = [len(task['prefix']) for task in small]
            plen = max(prefs)
        else:
            plen = 0
        for task in small:
            print '%s - %s' % (task['prefix'].ljust(plen),task['text'])
        print(_describe_print(len(small),open,owner,grep))

#
# Mercurial Extention Operations
# These are used to allow the tool to work as a Hg Extention
#
# cmd name        function call
#
def _findrepo(p):
    while not os.path.isdir(os.path.join(p, ".hg")):
        oldp, p = p, os.path.dirname(p)
        if p == oldp:
            return None
    return p

def cmd(ui,repo,cmd = '',*args,**opts):
    text = (' '.join(args)).strip();
    #print "cmd: %s" % cmd
    #print "opts: %s" % opts
    #print "args: %s\n" % text
    try:
        auto_detail = ui.configbool("bugs","auto-detail",True)
        bugsdir = ui.config("bugs","dir",".bugs")
        path = _findrepo(os.getcwd())
        if not path:
            raise NotInRepo
        os.chdir(path)
        bd = BugsDict(auto_detail,bugsdir)
        if cmd == 'add':
            bd.add(text)
            bd.write()
        elif cmd == 'rename':
            bd.rename(opts['id'], text)
            bd.write()
        elif cmd == 'assign':
            bd.assign(opts['id'], text, opts['force'])
            bd.write()
        elif cmd == 'details':
            bd.details(opts['id'])
        elif cmd == 'edit':
            bd.edit(opts['id'], ui.geteditor())
        elif cmd == 'comment':
            bd.comment(opts['id'], text)
        elif cmd == 'resolve':
            bd.resolve(opts['id'])
            bd.write()
        elif cmd == 'reopen':
            bd.reopen(opts['id'])
            bd.write()
        elif cmd == 'list':
            bd.list(not opts['resolved'], opts['owner'], opts['grep'])
    
    except Exception, e:
        sys.stderr.write('An Error Was Raised: %s\n%s\n%s\n%s\n%s' % (e.__class__,e.args,e.message,e.__dict__,e.__doc__))

    #open=True,owner='*',grep='',verbose=False,quiet=False):
cmdtable = {"bug": (cmd,[('i', 'id', '', 'Pass ID'),
                         ('f', 'force', False, 'Force username'),
                         ('r', 'resolved', False, 'List resolved bugs'),
                         ('o', 'owner', '*', 'Specify an owner'),
                         ('g', 'grep', '', 'Filter titles by')],"cmd")}
