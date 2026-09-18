"""Acknowledged cross-thread handoff into the existing asyncio queue."""
import asyncio
from concurrent.futures import Future

class ThreadsafeQueueProxy:
    def __init__(self,queue,loop):self.queue,self.loop=queue,loop
    def full(self):return self.queue.full()
    def put_nowait(self,item):
        try:
            if asyncio.get_running_loop() is self.loop:
                return self.queue.put_nowait(item)
        except RuntimeError:
            pass
        acknowledgement=Future()
        def enqueue():
            if not acknowledgement.set_running_or_notify_cancel():return
            try:self.queue.put_nowait(item)
            except Exception as exc:acknowledgement.set_exception(exc)
            else:acknowledgement.set_result(None)
        self.loop.call_soon_threadsafe(enqueue)
        try:return acknowledgement.result(timeout=10)
        except TimeoutError:
            if not acknowledgement.cancel():
                return acknowledgement.result()  # callback running; observe actual outcome
            raise
