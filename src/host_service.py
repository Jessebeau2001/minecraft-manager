from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar
import platform
import shutil
import time
import subprocess
from subprocess import CompletedProcess
from abc import ABC, abstractmethod
from utils import sanitize_filename


def run(cmd: list[str]) -> CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


class OperationErrorType(Enum):
    """Types of errors that can occur in host service operations."""
    COMMAND_FAILED = "command_failed"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    INVALID_STATE = "invalid_state"
    UNKNOWN = "unknown"


@dataclass
class OperationError:
    """Represents an error that occurred during a host service operation."""
    error_type: OperationErrorType
    message: str
    return_code: int | None = None
    stderr: str | None = None
    stdout: str | None = None

    def __str__(self) -> str:
        parts = [f"{self.error_type.value}: {self.message}"]
        if self.return_code is not None:
            parts.append(f"(exit code: {self.return_code})")
        if self.stderr:
            parts.append(f"stderr: {self.stderr}")
        return " ".join(parts)


T = TypeVar('T')


@dataclass
class Result(Generic[T]):
    """
    Represents the result of an operation that can either succeed or fail.
    """
    value: T | None = None
    error: OperationError | None = None

    def is_success(self) -> bool:
        """Returns True if the operation succeeded."""
        return self.error is None

    def is_error(self) -> bool:
        """Returns True if the operation failed."""
        return self.error is not None

    def unwrap(self) -> T:
        """Returns the value if successful, raises ValueError if failed."""
        if self.is_error() or self.value is None:
            raise ValueError(f"Cannot unwrap failed result: {self.error}")
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Returns the value if successful, or the default value if failed."""
        if self.is_error() or self.value is None:
            return default
        return self.value


def new_success(value: T) -> Result[T]:
    """Creates a successful result with the given value."""
    return Result(value=value, error=None)

def empty_success() -> Result[None]:
    return Result(value=None, error=None)

def new_failure(error: OperationError) -> Result[T]: # type: ignore
    """Creates a failed result with the given error."""
    return Result(value=None, error=error)


class ScreenService(ABC):
    @abstractmethod
    def list(self, trim_id: bool = False) -> Result[list[str]]:
        """
        Lists all screen sessions.
        
        Returns:
            Result containing list of session names on success, or error on failure.
        """
        ...

    @abstractmethod
    def create(self, name: str, command: str, workdir: str | None = None) -> Result[None]:
        """
        Creates a new screen session.
        
        Returns:
            Result with None on success, or error on failure.
        """

    @abstractmethod
    def stuff(self, name: str, command: str) -> Result[None]:
        """
        Sends a command to a screen session.
        
        Returns:
            Result with None on success, or error on failure.
        """
        ...

    @abstractmethod
    def wait_term(self, name: str, poll_interval: float = 0.5, timeout: float | None = None) -> Result[None]:
        """
        Waits for a screen session to terminate.
        
        Returns:
            Result with None on success, or error if timeout occurs.
        """
        ...

    def exists(self, name: str) -> bool:
        """Checks if a screen session exists."""
        result = self.list(trim_id=True)
        if result.is_error():
            raise RuntimeError() # TODO: Proper handle
        return name in result.unwrap()
    
    def trim_id(self, name: str) -> str:
        """Trims the process ID from a screen session name."""
        return name.split(".")[1] if "." in name else name


class LinuxScreenService(ScreenService):
    def _normalize_name(self, name: str) -> str:
        # Just use the filename algo
        return sanitize_filename(name)
    

    def list(self, trim_id: bool = False) -> Result[list[str]]:
        result = run(["screen", "-ls"])
        lines = result.stdout.splitlines()

        if result.returncode != 0: # is a successful execution, 1 everything else
            return new_failure(OperationError(
                error_type=OperationErrorType.COMMAND_FAILED,
                message="Failed to list screen sessions",
                return_code=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout
            ))

        if len(lines) < 2:
            # No sessions or unexpected output format
            return new_success([])
        
        session_names: list[str] = []

        for line in lines[1:-1]:  # Skip header and footer
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            name = parts[0]  # "12345.name"
            if trim_id:  # "12345.name" -> "name"
                name = self.trim_id(name)
            session_names.append(name)
        
        return new_success(session_names)


    def create(self, name: str, command: str, workdir: str | None = None) -> Result[None]:
        name = self._normalize_name(name)
        if workdir != None:
            # If workdir provided cd to it first
            command = f"cd {workdir} && {command}"
        
        args = ["screen", "-dmS", name, "bash", "-c", command]

        result = run(args)
        if result.returncode != 0:
            return new_failure(OperationError(
                error_type=OperationErrorType.COMMAND_FAILED,
                message=f"Failed to create screen session '{name}'",
                return_code=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout
            ))
        return empty_success()


    def stuff(self, name: str, command: str) -> Result[None]:
        name = self._normalize_name(name)
        result = run(["screen", "-S", name, "-X", "stuff", f"{command}\n"])
        if result.returncode != 0:
            return new_failure(OperationError(
                error_type=OperationErrorType.COMMAND_FAILED,
                message=f"Failed to send command to screen session '{name}'",
                return_code=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout
            ))
        return empty_success()


    def wait_term(self, name: str, poll_interval: float = 0.5, timeout: float | None = None) -> Result[None]:
        name = self._normalize_name(name)
        start = time.monotonic()
        while True:
            if not self.exists(name):
                return new_success(None)
            if timeout is not None and time.monotonic() - start > timeout:
                return new_failure(OperationError(
                    error_type=OperationErrorType.TIMEOUT,
                    message=f"Timeout waiting for screen session '{name}' to terminate after {timeout}s"
                ))
            time.sleep(poll_interval)

    def exists(self, name: str) -> bool:
        return super().exists(self._normalize_name(name))


@dataclass
class HostDescriptor():
    name: str
    host_location: str


class PlatformHostService(ABC):
    @abstractmethod
    def is_server_running(self, name: str) -> bool:
        ...
    
    @abstractmethod
    def start_server(self, name: str, workdir: str, entrypoint: str) -> Result[None]:
        ...
    
    @abstractmethod
    def stop_server(self, name: str) -> Result[None]:
        ...

    @abstractmethod
    def list_running(self) -> Result[list[HostDescriptor]]:
        ...
    
    @abstractmethod
    def run_in_server(self, name: str, command: str) -> Result[None]:
        ...


class ScreenPlatformService(PlatformHostService):
    __prefix: str
    __screen: ScreenService

    def __init__(self, screen: ScreenService):
        self.__prefix = "mcm"
        self.__screen = screen


    def __to_local_name(self, base: str) -> str:
        return f"{self.__prefix}-{base}"
    

    def __strip_local_name(self, base: str) -> str:
        split = len(self.__prefix) + 1  # +1 for dash
        return base[split:]
    
    
    def __list_local_sessions(self) -> Result[list[str]]:
        result = self.__screen.list()
        if result.is_error():
            return result
        
        local_sessions: list[str] = []
        for session in result.value:  # type: ignore
            name = self.__screen.trim_id(session)
            if name.startswith(self.__prefix):
                local_sessions.append(session)
        return new_success(local_sessions)
    

    def is_server_running(self, name: str) -> bool:
        local_name = self.__to_local_name(name)
        return self.__screen.exists(local_name)


    def start_server(self, name: str, workdir: str, entrypoint: str) -> Result[None]:
        local_name = self.__to_local_name(name)
        return self.__screen.create(local_name, entrypoint, workdir)
    
    
    def stop_server(self, name: str) -> Result[None]:
        local_name = self.__to_local_name(name)
        
        # Send stop command
        stuff_result = self.__screen.stuff(local_name, "stop")
        if stuff_result.is_error():
            return stuff_result
        
        # Wait for termination
        return self.__screen.wait_term(local_name, 1, 10)
    
    
    def list_running(self) -> Result[list[HostDescriptor]]:
        sessions_result = self.__list_local_sessions()
        if sessions_result.error != None:
            return new_failure(sessions_result.error)
        
        descriptors = [
            HostDescriptor(
                self.__strip_local_name(self.__screen.trim_id(session)),
                f"screen@{session}"
            ) for session in sessions_result.unwrap()
        ]
        return new_success(descriptors)
    

    def run_in_server(self, name: str, command: str) -> Result[None]:
        local_name = self.__to_local_name(name)
        return self.__screen.stuff(local_name, command)


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


#            __n__n__
#     .------`-\00/-'
#    /  ##  ## (oo)
#   / \## __   ./
#      |//YY \|/
# arie |||   |||