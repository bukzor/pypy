from __future__ import with_statement
import py
import sys, os
from pypy.module.thread.test.support import GenericTestThread
from rpython.translator.c.test.test_genc import compile


class AppTestLock(GenericTestThread):

    def test_lock(self):
        import _thread
        lock = _thread.allocate_lock()
        assert type(lock) is _thread.LockType
        assert lock.locked() is False
        raises(_thread.error, lock.release)
        assert lock.locked() is False
        r = lock.acquire()
        assert r is True
        r = lock.acquire(False)
        assert r is False
        assert lock.locked() is True
        lock.release()
        assert lock.locked() is False
        raises(_thread.error, lock.release)
        assert lock.locked() is False
        feedback = []
        lock.acquire()
        def f():
            self.busywait(0.25)
            feedback.append(42)
            lock.release()
        assert lock.locked() is True
        _thread.start_new_thread(f, ())
        lock.acquire()
        assert lock.locked() is True
        assert feedback == [42]

    def test_lock_in_with(self):
        import _thread
        lock = _thread.allocate_lock()
        feedback = []
        lock.acquire()
        def f():
            self.busywait(0.25)
            feedback.append(42)
            lock.release()
        assert lock.locked() is True
        _thread.start_new_thread(f, ())
        with lock:
            assert lock.locked() is True
            assert feedback == [42]
        assert lock.locked() is False

    def test_timeout(self):
        import _thread
        assert isinstance(_thread.TIMEOUT_MAX, float)
        assert _thread.TIMEOUT_MAX > 1000
        lock = _thread.allocate_lock()
        assert lock.acquire() is True
        assert lock.acquire(False) is False
        assert lock.acquire(True, timeout=.1) is False

    def test_ping_pong(self):
        # The purpose of this test is that doing a large number of ping-pongs
        # between two threads, using locks, should complete in a reasonable
        # time on a translated pypy with -A.  If the GIL logic causes too
        # much sleeping, then it will fail.
        import _thread as thread, time
        COUNT = 100000 if self.runappdirect else 50
        lock1 = thread.allocate_lock()
        lock2 = thread.allocate_lock()
        def fn():
            for i in range(COUNT):
                lock1.acquire()
                lock2.release()
        lock2.acquire()
        print("STARTING")
        start = time.time()
        thread.start_new_thread(fn, ())
        for i in range(COUNT):
            lock2.acquire()
            lock1.release()
        stop = time.time()
        assert stop - start < 30.0    # ~0.6 sec on pypy-c-jit


def test_compile_lock():
    from rpython.rlib import rgc
    from rpython.rlib.rthread import allocate_lock
    def g():
        l = allocate_lock()
        ok1 = l.acquire(True)
        ok2 = l.acquire(False)
        l.release()
        ok3 = l.acquire(False)
        res = ok1 and not ok2 and ok3
        return res
    g._dont_inline_ = True
    def f():
        res = g()
        # the lock must have been freed by now - we use refcounting
        return res
    fn = compile(f, [], gcpolicy='ref')
    res = fn()
    assert res


class AppTestLockAgain(GenericTestThread):
    # test it at app-level again to detect strange interactions
    test_lock_again = AppTestLock.test_lock.im_func


class AppTestRLock(GenericTestThread):
    """
    Tests for recursive locks.
    """
    def test_reacquire(self):
        import _thread
        lock = _thread.RLock()
        lock.acquire()
        lock.acquire()
        lock.release()
        lock.acquire()
        lock.release()
        lock.release()

    def test_release_unacquired(self):
        # Cannot release an unacquired lock
        import _thread
        lock = _thread.RLock()
        raises(RuntimeError, lock.release)
        lock.acquire()
        lock.acquire()
        lock.release()
        lock.acquire()
        lock.release()
        lock.release()
        raises(RuntimeError, lock.release)

    def test_release_save(self):
        import _thread
        lock = _thread.RLock()
        lock.acquire()
        state = lock._release_save()
        lock._acquire_restore(state)
        lock.release()

    def test__is_owned(self):
        import _thread
        lock = _thread.RLock()
        assert lock._is_owned() is False
        lock.acquire()
        assert lock._is_owned() is True
        lock.acquire()
        assert lock._is_owned() is True
        lock.release()
        assert lock._is_owned() is True
        lock.release()
        assert lock._is_owned() is False

    def test_context_manager(self):
        import _thread
        lock = _thread.RLock()
        with lock:
            assert lock._is_owned() is True

    def test_timeout(self):
        import _thread
        lock = _thread.RLock()
        assert lock.acquire() is True
        assert lock.acquire(False) is True
        assert lock.acquire(True, timeout=.1) is True


