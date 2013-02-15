import sys


class AppTest:
    spaceconfig = dict(usemodules=['thread', 'signal'])

    def setup_class(cls):
        if (not cls.runappdirect or
                '__pypy__' not in sys.builtin_module_names):
            import py
            py.test.skip("this is only a test for -A runs on top of pypy")

    def test_enable_signals(self):
        import thread, signal, time
        #
        interrupted = []
        lock = thread.allocate_lock()
        lock.acquire()
        #
        def subthread():
            try:
                time.sleep(0.25)
                with thread.signals_enabled:
                    thread.interrupt_main()
            except BaseException, e:
                interrupted.append(e)
            lock.release()
        #
        thread.start_new_thread(subthread, ())
        lock.acquire()
        assert len(interrupted) == 1
        assert 'KeyboardInterrupt' in interrupted[0].__class__.__name__
