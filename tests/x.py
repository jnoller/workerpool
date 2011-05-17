import workers

def _tfunc(val, blah=None):
    return val + 1

def test_process_pool():
    wc = 10
    import multiprocessing
    x = workers.WorkerPool(4, workerclass=workers.ProcessWorker,
                              queueclass=multiprocessing.JoinableQueue,
                              eventclass=multiprocessing.Event)

    for i in range(wc):
        x.inbox.put((_tfunc, [1], {}))
    x.exile()
    results = [i for i in workers.iterqueue(x.outbox)]
    print len(results), ' ', wc

if __name__ == "__main__":
    test_process_pool()
