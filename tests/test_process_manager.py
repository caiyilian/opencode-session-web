import subprocess

from services.process_manager import ProcessManager


class FakeProcess:
    _next_pid = 1000

    def __init__(self, command, *, wait_timeout_once=False, returncode=None):
        self.command = command
        self.pid = FakeProcess._next_pid
        FakeProcess._next_pid += 1
        self.returncode = returncode
        self.wait_timeout_once = wait_timeout_once
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.wait_timeout_once and not self.killed:
            self.wait_timeout_once = False
            raise subprocess.TimeoutExpired(self.command, timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def test_start_tracks_process():
    created = []

    def popen_factory(command, **kwargs):
        created.append((command, kwargs))
        return FakeProcess(command)

    manager = ProcessManager(popen_factory=popen_factory, clock=lambda: 123.0)
    process = manager.start(["opencode", "run"], stdout=subprocess.PIPE)

    assert created == [(["opencode", "run"], {"stdout": subprocess.PIPE})]
    snapshot = manager.snapshot()
    assert snapshot[0].pid == process.pid
    assert snapshot[0].command == ("opencode", "run")
    assert snapshot[0].running is True
    assert snapshot[0].started_at == 123.0


def test_cleanup_finished_unregisters_exited_processes():
    manager = ProcessManager()
    running = manager.register(FakeProcess(["running"]))
    exited = manager.register(FakeProcess(["exited"], returncode=0))

    assert manager.cleanup_finished() == [exited.pid]
    assert [item.pid for item in manager.snapshot()] == [running.pid]


def test_terminate_kills_after_timeout():
    manager = ProcessManager(terminate_timeout=0.1)
    process = manager.register(FakeProcess(["slow"], wait_timeout_once=True))

    assert manager.terminate(process) is True
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2
    assert manager.snapshot() == []


def test_cleanup_all_terminates_every_running_process():
    manager = ProcessManager()
    first = manager.register(FakeProcess(["first"]))
    second = manager.register(FakeProcess(["second"]))

    assert manager.cleanup_all() == [first.pid, second.pid]
    assert first.terminated is True
    assert second.terminated is True
    assert manager.snapshot() == []


def test_register_atexit_is_idempotent():
    registered = []
    manager = ProcessManager(atexit_register=registered.append)

    manager.register_atexit()
    manager.register_atexit()

    assert len(registered) == 1
    assert registered[0].__self__ is manager
    assert registered[0].__func__ is ProcessManager.cleanup_all
