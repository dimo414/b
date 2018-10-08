# b-test.py - Distributed Bug Tracker Extention for Mercurial
#
# Copyright 2010-2011 Michael Diamond <michael@digitalgemstones.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.
# http://www.gnu.org/licenses/licenses.html
# http://www.gnu.org/licenses/gpl.html
"""Standalone unit tests for b, simply run this file

This module can be run directly, or as a Mercurial hook.  Run as a hook,
it will prompt you if you would like to run the tests, and then stop the
command if a test fails.  It is suggested you use it with the precommit
hook, like so:

[hooks]
precommit=python:src/b-test.py:hook

This does not stop you from committing (simply tell it not to run the tests)
but is provided as a convenience to prevent regressions.  Tests should
always be run before pushing.
"""

import os, re, shutil, sys, tempfile, unittest
# adds everything in the same directory to pythonpath regardless of how the module is run
sys.path.append(os.path.dirname(__file__))
# Configures simple hashing
os.environ['HG_B_SIMPLE_HASHING'] = 'true'
import b

_debug = False

class Test(unittest.TestCase):
        
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        global _debug
        if _debug:
            print("Running tests on: %s\n"
                  "This directory WILL NOT be deleted at the end of this test" % self.dir)
        os.chdir(self.dir)
        b._simple_hash = True
        self.bd = b.BugsDict()
    
    def tearDown(self):
        global _debug
        if not _debug:
            shutil.rmtree(self.dir)
    
    def conclude(self):
        """Use at the end of tests to ensure data is being written to bugs dict successfully.
        
        Any operation that precedes a call to bd.write() in b's cmd function must be tested
        with this function.  Despite the name, it is safe to call at any point during a test,
        no data should be lost."""
        list = self.bd.list(alpha=True)
        self.bd.write()
        self.bd = b.BugsDict()
        self.assertEqual(list, self.bd.list(alpha=True))
        
    def test_helpers(self):
        """Tests the helper methods"""
        # Many of these are effectively tested by other tests
        # this test is for unusual edge cases.  If a helper method
        # has none, the method is simply run to ensure no exceptions
        
        #_datetime
        b._datetime()
        b._datetime(1310458238.24)
        
        #_hash
        b._hash("test")

        #_mkdir_p
        b._mkdir_p('dir/to/test/_mkdir_p')

        #_truth
        self.assertTrue(b._truth('True'))
        self.assertFalse(b._truth('False'))

        #_task_from_taskline
        good_list = [ # tasklines that should work
                     "",
                     "task",
                     "    task    | a:1, b:2, c:3, d:4, e:5",
                     "task|    id:13443, owner:, open: True, time: 1234",
                     "task|    id:13443, owner:somebody, open: True, time: 1234",
                     "task | taskpart | id:1234"
                     ]
        for tl in good_list:
            task = b._task_from_taskline(tl)
            self.assertEqual(task['text'],tl.rsplit('|',1)[0].strip())
        
        bad_list = [ # tasklines that should fail
                    "task|taskpart", # can't handle direct edit inserts with |
                    "task | id:12|34, owner=you?" # can't handle | in metadata
                    ]
        for tl in bad_list:
            self.assertRaises(b.InvalidTaskfile, b._task_from_taskline, tl)

        #_tasklines_from_tasks
        b._tasklines_from_tasks([
                                 {'text': "task", 'id':"4567"}
                                 ])
        
        #_prefixes
        prefix_gen = ['a','abb','bbb','bbbb','cdef','cghi','defg','defh','e123456789']
        self.assertEqual(b._prefixes(prefix_gen),{'a': 'a', 'abb': 'ab', 'defh': 'defh', 'cdef': 'cd',
                                             'e123456789': 'e', 'cghi': 'cg', 'bbbb': 'bbbb', 
                                             'bbb': 'bbb', 'defg': 'defg'})

        #_describe_print
        self.assertEqual(b._describe_print(1,True,'*',''),'Found 1 open bug')
        self.assertEqual(b._describe_print(10,True,'*',''),'Found 10 open bugs')
        self.assertEqual(b._describe_print(11,False,'*',''),'Found 11 resolved bugs')
        self.assertEqual(b._describe_print(12,True,'',''),'Found 12 open bugs owned by Nobody')
        self.assertEqual(b._describe_print(13,True,'Jack',''),'Found 13 open bugs owned by Jack')
        self.assertEqual(b._describe_print(14,True,'','Word'),'Found 14 open bugs owned by Nobody whose title contains Word')
        self.assertEqual(b._describe_print(15,True,'Jack','Word'),'Found 15 open bugs owned by Jack whose title contains Word')

    def test_private_methods(self):
        """Tests the private methods of BD"""
        # Like test_helpers, some methods may just be called to test that they don't raise an exception
        
        self.bd.add("test") #a94a8fe5cc
        self.bd.add("another test") #afc8edc74a
        
        #__getitem__
        self.assertRaises(b.UnknownPrefix, self.bd.__getitem__, 'b')
        self.assertRaises(b.AmbiguousPrefix, self.bd.__getitem__, 'a')
        self.assertEqual(self.bd['a9']['text'], 'test')
        self.assertEqual(self.bd['a94a']['text'], 'test')
        self.assertEqual(self.bd['afc8edc74a']['text'], 'another test')
        
        #_get_details_path
        id = self.bd.id('a9')
        _,path = self.bd._get_details_path(id)
        
        #_make_details_file
        self.bd._make_details_file(id)
        self.assertTrue(os.path.exists(path))
        
        #_user_list
        self.bd.assign('a9', 'User', True)
        self.assertEqual(len(self.bd._users_list()),2)
        
        #_get_user
        # tested more completely by test_users
        self.assertEqual(self.bd._get_user('us'),'User')
        
    def test_api(self):
        """Tests api functions that don't rely on Mercurial"""
        # Version
        self.assertTrue(b.version() > b.version("0.6.1"))
        
    def test_id(self):
        """Straightforward test, ensures ID function works"""
        self.bd.add("test")
        self.assertEqual(self.bd.id('a'),'a94a8fe5ccb19ba61c4c0873d391e987982fbbd3')
    
    def test_add(self):
        """Basic add functionality tested everywhere, edge cases here"""
        self.bd.add('test|with"bars,and\'other\tpotentially#bad{characters}')
        self.assertEqual(self.bd.list(), 'd - test|with"bars,and\'other\t'
                         'potentially#bad{characters}\nFound 1 open bug')
        self.assertEqual(self.bd.last_added_id,'deea8c528cd4fe5ff34b3a15bb97de097d99c4f2')
        self.conclude()
    
    def test_rename(self):
        """Tests total rename and sed-style rename"""
        self.bd.add('test')
        self.bd.rename('a','give the knife')
        self.assertEqual(self.bd.list(),'a - give the knife\nFound 1 open bug')
        self.conclude() # write to file, reload
        self.bd.rename('a', '/g|kn/l/')
        self.assertEqual(self.bd.list(),'a - live the life\nFound 1 open bug')
        self.conclude()
    
    def test_users(self):
        """Tests output of users command"""
        self.bd.add('unassigned')
        self.bd.user = 'User'
        self.bd.add('test')
        self.bd.add('another test')
        self.bd.add('resolved test')
        self.bd.resolve('8')
        self.bd.user = 'A User'
        self.bd.add('different test')
        self.assertEqual(self.bd.users(), 'Username: Open Bugs\nNobody: 1\nA User: 1\nUser:   2\n')
    
    def test_assign(self):
        """Tests user assignment and forcing of user creation"""
        self.bd.user = 'User'
        self.bd.add('test')
        self.bd.user = 'A User'
        self.bd.add('a test')
        self.bd.add('a new test')
        self.assertEqual(self.bd.users(),'Username: Open Bugs\nA User: 2\nUser:   1\n')
        self.bd.assign('9','u')
        self.conclude()
        self.assertEqual(self.bd.users(),'Username: Open Bugs\nA User: 1\nUser:   2\n')
        self.assertRaises(b.UnknownUser, self.bd.assign,'9','Newbie')
        self.bd.assign('9', 'Uther', True)
        self.assertEqual(self.bd.users(),'Username: Open Bugs\nA User: 1\nUther:  1\nUser:   1\n')
        self.assertRaises(b.AmbiguousUser, self.bd.assign, '9', 'u')
        
        self.conclude()
    
    def test_details(self):
        """Tests outputting of issue details with and without a details file"""
        self.bd.add('new test')
        self.assertTrue(re.match('Title: new test\nID: ce91fd20f393d261ea86e97fa26c273d02d43b4b\n'
                                 'Filed On: \w+, \w+ \d\d \d\d\d\d \d\d:\d\d[A|P]M'
                                 '\n\nNo Details File Found.',
                        self.bd.details('c')))
        self.bd.assign('c', 'User', True)
        self.bd.resolve('c')
        self.bd.user = 'Another User'
        self.bd.comment('c','Resolved an issue.\nHow nice!')
        self.assertTrue(re.match('Title: new test\nID: ce91fd20f393d261ea86e97fa26c273d02d43b4b\n'
                                 '\*Resolved\* Owned By: User\n'
                                 'Filed On: \w+, \w+ \d\d \d\d\d\d \d\d:\d\d[A|P]M\n\n'
                                 '\[comments\]\n\nBy: Another User\n'
                                 'On: \w+, \w+ \d\d \d\d\d\d \d\d:\d\d[A|P]M\nResolved an issue.\n'
                                 'How nice!',
                                 self.bd.details('c')))
                        
        
    
    def test_edit(self):
        """Edit does little more than launch an external editor.  Nothing to easily test for now."""
        pass
    
    def test_comment(self):
        """Confirms comment functionality works"""
        self.bd.add('test')
        self.bd.comment('a', 'This is a comment')
        self.assertTrue(re.match('Title: test\nID: a94a8fe5ccb19ba61c4c0873d391e987982fbbd3'
                        '\nFiled On: \w+, \w+ \d\d \d\d\d\d \d\d:\d\d[A|P]M\n\n\[comments\]\n\n'
                        'On: \w+, \w+ \d\d \d\d\d\d \d\d:\d\d[A|P]M\nThis is a comment',
                        self.bd.details('a')))
    
    def test_resolve(self):
        """Tests both resolve and reopen"""
        self.bd.add('test')
        self.bd.add('another test')
        self.assertEqual(self.bd.list(), 'af - another test\na9 - test\nFound 2 open bugs')
        self.bd.resolve('af')
        self.assertEqual(self.bd.list(), 'a9 - test\nFound 1 open bug')
        self.assertEqual(self.bd.list(False), 'af - another test\nFound 1 resolved bug')
        self.conclude()
        self.bd.reopen('af')
        self.bd.resolve('a9')
        self.assertEqual(self.bd.list(), 'af - another test\nFound 1 open bug')
        self.assertEqual(self.bd.list(False), 'a9 - test\nFound 1 resolved bug')
        
    def test_list(self):
        """Tests that the BD doesn't fail when calling list before the BD has done any work"""
        # empty list
        self.assertEqual(self.bd.list(),"Found 0 open bugs")
        self.bd.add("EFGH")
        # one item
        self.assertEqual(self.bd.list(),"a - EFGH\nFound 1 open bug")
        self.bd.add("ABCD")
        self.bd.add("IJKL")
        # additional items, ordered by ID
        self.assertEqual(self.bd.list(),"a - EFGH\nf - ABCD\n6 - IJKL\nFound 3 open bugs")
        # ordered by title
        self.assertEqual(self.bd.list(alpha=True),"f - ABCD\na - EFGH\n6 - IJKL\nFound 3 open bugs")
        # ordered by creation time
        self.assertEqual(self.bd.list(chrono=True),"a - EFGH\nf - ABCD\n6 - IJKL\nFound 3 open bugs")
        
        # TODO truncate
        # how should we test truncate in a platform independent fashion?
        
        self.conclude()
    
    def test_list_filters(self):
        """Tests list's filter functionality.
          Filter by owner and by grep - resolution is tested in test_resolve
        """
        self.bd.add('ABCD')
        self.bd.assign('fb','Someone',True)
        self.bd.add('DEFG')
        self.bd.user = 'User'
        self.bd.add('GHIJ')
        self.bd.add('JKLM')
        self.assertEqual(self.bd.list(owner='me'),'f1 - GHIJ\n4  - JKLM\nFound 2 open bugs owned by User')
        self.assertEqual(self.bd.list(owner='no'),'b - DEFG\nFound 1 open bug owned by Nobody')
        self.assertEqual(self.bd.list(owner='some'),'fb - ABCD\nFound 1 open bug owned by Someone')
        self.assertEqual(self.bd.list(grep='D'),'fb - ABCD\nb  - DEFG\nFound 2 open bugs whose title contains D')
        self.assertEqual(self.bd.list(grep='h'),'f1 - GHIJ\nFound 1 open bug whose title contains h')
        self.assertEqual(self.bd.list(owner='u',grep='j'),'f1 - GHIJ\n4  - JKLM\nFound 2 open bugs owned by User whose title contains j')
            
    def test_speed(self):
        """Tests the speed of generating and listing a large BD.
        
        Operations being timed:
          List sorted
          Write file
          Read file
          List sorted
          Compare lists to confirm equality
        
        If this fails, confirm that the most recent tagged release does not also fail,
        and then try to identify what expensive changes have been made between then
        and now.  If the most recent tagged release does not fail this test, no changes
        may be permitted to cause this test to fail.
        """
        timelimit = 4   # seconds to allow to run
        numbugs = 10000 # number of bugs to create before testing - increase this when possible
        self.bd.fast_add = True
        for i in range(0,numbugs):
            self.bd.add('This is bug %s - be nice to it' % str(i))
            
        import timeit
        t = timeit.Timer(self.conclude)
        time = t.timeit(1)
        msg = "Accessing a large list took %.3f seconds - not allowed to exceed %s seconds." % (time,timelimit)
        self.assertTrue(time <= timelimit, msg)
        
        self.bd.list()

def hook(ui, repo, *args, **opts):
    # TODO move hook into a shell script so it can call this and BATS
    if ui.promptchoice("Would you like to run unit tests before committing? (Y/n):$$ &Yes $$ &No") == 0:
        suite = unittest.TestLoader().loadTestsFromTestCase(Test)
        result = unittest.TextTestRunner().run(suite)
        return len(result.errors)+len(result.failures)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'help':
        print("Run unit tests against b.py.  No arguments runs all tests, or you can pass the suffix of "
              "one or more test methods from this file, such as helpers, add, or assign - see the "
              "source for all possible tests.")
        sys.exit()
    sys.argv = sys.argv[0:1] + ['Test.test_'+n for n in sys.argv[1:]]
    unittest.main()