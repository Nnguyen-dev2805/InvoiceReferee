"""One-process, one-active-run executor (T08, System §8).

The MVP keeps a single executor inside one app process. ``RunExecutor`` owns:

- a ``ThreadPoolExecutor(max_workers=1)`` that runs the pipeline OFF the request
  thread, so the API can return a run immediately and the UI can poll/Stop;
- a single-permit semaphore ("the slot") that ``acquire`` rejects while a run is
  in flight (``RUN_BUSY``). The permit is released by the WORKER when it
  finishes, so the slot is held for the whole run — a queued second run can never
  start, and ``set_policy`` (idle-only) is refused while a run is running.

There is deliberately no broker, worker fleet, lease, crash-recovery engine or
concurrent-user infrastructure (System §8). ``CaseService`` holds one executor
per instance; resources are never global.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Semaphore
from typing import Callable

from invoice_referee.domain.models import DomainError


class RunExecutor:
    """A single-slot background executor. ``acquire`` gates the one active run."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='invoice-run')
        self._slot = Semaphore(1)

    def acquire(self) -> None:
        """Take the run slot or raise ``RUN_BUSY`` (never blocks)."""
        if not self._slot.acquire(blocking=False):
            raise DomainError('RUN_BUSY', 'Đang có một run chạy; hãy chờ hoặc Stop run hiện tại.')

    def release(self) -> None:
        """Release the slot without starting a run (caller error/deny path)."""
        self._slot.release()

    def submit(self, work: Callable[[], None]) -> Future:
        """Schedule ``work``; the WORKER releases the slot when it finishes.

        The caller must have acquired the slot first. Ownership of the release
        transfers to the worker, so the caller must NOT release after submitting.
        """
        def _wrapped() -> None:
            try:
                work()
            finally:
                self._slot.release()

        return self._pool.submit(_wrapped)

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting work and (by default) wait for the running worker."""
        self._pool.shutdown(wait=wait)


__all__ = ['RunExecutor']
