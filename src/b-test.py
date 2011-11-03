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

import os, shutil, sys, tempfile, unittest
# adds everything in the same directory to pythonpath regardless of how the module is run
sys.path.append(os.path.dirname(__file__))
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
        """Use at the end of tests to ensure data is being written to bugs dict successfully"""
        list = self.bd.list()
        self.bd.write()
        self.bd = b.BugsDict()
        self.assertEqual(list, self.bd.list())
        
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
        
    def test_id(self):
        pass
    
    def test_add(self):
        pass
    
    def test_rename(self):
        pass
    
    def test_users(self):
        pass
    
    def test_assign(self):
        pass
    
    def test_details(self):
        pass
    
    def test_edit(self):
        pass
    
    def test_comment(self):
        pass
    
    def test_resolve(self):
        pass
    
    def test_reopen(self):
        pass
        
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
        
        self.conclude()
    
    def test_list_filters(self):
        pass
    
    def test_speed(self):
        for i in range(1,10):
            self.bd.add(str(i))
        
        self.conclude()
        
        self.bd.list()

def hook(ui, repo, *args, **opts):
    if ui.promptchoice("Would you like to run unit tests before committing? (y/n):",['&No','&Yes']):
        suite = unittest.TestLoader().loadTestsFromTestCase(Test)
        unittest.TextTestRunner().run(suite)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.test_list_empty']
    unittest.main()