from asyncio import AbstractEventLoopPolicy, Task

class VertxRunner(AbstractEventLoopPolicy):
    def __init__(self, clustered=False):
        from .core.vertx import Vertx
        self.v = Vertx.vertx()

    def run(self, coro):
        Task(coro, loop=self)

    def call_later(self, delay, func, *args):
        def do_it(_):
            func(*args)
        self.v.set_timer(delay, do_it)

    def call_soon(self, func, *args):
        self.call_later(1, func, *args)

    def get_debug(self):
        return False


