""" Handles coroutines and futures. 

This module contains objects used to interact with the Vert.x
JVM using coroutines. It is based on the tornado coroutine
implementation.

"""
import sys
import types
import textwrap
import functools
from concurrent.futures import Future

try:
    from collections.abc import Generator as GeneratorType  # py35+
except ImportError:
    from types import GeneratorType

try:
    from inspect import isawaitable  # py35+
except ImportError:
    def isawaitable(x): return False


class KeyReuseError(Exception):
    pass


class UnknownKeyError(Exception):
    pass


class LeakedCallbackError(Exception):
    pass


class BadYieldError(Exception):
    pass


class Return(Exception):
    def __init__(self, val):
        self.value = val


def coroutine(func):
    # On Python 3.5, set the coroutine flag on our generator, to allow it
    # to be used with 'await'.
    if hasattr(types, 'coroutine'):
        func = types.coroutine(func)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        future = Future()

        try:
            result = func(*args, **kwargs)
        except (Return, StopIteration) as e:
            result = getattr(e, 'value', None)
        except Exception as e:
            future.set_exception(e)
            return future
        else:
            if isinstance(result, GeneratorType):
                # Inline the first iteration of Runner.run.  This lets us
                # avoid the cost of creating a Runner when the coroutine
                # never actually yields, which in turn allows us to
                # use "optional" coroutines in critical path code without
                # performance penalty for the synchronous case.
                try:
                    yielded = next(result)
                except (StopIteration, Return) as e:
                    future.set_result(getattr(e, 'value', None))
                except Exception as e:
                    future.set_exception(e)
                else:
                    Runner(result, future, yielded)
                try:
                    return future
                finally:
                    # Subtle memory optimization: if next() raised an exception,
                    # the future's exc_info contains a traceback which
                    # includes this stack frame.  This creates a cycle,
                    # which will be collected at the next full GC but has
                    # been shown to greatly increase memory usage of
                    # benchmarks (relative to the refcount-based scheme
                    # used in the absence of cycles).  We can avoid the
                    # cycle by clearing the local variable after we return it.
                    future = None
        future.set_result(result)
        return future
    return wrapper

class VertxRunner():
    def run_until_complete(self, coro):
        return coro.result()

_null_future = Future()
_null_future.set_result(None)

class Runner(object):
    """Engine used to drive a running coroutine.

    Maintains information about pending callbacks and their results.

    The results of the generator are stored in ``result_future`` (a
    `.Future`)
    """
    def __init__(self, gen, result_future, first_yielded):
        self.gen = gen
        self.result_future = result_future
        self.future = _null_future
        self.yield_point = None
        self.pending_callbacks = None
        self.results = None
        self.running = False
        self.finished = False
        self.had_exception = False
        if self.handle_yield(first_yielded):
            self.run()

    def register_callback(self, key):
        """Adds ``key`` to the list of callbacks."""
        if self.pending_callbacks is None:
            # Lazily initialize the old-style YieldPoint data structures.
            self.pending_callbacks = set()
            self.results = {}
        if key in self.pending_callbacks:
            raise KeyReuseError("key %r is already pending" % (key,))
        self.pending_callbacks.add(key)

    def is_ready(self, key):
        """Returns true if a result is available for ``key``."""
        if self.pending_callbacks is None or key not in self.pending_callbacks:
            raise UnknownKeyError("key %r is not pending" % (key,))
        return key in self.results

    def set_result(self, key, result):
        """Sets the result for ``key`` and attempts to resume the generator."""
        self.results[key] = result
        if self.yield_point is not None and self.yield_point.is_ready():
            try:
                self.future.set_result(self.yield_point.get_result())
            except Exception as e:
                self.future.set_exception(e)
            self.yield_point = None
            self.run()

    def run(self, result=None):
        """Starts or resumes the generator, running until it reaches a
        yield point that is not ready.
        """
        if self.running or self.finished:
            return
        try:
            self.running = True
            while True:
                future = self.future
                if not future.done():
                    return
                self.future = None
                try:
                    exc_info = None

                    try:
                        value = future.result()
                    except Exception:
                        self.had_exception = True
                        exc_info = sys.exc_info()

                    if exc_info is not None:
                        yielded = self.gen.throw(*exc_info)
                        exc_info = None
                    else:
                        yielded = self.gen.send(value)
                except (StopIteration, Return) as e:
                    self.finished = True
                    self.future = _null_future
                    if self.pending_callbacks and not self.had_exception:
                        # If we ran cleanly without waiting on all callbacks
                        # raise an error (really more of a warning).  If we
                        # had an exception then some callbacks may have been
                        # orphaned, so skip the check in that case.
                        raise LeakedCallbackError(
                            "finished without waiting for callbacks %r" %
                            self.pending_callbacks)
                    self.result_future.set_result(getattr(e, 'value', None))
                    self.result_future = None
                    return
                except Exception as e:
                    self.finished = True
                    self.future = _null_future
                    self.result_future.set_exception(e)
                    self.result_future = None
                    return
                if not self.handle_yield(yielded):
                    return
        finally:
            self.running = False

    def handle_yield(self, yielded):
        try:
            self.future = convert_yielded(yielded)
        except BadYieldError as e:
            self.future = Future()
            self.future.set_exception(e)

        if not self.future.done():
            self.future.add_done_callback(self.run)
            return False
        return True

if sys.version_info >= (3, 3):
    exec(textwrap.dedent("""
    @coroutine
    def _wrap_awaitable(x):
        return (yield from x)
    """))
else:
    def _wrap_awaitable(x):
        raise NotImplementedError()

def convert_yielded(yielded):
    """ Convert a yielded object into a Future. """
    if isinstance(yielded, Future):
        return yielded
    elif isawaitable(yielded):
        return _wrap_awaitable(yielded)
    else:
        raise BadYieldError("yielded unknown object %r" % (yielded,))
