.. workers documentation master file, created by
   sphinx-quickstart on Sun Sep 19 12:37:03 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Workers: Making Work Light
======================================

Workers is a threaded job pool interface that intends to make
farming out work to multiple threads easy. Workers reduces
the amount of boilerplate code needed to launch worker threads
and makes dispatching work straightforward.


Quick Start
===========

Running workers in the most basic way is as simple as:
a) creating a pool, b) queuing work, c) reading results.
You send work to the pool by putting a tuple containing a callable,
its positional arguments and keyword arguments on the inbox queue.

.. code-block:: python

   def download_file(uri, path):
       # ... example
       return path, bytes_fetched

   tofetch = [('http://example.org/index.html', 'ex.html')]
   with workers.pool(8) as pool:
       for uri, path in tofetch:
           pool.inbox.put((download_file, [uri, path], {}))
   for path, bytes in workerptool.iterqueue(pool.outbox):
        print 'file %s: %s bytes downloaded' % (path, bytes)

Every pool has an inbox, an outbox and an errbox. Workers take
work off the inbox, put their results on the outbox, and if an
exception is raised, puts it on the errbox. All three of these
are Queue objects that support the .put/.get methods. The programmer
can specify the boxes as arguments but if the are not given
default to Queue.Queue objects.

.. code-block:: python

   def multi_download(user_input):
       outbox = Queue.Queue()
       errbox = Queue.Queue()
       with workers.pool(8, outbox=outbox, errbox=errbox) as pool:
           for uri, path in user_input:
               pool.inbox.put((download_file, [uri, path], {}))
       for err in workers.iterqueue(errbox):
           raise err
       for path, bytes in workers.iterqueue(outbox):
           print 'file %s: %s bytes downloaded' % (path, bytes)

If you are familiar with threading in Python you might wonder what
is happening under the covers. We can write this code in another way:

.. code-block:: python

   def multi_download(user_input):
       pool = workers.WorkerPool(8)
       try:
           for uri, path in user_input:
               pool.inbox.put((download_file, [uri, path], {}))
       finally:
           pool.exile()
       # process results ...

The WorkerPool object manages the threads and dispatches work to
them. The workers take the callable and its arguments and calls
it (shocking, isn't it). The exile function tells the pool to
shut down, but waits until all items have been taken off the
inbox (you can control this with an argument).

These are the basics, but there are more advanced ways to use
the workers module. Please take a look at the module documentation
and explore the library.


Workers: Details
====================

.. toctree::
   :maxdepth: 2

   module.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

