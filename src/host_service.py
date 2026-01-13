import platform
import shutil
import time
import subprocess
from subprocess import CompletedProcess
from abc import ABC, abstractmethod
from utils import sanitize_filename


def run(cmd: list[str]) -> CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


class ScreenService(ABC):
    @abstractmethod
    def list(self, trim_id: bool = False) -> list[str]:
        ...

    @abstractmethod
    def create(self, name: str, command: str) -> bool:
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
    def _normalize_name(self, name: str) -> str:
        # Just use the filename algo
        return sanitize_filename(name)

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


    def create(self, name: str, command: str) -> bool:
        name = self._normalize_name(name)
        args = ["screen", "-dmS", name, "bash", "-c", command]

        result = run(args) # call subprocess
        return result.returncode == 0


    def stuff(self, name: str, command: str) -> bool:
        name = self._normalize_name(name)
        result = run(["screen", "-S", name, "-X", "stuff", f"{command}\n"])
        return result.returncode == 0


    def wait_term(self, name: str, poll_interval: float = 0.5, timeout: float | None = None) -> bool:
        name = self._normalize_name(name)
        start = time.monotonic()
        while True:
            if not self.exists(name):
                return True
            if timeout is not None and time.monotonic() - start > timeout:
                return False
            time.sleep(poll_interval)

    def exists(self, name: str) -> bool:
        return super().exists(self._normalize_name(name))


class PlatformHostService(ABC):
    @abstractmethod
    def is_server_running(self, name: str) -> bool:
        ...
    
    @abstractmethod
    def start_server(self, name: str, workdir: str, entrypoint: str) -> bool:
        ...
    
    @abstractmethod
    def stop_server(self, name: str) -> bool:
        ...
    
    @abstractmethod
    def run_in_server(self, name: str, command: str):
        ...


class ScreenPlatformService(PlatformHostService):
    _prefix: str
    _screen: ScreenService

    def __init__(self, screen: ScreenService):
        self._prefix = "mcm"
        self._screen = screen


    def _local_name(self, base: str) -> str:
        return f"{self._prefix}-{base}"
    

    def is_server_running(self, name: str) -> bool:
        local_name = self._local_name(name)
        return self._screen.exists(local_name)


    def start_server(self, name: str, workdir: str, entrypoint: str) -> bool:
        local_name = self._local_name(name)
        cmd = f"cd {workdir} && {entrypoint}" # In the wrong layer, this should not know about linux vs other OS
        return self._screen.create(local_name, cmd)
    
    
    def stop_server(self, name: str) -> bool:
        local_name = self._local_name(name)
        self._screen.stuff(local_name, "stop")
        return self._screen.wait_term(local_name, 1, 10)
    

    def run_in_server(self, name: str, command: str):
        local_name = self._local_name(name)
        self._screen.stuff(local_name, command)


def run_test():
    ScreenPlatformService(LinuxScreenService())


def create_os_host_service() -> PlatformHostService:
    system = platform.system()
    match system:
        case "Linux":
            if shutil.which("screen"):
                return ScreenPlatformService(LinuxScreenService())
            else:
                raise RuntimeError("System requirements not met, please install packages: [ screen ]")
        case _:
            raise RuntimeError(f"System {system} is not supported")