class AppTestLockSignals(GenericTestThread):
    pytestmark = py.test.mark.skipif("os.name != 'posix'")

    def setup_class(cls):
        cls.w_using_pthread_cond = cls.space.wrap(sys.platform == 'freebsd6')

    def w_acquire_retries_on_intr(self, lock):
        import _thread, os, signal, time
        self.sig_recvd = False
        def my_handler(signal, frame):
            self.sig_recvd = True
        old_handler = signal.signal(signal.SIGUSR1, my_handler)
        try:
            def other_thread():
                # Acquire the lock in a non-main thread, so this test works for
                # RLocks.
                lock.acquire()
                # Wait until the main thread is blocked in the lock acquire, and
                # then wake it up with this.
                time.sleep(0.5)
                os.kill(os.getpid(), signal.SIGUSR1)
                # Let the main thread take the interrupt, handle it, and retry
                # the lock acquisition.  Then we'll let it run.
                time.sleep(0.5)
                lock.release()
            _thread.start_new_thread(other_thread, ())
            # Wait until we can't acquire it without blocking...
            while lock.acquire(blocking=False):
                lock.release()
                time.sleep(0.01)
            result = lock.acquire()  # Block while we receive a signal.
            assert self.sig_recvd
            assert result
        finally:
            signal.signal(signal.SIGUSR1, old_handler)

    def test_lock_acquire_retries_on_intr(self):
        import _thread
        self.acquire_retries_on_intr(_thread.allocate_lock())

    def test_rlock_acquire_retries_on_intr(self):
        import _thread
        self.acquire_retries_on_intr(_thread.RLock())

    def w_alarm_interrupt(self, sig, frame):
        raise KeyboardInterrupt

    def test_lock_acquire_interruption(self):
        if self.using_pthread_cond:
            skip('POSIX condition variables cannot be interrupted')
        import _thread, signal, time
        # Mimic receiving a SIGINT (KeyboardInterrupt) with SIGALRM while stuck
        # in a deadlock.
        # XXX this test can fail when the legacy (non-semaphore) implementation
        # of locks is used in thread_pthread.h, see issue #11223.
        oldalrm = signal.signal(signal.SIGALRM, self.alarm_interrupt)
        try:
            lock = _thread.allocate_lock()
            lock.acquire()
            signal.alarm(1)
            t1 = time.time()
            # XXX: raises doesn't work here?
            #raises(KeyboardInterrupt, lock.acquire, timeout=5)
            try:
                lock.acquire(timeout=5)
            except KeyboardInterrupt:
                pass
            else:
                assert False, 'Expected KeyboardInterrupt'
            dt = time.time() - t1
            # Checking that KeyboardInterrupt was raised is not sufficient.
            # We want to assert that lock.acquire() was interrupted because
            # of the signal, not that the signal handler was called immediately
            # after timeout return of lock.acquire() (which can fool assertRaises).
            assert dt < 3.0
        finally:
            signal.signal(signal.SIGALRM, oldalrm)

    def test_rlock_acquire_interruption(self):
        if self.using_pthread_cond:
            skip('POSIX condition variables cannot be interrupted')
        import _thread, signal, time
        # Mimic receiving a SIGINT (KeyboardInterrupt) with SIGALRM while stuck
        # in a deadlock.
        # XXX this test can fail when the legacy (non-semaphore) implementation
        # of locks is used in thread_pthread.h, see issue #11223.
        oldalrm = signal.signal(signal.SIGALRM, self.alarm_interrupt)
        try:
            rlock = _thread.RLock()
            # For reentrant locks, the initial acquisition must be in another
            # thread.
            def other_thread():
                rlock.acquire()
            _thread.start_new_thread(other_thread, ())
            # Wait until we can't acquire it without blocking...
            while rlock.acquire(blocking=False):
                rlock.release()
                time.sleep(0.01)
            signal.alarm(1)
            t1 = time.time()
            #raises(KeyboardInterrupt, rlock.acquire, timeout=5)
            try:
                rlock.acquire(timeout=5)
            except KeyboardInterrupt:
                pass
            else:
                assert False, 'Expected KeyboardInterrupt'
            dt = time.time() - t1
            # See rationale above in test_lock_acquire_interruption
            assert dt < 3.0
        finally:
            signal.signal(signal.SIGALRM, oldalrm)

