import time
import shlex
import subprocess
from subprocess import CompletedProcess
from abc import ABC, abstractmethod


def run(cmd: list[str]) -> CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


class ScreenService(ABC):
    @abstractmethod
    def list(self, trim_id: bool = False) -> list[str]:
        ...

    @abstractmethod
    def create(self, name: str, command: str | None = None) -> bool:
        ...

    @abstractmethod
    def stuff(self, name: str, command: str) -> bool:
        ...

    @abstractmethod
    def wait_term(self, name: str, poll_interval: float = 0.5, timeout: float | None = None) -> bool:
        ...

    def exists(self, name: str) -> bool:
        return name in self.list(trim_id=True)


class LinuxScreenService(ScreenService):
    def list(self, trim_id: bool = False) -> list[str]:
        result = run(["screen", "-ls"])
        lines = result.stdout.splitlines()
        
        if result.returncode != 0:
            return [] # TODO: Error?

        if len(lines) < 2:
            return [] # TODO: Do we want to error this, or maybe just log
        
        session_names: list[str] = []

        for line in lines[1:-1]: # Skip header and footer
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            name = parts[0] # "12345.name"
            if trim_id and "." in name:
                name = name.split(".")[1] # ["12345", "name"]
            session_names.append(name)
        
        return session_names


    def create(self, name: str, command: str | None = None) -> bool:
        args = ["screen", "-dmS", name]
        if command != None:
            args += shlex.split(command)
        result = run(args)
        return result.returncode == 0


    def stuff(self, name: str, command: str) -> bool:
        result = run(["screen", "-S", name, "-X", "stuff", f"{command}\n"])
        return result.returncode == 0


    def wait_term(self, name: str, poll_interval: float = 0.5, timeout: float | None = None) -> bool:
        start = time.monotonic()
        while True:
            if not self.exists(name):
                return True
            if timeout is not None and time.monotonic() - start > timeout:
                return False
            time.sleep(poll_interval)


class ScreenPlatformService():
    _prefix: str
    _screen: ScreenService

    def __init__(self, screen: ScreenService):
        self._prefix = "mcm"
        self._screen = screen


    def _local_name(self, base: str) -> str:
        return f"{self._prefix}-{base}"
    

    def is_server_running(self, name: str):
        local_name = self._local_name(name)
        return self._screen.exists(local_name)


    def start_server(self, name: str) -> bool:
        local_name = self._local_name(name)
        return self._screen.create(local_name, "sleep 10")
    
    
    def stop_server(self, name: str) -> bool:
        local_name = self._local_name(name)
        self._screen.stuff(local_name, "stop")
        return self._screen.wait_term(local_name)


def run_test():
    service = ScreenPlatformService(LinuxScreenService())

    service.start_server("my")