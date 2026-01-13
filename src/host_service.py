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
    
    Use is_success() to check if the operation succeeded, and access value or error accordingly.
    """
    value: T | None = None
    error: OperationError | None = None

    def is_success(self) -> bool:
        """Returns True if the operation succeeded."""
        return self.error is None

    def is_error(self) -> bool:
        """Returns True if the operation failed."""
        return self.error is not None

    @staticmethod
    def success(value: T) -> 'Result[T]':
        """Creates a successful result with the given value."""
        return Result(value=value, error=None)

    @staticmethod
    def failure(error: OperationError) -> 'Result[T]':
        """Creates a failed result with the given error."""
        return Result(value=None, error=error)

    def unwrap(self) -> T:
        """
        Returns the value if successful, raises ValueError if failed.
        Use this when you're certain the operation succeeded.
        """
        if self.is_error():
            raise ValueError(f"Cannot unwrap failed result: {self.error}")
        return self.value  # type: ignore

    def unwrap_or(self, default: T) -> T:
        """Returns the value if successful, or the default value if failed."""
        if self.is_error():
            return default
        return self.value  # type: ignore


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
    def create(self, name: str, command: str) -> Result[None]:
        """
        Creates a new screen session.
        
        Returns:
            Result with None on success, or error on failure.
        """
        ...

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
            return False
        return name in result.value  # type: ignore
    
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
        
        if result.returncode not in (0, 1):  # screen returns 1 when no sessions exist
            return Result.failure(OperationError(
                error_type=OperationErrorType.COMMAND_FAILED,
                message="Failed to list screen sessions",
                return_code=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout
            ))

        if len(lines) < 2:
            # No sessions or unexpected output format
            return Result.success([])
        
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
        
        return Result.success(session_names)


    def create(self, name: str, command: str) -> Result[None]:
        name = self._normalize_name(name)
        args = ["screen", "-dmS", name, "bash", "-c", command]

        result = run(args)
        if result.returncode != 0:
            return Result.failure(OperationError(
                error_type=OperationErrorType.COMMAND_FAILED,
                message=f"Failed to create screen session '{name}'",
                return_code=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout
            ))
        return Result.success(None)


    def stuff(self, name: str, command: str) -> Result[None]:
        name = self._normalize_name(name)
        result = run(["screen", "-S", name, "-X", "stuff", f"{command}\n"])
        if result.returncode != 0:
            return Result.failure(OperationError(
                error_type=OperationErrorType.COMMAND_FAILED,
                message=f"Failed to send command to screen session '{name}'",
                return_code=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout
            ))
        return Result.success(None)


    def wait_term(self, name: str, poll_interval: float = 0.5, timeout: float | None = None) -> Result[None]:
        name = self._normalize_name(name)
        start = time.monotonic()
        while True:
            if not self.exists(name):
                return Result.success(None)
            if timeout is not None and time.monotonic() - start > timeout:
                return Result.failure(OperationError(
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
        """
        Checks if a server is currently running.
        
        Returns:
            True if the server is running, False otherwise.
        """
        ...
    
    @abstractmethod
    def start_server(self, name: str, workdir: str, entrypoint: str) -> Result[None]:
        """
        Starts a server.
        
        Returns:
            Result with None on success, or error on failure.
        """
        ...
    
    @abstractmethod
    def stop_server(self, name: str) -> Result[None]:
        """
        Stops a server.
        
        Returns:
            Result with None on success, or error on failure.
        """
        ...

    @abstractmethod
    def list_running(self) -> Result[list['HostDescriptor']]:
        """
        Lists all running servers.
        
        Returns:
            Result containing list of HostDescriptor on success, or error on failure.
        """
        ...
    
    @abstractmethod
    def run_in_server(self, name: str, command: str) -> Result[None]:
        """
        Executes a command in a running server.
        
        Returns:
            Result with None on success, or error on failure.
        """
        ...


class ScreenPlatformService(PlatformHostService):
    __prefix: str
    __screen: ScreenService

    # TODO: When searching/listing screens sessions, make sure to only
    # accept candidates with the local prefix

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
        return Result.success(local_sessions)
    

    def is_server_running(self, name: str) -> bool:
        local_name = self.__to_local_name(name)
        return self.__screen.exists(local_name)


    def start_server(self, name: str, workdir: str, entrypoint: str) -> Result[None]:
        local_name = self.__to_local_name(name)
        cmd = f"cd {workdir} && {entrypoint}"  # In the wrong layer, this should not know about linux vs other OS
        return self.__screen.create(local_name, cmd)
    
    
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
        if sessions_result.is_error():
            return Result.failure(sessions_result.error)  # type: ignore
        
        descriptors = [
            HostDescriptor(
                self.__strip_local_name(self.__screen.trim_id(session)),
                f"screen@{session}"
            ) for session in sessions_result.value  # type: ignore
        ]
        return Result.success(descriptors)
    

    def run_in_server(self, name: str, command: str) -> Result[None]:
        local_name = self.__to_local_name(name)
        return self.__screen.stuff(local_name, command)


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
