"""
workers unit tests

Copyright (c) 2010 Nasuni Corporation http://www.nasuni.com/

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import Queue
import threading
import time
import unittest

import workers


def _tfunc(val, blah=None):
    return val + 1


def _lazyfunc():
    time.sleep(.5)
    return True


def _tfunc_return(val, blah=None):
    return (_tfunc, [val], {})


def _recursive_return(val, blah=None):
    time.sleep(.01)
    return (_recursive_return, [val], {})


def _err(*args, **kwargs):
    raise Exception('error cond')


class TestWorker(unittest.TestCase):
    """ Tests for the worker class specifically
    """

    def setUp(self):
        self.inbox = Queue.Queue()
        self.outbox = Queue.Queue()
        self.errbox = Queue.Queue()
        self.run = threading.Event()
        self.stop = threading.Event()

    def test_worker_basic(self):
        x = workers.Worker(self.run, self.stop, self.inbox,
                              self.outbox, self.errbox, name='flob',
                              stagger=0.1)
        x.start()
        self.run.set()
        self.assertEqual(x.name, "Worker-flob")
        self.inbox.put((_tfunc, [1], {}))
        self.run.clear()
        self.run.set()
        self.inbox.join()
        self.assertEqual(self.outbox.qsize(), 1)
        x.banish()
        x.join()

    def test_worker_err(self):
        x = workers.Worker(self.run, self.stop, self.inbox,
                              self.outbox, self.errbox, name='flob')
        x.start()
        self.run.set()
        self.inbox.put((_err, [1], {}))
        self.inbox.join()
        self.assertEqual(self.errbox.qsize(), 1)
        x.banish()
        x.join()

    def test_worker_local_data(self):
        stuff = []
        def setup(worker):
            d = {'called': 0}
            stuff.append(d)
            return d
        def do_work(v, worker_data):
            worker_data['called'] += 1
            return v
        x = workers.Worker(self.run, self.stop, self.inbox,
                              self.outbox, self.errbox,
                              name='worker_with_data', worker_setup=setup)
        x.start()
        self.run.set()
        self.inbox.put((do_work, [1], {}))
        self.inbox.put((do_work, [2], {}))
        self.inbox.join()
        self.assertEqual(self.errbox.qsize(), 0)
        self.assertEqual(self.outbox.qsize(), 2)
        self.assertEqual(len(stuff), 1)
        self.assertEqual(stuff.pop()['called'], 2)
        x.banish()
        x.join()



class TestMisc(unittest.TestCase):

    def test_harvest(self):
        q = Queue.Queue()
        for _ in range(100):
            q.put(1)
        self.assertEqual(sum([i for i in workers.iterqueue(q)]), 100)


class TestWorkerThreadPool(unittest.TestCase):

    def setUp(self):
        self.wc = 10

    def test_basic_work(self):
        """ test the basic spawn, work, result cycle
        """
        x = workers.WorkerPool(self.wc)
        for i in range(self.wc):
            x.inbox.put((_tfunc, [1], {}))
        x.exile()
        results = [i for i in workers.iterqueue(x.outbox)]
        self.assertEqual(len(results), self.wc)
        self.assertEqual(x.name, "WorkerPool-%s" % self.wc)

    def test_exceptions(self):
        """ test the exception handling
        """
        x = workers.WorkerPool(self.wc)
        for i in range(self.wc):
            x.inbox.put((_err, [1], {}))
        x.exile()
        self.assertEqual(x.errbox.qsize(), self.wc)

    def test_pool_manip(self):
        """ Test the pool spin up and manipulation methods
        """
        x = workers.WorkerPool(self.wc)
        x.run()
        self.assertEqual(x.poolsize(), self.wc)
        x.summon(self.wc)
        self.assertEqual(x.poolsize(), self.wc * 2)
        x.banish(self.wc)
        self.assertEqual(x.poolsize(), self.wc)
        x.banish(self.wc)
        self.assertEqual(x.poolsize(), 0)

    def test_pause(self):
        """ Test the pause functionality - this is actually a PITA because of
        the speed at which a task/thread can execute on the queue. This is a
        best effort test.
        """
        x = workers.WorkerPool(self.wc)
        for i in range(self.wc * 2):
            x.inbox.put((_lazyfunc, [], {}))
        time.sleep(.6)
        x.pause()
        results = [i for i in workers.iterqueue(x.outbox)]
        self.assertEqual(len(results), 10)
        x.run()
        x.exile()
        results = [i for i in workers.iterqueue(x.outbox)]
        self.assertEqual(len(results), self.wc)

    def test_prodcom(self):
        """ Try making two pools - one of which's outbox is passed in as the
        inbox to a second pool - allows for easy producer/consumer constructs
        """
        prod = workers.WorkerPool(self.wc)
        com = workers.WorkerPool(self.wc, inbox=prod.outbox)
        for i in range(self.wc):
            prod.inbox.put((_tfunc_return, [1], {}))
        prod.exile()
        com.exile()
        results = [i for i in workers.iterqueue(com.outbox)]
        self.assertEqual(len(results), self.wc)

    def test_circle(self):
        """ As a lark - tie a prod->com->prod circle, this means we can ring
        them together, not something you'd want to do a lot, but it can be
        useful.
        """
        inbox = Queue.Queue()
        outbox = Queue.Queue()
        prod = workers.WorkerPool(self.wc, inbox=outbox, outbox=inbox)
        com = workers.WorkerPool(self.wc, inbox=inbox, outbox=outbox)
        for i in range(10):
            inbox.put((_recursive_return, [1], {}))
        com.exile()
        prod.exile()
        results = []
        results.extend([i for i in workers.iterqueue(outbox)])
        results.extend([i for i in workers.iterqueue(inbox)])
        self.assertEqual(len(results), 10)

    def test_pool_ctx(self):
        """ Test the pool contextmanager
        """
        with workers.pool(self.wc) as pool:
            for i in range(self.wc):
                pool.inbox.put((_tfunc, [1], {}))
        results = [i for i in workers.iterqueue(pool.outbox)]
        self.assertEqual(len(results), self.wc)

    def test_pool_ctx_error(self):
        """ Test the pool contextmanager when an error is raised
        """
        try:
            with workers.pool(self.wc) as pool:
                for i in range(self.wc):
                    pool.inbox.put((_tfunc, [1], {}))
                raise ValueError('foobar')
            err = None
        except Exception, e:
            err = e
        self.assertEqual(str(err), 'foobar')
        results = [i for i in workers.iterqueue(pool.outbox)]
        self.assertEqual(len(results), self.wc)

    def test_pool_with_worker_data(self):
        """ Test using a pool when setting worker local data.
        """
        stuff = []
        def setup(worker):
            d = {'called': 0}
            stuff.append(d)
            return d
        def do_work(v, worker_data):
            worker_data['called'] += 1
            return v
        with workers.pool(self.wc, worker_setup=setup) as pool:
            for idx in range(self.wc):
                pool.inbox.put((do_work, [idx], {}))
            pool.inbox.join()
        results = [i for i in workers.iterqueue(pool.outbox)]
        self.assertEqual(len(results), self.wc)
        self.assertEqual(len(stuff), self.wc)
        self.assertEqual(pool.errbox.qsize(), 0)

    def test_name_suffix(self):
        names = []
        def do_something():
            myname = threading.currentThread().getName()
            names.append(myname)
        with workers.pool(self.wc, suffix='foobly') as pool:
            for _ in range(self.wc):
                pool.inbox.put((do_something, [], {}))
            pool.inbox.join()
        for n in names:
            self.assertTrue(n.endswith('-foobly'))
        self.assertEqual(self.wc, len(names))


class TestSummoningPool(unittest.TestCase):

    def test_sp_basic(self):
        x = workers.SummoningPool(1, 10, rate=2, ratio=2, interval=0)
        x.pause()
        for _ in range(100):
            x.inbox.put((_lazyfunc, [], {}))
        x.run()
        sizes = []
        for _ in range(22):
            sizes.append(x.poolsize())
            time.sleep(.2)
        if sum(sizes): # Protect against a minor race. Need to rethink.
            self.assert_(sum(sizes) > 22, 'sum is %s' % sum(sizes))
        for val in sizes:
            self.assert_(val <= 10, '%s is over 10' % val)
        x.exile()

if __name__ == '__main__':
    unittest.main()
