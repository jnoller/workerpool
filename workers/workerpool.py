"""
workerpool.py

Simple to use/compose threadpool(s) and worker classes. Most uses of this can
be boiled down to a simple example::

    with workerpool.pool(10) as pool:
        for original in _walk(sdir):
            dest = change_root(tdir, original)
            pool.inbox.put((_copy, [original, dest], {}))
    results = [i for i in worker.iterqueue(pool.outbox)]
    errors = [i for i in workerpool.iterqueue(pool.errbox)]
    print results, errors

This uses the :func:`pool` context manager to give you a threadpool of 10
workers. You then use the inbox (outbox/errbox) of the pool to communicate or
retrieve values from the workers.

Also included is a self-managing version of the :class:`WorkerPool` called
:class:`SummoningPool` which will monitor the amount of work versus the number
of workers and summon/banish workers from the pool as needed to stick to the
passed in ratio value.

In the case of all pools, the inbox is used to communicate work to the children
- there is an expected format::

    (func, [], {})

This maps to the function or method the worker should call, along with the args
and kwargs. Any value returned from the work func is put in the outbox. Any 
exceptions raised are put in the errbox. These boxes can be accessed within the
pool context, but they are only guaranteed to contain all completed work after
exiting the pool context or if you call exile() on your own.

Occasionally, there is a need to have a data structure per-thread. For simple
situations where subclassing :class:``Worker`` is too much work, the
WorkerPool constructors accept a ``worker_setup`` callback argument. When
a worker begins running it will call the callback with itself as the single
argument. The object that is returned from this call is kept locally and
passed to the work func as an extra keyword argument.

We've forgone the magic of having an add_work method which would intelligently
detect what was being passed into the inbox in favor of something more 
explicit.  If you wanted the magic of something which didn't need the explicit
inbox tuple, you can implement your own :class:`Worker` class which performs
the calling/execution of the work within the inbox differently::

    class MyWorker(threading.Thread)
    ...
    def run(self):

        self._run.wait()
        time.sleep(self.stagger)
        while not self._stop.isSet():
            if self._banished.isSet():
                return
            if not self._run.isSet():
                self._run.wait()
            try:
                # Change this code right here:
                thingie, args, kwargs = self.inbox.get(block=True, timeout=1)
                # End changed code
                try:
                    result = thingie(*args, **kwargs)
                    self.outbox.put(result)
                except Exception, e:
                    self.errbox.put(e)
                finally:
                    self.inbox.task_done()

            except Queue.Empty:
                pass


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
from __future__ import with_statement


__all__ = ['Worker','SummoningPool', 'Watchman', 'WorkerPool', 'iterqueue',
           'pool', 'summoning_pool', 'DummyQueue', 'ProcessWorker']


from contextlib import contextmanager
import Queue
import threading
import multiprocessing
import time


_SENTINEL = object()
_SENTINEL = 'POOP'


class Worker(threading.Thread):
    """ Basic worker thread - this thread waits on the run event (which is
    implicitly called on pool start()) and loops on the inbox queue until told
    to stop. As each task is pulled (destructively) from the inbox, it is
    assumed that the format of the task is::

        (func, [], {})

    If this assumption doesn't jive with your usecase; you can subclass this
    class and replace the run method. Noting of course, you should keep the
    logic of when to stop/start and handle exceptions in place.

    :param run: A threading.Event object indicating that the thread should run.
    :param stop: A threading.Event object indicating that the thread should
                stop execution, and exit.
    :param inbox: The main queue for inbound tasks.
    :param outbox: The queue to store results in.
    :param errbox: The queue to store exceptions in if a task results in one.
    :param worker_setup: Optional - a callback function that returns a worker
                         local object. The callback should accept a single
                         argument for the worker object
    :param name: Optional - the identified to append onto Worker-{name}
    :param stagger: Optional - how long to sleep before beginning work.
    """

    def __init__(self, run, stop, inbox, outbox, errbox, worker_setup=None,
                 name=None, stagger=0):
        super(Worker, self).__init__()
        self._run = run
        self._stop = stop
        self.inbox = inbox
        self.outbox = outbox
        self.errbox = errbox
        self.stagger = stagger
        self.worker_setup = worker_setup
        self._banished = threading.Event()

        self.setName("Worker-%s" % (name or 'x'))

    def banish(self):
        """ Banish this worker to icy nothingness.
        """
        self._banished.set()

    def run(self):
        """ Loop on the inbox until we're told not to.
        """
        self._run.wait()
        time.sleep(self.stagger)
        if self.worker_setup:
            worker_data = self.worker_setup(self)
        else:
            worker_data = None
        while not self._stop.isSet():
            if self._banished.isSet():
                return
            if not self._run.isSet():
                self._run.wait()
            try:
                # use a blocking get w/ timeout to reduce contention
                # on the queue if a writer is trying to compete with lots
                # of readers. This drags shutdown time out, but is better
                thingie, args, kwargs = self.inbox.get(block=True, timeout=1)
                try:
                    result = self.call_func(thingie, args, kwargs, worker_data)
                    self.outbox.put(result)
                except Exception, e:
                    self.errbox.put(e)
                finally:
                    self.inbox.task_done()

            except Queue.Empty:
                pass

    def call_func(self, func, args, kwargs, worker_data=None):
        """ Execute the callable object passed in as ``func`` with
        the given positional and keyword args. If worker_data has been
        created it is also passed in as a keyword argument.

        :param func: A callable object
        :param args: A list of arguments to be passed to func
        :param kwargs: A dict of keyword arguments to be passed to func
        :param worker_data: An object passed to func as an additional
                            keyword if defined
        """
        if worker_data is not None:
            # do not mangle the orignal kwargs, because there is the
            # possibility the user plans on using it again
            kwargs = dict(kwargs)
            kwargs['worker_data'] = worker_data
        return func(*args, **kwargs)


class ProcessWorker(multiprocessing.Process):
    def __init__(self, run, stop, inbox, outbox, errbox, worker_setup=None,
                 name=None, stagger=0):
        super(ProcessWorker, self).__init__()
        self._run = run
        self._stop = stop
        self.inbox = inbox
        self.outbox = outbox
        self.errbox = errbox
        self.stagger = stagger
        self.worker_setup = worker_setup
        self._banished = threading.Event()

        self.name = "Worker-%s" % (name or 'x')

    def banish(self):
        """ Banish this worker to icy nothingness.
        """
        self._banished.set()

    def run(self):
        """ Loop on the inbox until we're told not to.
        """
        self._run.wait()
        time.sleep(self.stagger)
        if self.worker_setup:
            worker_data = self.worker_setup(self)
        else:
            worker_data = None
        while not self._stop.is_set():
            if self._banished.is_set():
                return
            if not self._run.is_set():
                self._run.wait()
            try:
                # use a blocking get w/ timeout to reduce contention
                # on the queue if a writer is trying to compete with lots
                # of readers. This drags shutdown time out, but is better
                thingie, args, kwargs = self.inbox.get(block=True, timeout=1)
                try:
                    result = self.call_func(thingie, args, kwargs, worker_data)
                    print 'done'
                    self.outbox.put(result)
                except Exception, e:
                    self.errbox.put(e)
                finally:
                    self.inbox.task_done()

            except Queue.Empty:
                pass

    def call_func(self, func, args, kwargs, worker_data=None):
        """ Execute the callable object passed in as ``func`` with
        the given positional and keyword args. If worker_data has been
        created it is also passed in as a keyword argument.

        :param func: A callable object
        :param args: A list of arguments to be passed to func
        :param kwargs: A dict of keyword arguments to be passed to func
        :param worker_data: An object passed to func as an additional
                            keyword if defined
        """
        if worker_data is not None:
            # do not mangle the orignal kwargs, because there is the
            # possibility the user plans on using it again
            kwargs = dict(kwargs)
            kwargs['worker_data'] = worker_data
        return func(*args, **kwargs)


class WorkerPool(threading.Thread):
    """
    Main pool management/creation class.

    :param wcount: Number of workers to create.
    :param stagger: Optional: In seconds, the amount for each thread to sleep
                    before starting. This means if you have 10 threads, the
                    10th thread will sleep 10 seconds before beginning work.
    :param inbox: Optional: a Queue to use for the inbound tasks
    :param outbox: Optional: a Queue to use for the results from the tasks
    :param errbox: Optional: a Queue to use for the errors a given task may get
    :param suffix: Optional: a string to append to the worker thread's name
    :param workerclass: Optional: A different class than the default
                        :class:`Worker` to instantiate to do the work.
    :param worker_setup: Optional: A callback function that accepts one arg,
                         see worker_setup on :class:`Worker` for details.
    """

    def __init__(self, wcount, stagger=0,
                 inbox=None, outbox=None, errbox=None, suffix=None,
                 workerclass=Worker, queueclass=Queue.Queue,
                 eventclass=threading.Event,
                 worker_setup=None):
        super(WorkerPool, self).__init__()

        self.inbox = inbox or queueclass()
        self.outbox = outbox or queueclass()
        self.errbox = errbox or queueclass()
        self.suffix = suffix
        self.workerclass = workerclass
        self.worker_setup = worker_setup
        self._run = eventclass()
        self._stop = eventclass()
        self.setName("WorkerPool-%s" % wcount)
        self.pool = []
        self.summon(wcount, stagger=stagger)
        self.start()

    def __getattr__(self, name): #py2.5 compat
        if name == 'name':
            return self.getName()

    def poolsize(self):
        """ Return the size of the current pool.
        """
        return len(self.pool)

    def summon(self, count, stagger=0):
        """ Summon (spawn) `count` workers and add them to the workerpool -
        you can optionally define a stagger (in sec) to force all of the new
        workers to sleep before starting (ramp)

        :param count: An integer value indicating how many threads to add.
        :param stagger: Optional - How long to space each thread's startup out
                        - this means that if you make 10 threads, thread 1 will
                        start in 0 sec, and thread 10 in 10 secs. Useful for
                        ramping.
        """
        cstagger = 0
        for cn in range(count):
            cstagger += stagger
            if self.suffix:
                cn = '%s-%s' % (cn, self.suffix)
            wk = self.workerclass(self._run, self._stop, self.inbox,
                                  self.outbox, self.errbox, name=cn,
                                  worker_setup=self.worker_setup,
                                  stagger=cstagger)
            wk.start()
            self.pool.append(wk)

    def banish(self, count):
        """ Banish `count` workers - if count is > than the current pool, the
        entire pool is banished, and then we can't have nice things.

        :param count: An integer value indicating how many threads to banish
                      from the pool.
        """
        banished = []
        for _ in range(min(count, len(self.pool))):
            worker = self.pool.pop()
            worker.banish()
            banished.append(worker)

        for worker in banished:
            worker.join()

    def run(self):
        """ Start the pool running
        """
        self._run.set()

    def pause(self):
        """ Pause the pool; this does not stop them
        """
        self._run.clear()

    def stop(self, join=True):
        """ Stop the pool; all workers will halt and exit - if join is True
        (the default) then the inbox will be joined *prior* to the stop flag
        being set.

        :param join: Optional - indicate if the inbox queue should be joined
                     `before` the individual worker threads. This means that
                     the inbox will be `completed` prior to thread shutdown.
        """
        if join:
            self.inbox.join()
        self._stop.set()
        for worker in self.pool:
            worker.join()

    def exile(self, join=True):
        """ Perform a total shutdown of this pool - this means that we call
        stop(join=join) and then join ourself.
        """
        self.stop(join=join)
        self.join()


class Watchman(threading.Thread):
    """ Watchman class; watches the pool and will generate/remove threads based
    on the ratio and current number of workers.

    :param wcount: The initial worker count.
    :param maxw: Maximum number of threads to create.
    :param rate: The rate at which to spawn new workers.
    :param ratio: The ratio of work / workers at which to summon or banish new
                  threads.
    :param interval: How frequently to poll the current work queue and pool
                     size and summon/banish new workers.
    :param pool: The :class:`WorkerPool` to watch.
    """

    def __init__(self, wcount, maxw, rate, ratio, interval, pool):
        super(Watchman, self).__init__()
        self.daemon = True
        self.wcount = wcount
        self.maxw = maxw
        self.rate = rate
        self.ratio = ratio
        self.interval = interval
        self.pool = pool
        self.stop = threading.Event()

    def run(self):
        """ Primary watchman run method - never called directly
        """
        while not self.stop.isSet():
            size = self.pool.inbox.qsize()
            psize = self.pool.poolsize()
            if size and psize:
                current = (size / self.pool.poolsize())
                if current > self.ratio and (psize < self.maxw):
                    spawn = min([self.rate, (self.maxw - psize)])
                    self.pool.summon(spawn)
                elif current < self.ratio:
                    self.pool.banish(self.rate)
            else:
                if psize > self.wcount:
                    self.pool.banish(self.rate)
            time.sleep(self.interval)


class SummoningPool(WorkerPool):
    """ SummoningPool is a subclass of WorkerPool which monitors the current
    threadpool within the workerpool, and if it is below a certain ratio of
    (work / workers), it will summon more threads to the pool. The inverse is
    also true, if there are more threads than work ((work / workers) < ratio)
    worker threads will be banished. See :meth:`Watchman.run` for the precise
    logic.

    :param wcount: Number of workers to create.
    :param maxw: Maximum number of threads to create.
    :param rate: How many threads to create if the ratio is met.
    :param interval: Seconds, how frequently to perform the check on the pool
                     and work queue. This dictates how quickly we can
                     generate threads.
    :param inbox: Optional: a Queue to use for the inbound tasks
    :param outbox: Optional: a Queue to use for the results from the tasks
    :param errbox: Optional: a Queue to use for the errors a given task may get
    :param suffix: Optional: a string to append to the worker thread's name
    :param workerclass: Optional: A different class than the default
                        :class:`Worker` to instantiate to do the work.
    :param worker_setup: Optional: A callback function that accepts one arg,
                         see worker_setup on :class:`Worker` for details.
    """

    def __init__(self, wcount, maxw, rate=1, ratio=10, interval=1,
                 inbox=None, outbox=None, errbox=None, suffix=None,
                 workerclass=Worker, worker_setup=None):
        super(SummoningPool, self).__init__(wcount, inbox=inbox,
                                            outbox=outbox, errbox=errbox,
                                            suffix=suffix,
                                            workerclass=workerclass,
                                            worker_setup=worker_setup)
        self.watcher = Watchman(wcount, maxw, rate, ratio, interval, self)
        self.watcher.start()

    def stop(self, join=True):
        """ Stop the pool; all workers will halt and exit - if join is True
        (the default) then the inbox will be joined *prior* to the stop flag
        being set.

        :param join: Optional - indicate if the inbox queue should be joined
                     `before` the individual worker threads. This means that
                     the inbox will be `completed` prior to thread shutdown.
        """
        self.watcher.stop.set()
        if join:
            self.inbox.join()
        self._stop.set()
        for worker in self.pool:
            worker.join()


@contextmanager
def pool(*args, **kwargs):
    """ Simple contextmanager which auto-exiles the pool when the caller is
    completed using it. The pool itself is passed back to the caller. *args and
    **kwargs are passed to the :class:`WorkerPool`.
    """
    pool = WorkerPool(*args, **kwargs)
    try:
        yield pool
    finally:
        pool.exile()


@contextmanager
def summoning_pool(*args, **kwargs):
    """ Simple contextmanager which auto-exiles the pool when the caller is
    completed using it. The pool itself is passed back to the caller. *args and
    **kwargs are passed to the :class:`SummoningPool`.
    """
    pool = SummoningPool(*args, **kwargs)
    try:
        yield pool
    finally:
        pool.exile()


def iterqueue(queue):
    """ Utility function to harvest results using a sentinel -
    inserts a None into the queue and then passes you back the results as a
    generator expression. Calling this before a threadpool is done writing to
    it will return only partial results

    :param queue: The queue to iterate.
    """
    queue.put(_SENTINEL)
    return (i for i in iter(queue.get, _SENTINEL))


class DummyQueue(Queue.Queue):
    """ A Queue that discards all items put on it and optionally calls
    a callback function (typically a logging function) with the item as
    the only argument.
    """

    def __init__(self, callback=None):
        """ Setup the parent and set a callback method if supplied """
        Queue.Queue.__init__(self)
        self.callback = callback

    def put(self, item, block=False, timeout=False):
        """ Do nothing, or if a callback is set, call it with the item
        as the only argument.
        """
        if self.callback:
            self.callback(item)
