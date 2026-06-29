from __future__ import annotations

import atexit
from dataclasses import dataclass
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    command: tuple[str, ...] | str | None
    running: bool
    started_at: float


@dataclass
class _ProcessRecord:
    process: Any
    command: tuple[str, ...] | str | None
    started_at: float


class ProcessManager:
    def __init__(
        self,
        *,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        terminate_timeout: float = 5,
        clock: Callable[[], float] = time.time,
        atexit_register: Callable[..., Any] = atexit.register,
    ):
        self._popen_factory = popen_factory
        self._terminate_timeout = terminate_timeout
        self._clock = clock
        self._atexit_register = atexit_register
        self._lock = threading.RLock()
        self._processes: dict[int, _ProcessRecord] = {}
        self._atexit_registered = False

    def start(self, command: Sequence[str] | str, **popen_kwargs) -> Any:
        process = self._popen_factory(command, **popen_kwargs)
        self.register(process, command)
        return process

    def register(self, process: Any, command: Sequence[str] | str | None = None) -> Any:
        pid = self._pid(process)
        normalized_command = tuple(command) if isinstance(command, list | tuple) else command
        with self._lock:
            self._processes[pid] = _ProcessRecord(
                process=process,
                command=normalized_command,
                started_at=self._clock(),
            )
        return process

    def unregister(self, process_or_pid: Any) -> bool:
        pid = self._pid(process_or_pid)
        with self._lock:
            return self._processes.pop(pid, None) is not None

    def cleanup_finished(self) -> list[int]:
        with self._lock:
            finished = [
                pid
                for pid, record in self._processes.items()
                if record.process.poll() is not None
            ]
            for pid in finished:
                self._processes.pop(pid, None)
        return finished

    def terminate(self, process_or_pid: Any, timeout: float | None = None) -> bool:
        record = self._record(process_or_pid)
        if not record:
            return False

        process = record.process
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=self._timeout(timeout))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=self._timeout(timeout))
        self.unregister(process)
        return True

    def cleanup_all(self, timeout: float | None = None) -> list[int]:
        with self._lock:
            pids = list(self._processes)
        for pid in pids:
            self.terminate(pid, timeout=timeout)
        return pids

    def snapshot(self) -> list[ProcessSnapshot]:
        with self._lock:
            return [
                ProcessSnapshot(
                    pid=pid,
                    command=record.command,
                    running=record.process.poll() is None,
                    started_at=record.started_at,
                )
                for pid, record in self._processes.items()
            ]

    def register_atexit(self):
        with self._lock:
            if self._atexit_registered:
                return
            self._atexit_register(self.cleanup_all)
            self._atexit_registered = True

    def _record(self, process_or_pid: Any) -> _ProcessRecord | None:
        pid = self._pid(process_or_pid)
        with self._lock:
            return self._processes.get(pid)

    def _pid(self, process_or_pid: Any) -> int:
        if isinstance(process_or_pid, int):
            return process_or_pid
        return int(process_or_pid.pid)

    def _timeout(self, timeout: float | None) -> float:
        return self._terminate_timeout if timeout is None else timeout
