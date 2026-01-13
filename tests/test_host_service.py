"""Tests for host_service error handling."""

import pytest
from unittest.mock import Mock, patch
from subprocess import CompletedProcess

from host_service import (
    OperationError,
    OperationErrorType,
    Result,
    LinuxScreenService,
    ScreenPlatformService,
)


class TestResult:
    """Test the Result type."""

    def test_success_result(self):
        result = Result.success("test_value")
        assert result.is_success()
        assert not result.is_error()
        assert result.value == "test_value"
        assert result.error is None

    def test_failure_result(self):
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Test error",
            return_code=1
        )
        result = Result.failure(error)
        assert result.is_error()
        assert not result.is_success()
        assert result.value is None
        assert result.error == error

    def test_unwrap_success(self):
        result = Result.success(42)
        assert result.unwrap() == 42

    def test_unwrap_failure(self):
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Test error"
        )
        result = Result.failure(error)
        with pytest.raises(ValueError, match="Cannot unwrap failed result"):
            result.unwrap()

    def test_unwrap_or_success(self):
        result = Result.success(42)
        assert result.unwrap_or(0) == 42

    def test_unwrap_or_failure(self):
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Test error"
        )
        result = Result.failure(error)
        assert result.unwrap_or(0) == 0


class TestOperationError:
    """Test the OperationError class."""

    def test_error_str_minimal(self):
        error = OperationError(
            error_type=OperationErrorType.TIMEOUT,
            message="Operation timed out"
        )
        assert "timeout: Operation timed out" in str(error)

    def test_error_str_with_return_code(self):
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Command failed",
            return_code=127
        )
        error_str = str(error)
        assert "command_failed: Command failed" in error_str
        assert "(exit code: 127)" in error_str

    def test_error_str_with_stderr(self):
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Command failed",
            stderr="Error message"
        )
        error_str = str(error)
        assert "stderr: Error message" in error_str


class TestLinuxScreenService:
    """Test LinuxScreenService error handling."""

    @patch('host_service.run')
    def test_list_success(self, mock_run):
        """Test successful list operation."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-ls"],
            returncode=0,
            stdout="There are screens on:\n\t12345.test-session\t(Detached)\n1 Socket in /run/screen/S-user.\n",
            stderr=""
        )
        
        service = LinuxScreenService()
        result = service.list()
        
        assert result.is_success()
        assert "12345.test-session" in result.value

    @patch('host_service.run')
    def test_list_no_sessions(self, mock_run):
        """Test list when no sessions exist."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-ls"],
            returncode=1,
            stdout="No Sockets found in /run/screen/S-user.\n",
            stderr=""
        )
        
        service = LinuxScreenService()
        result = service.list()
        
        assert result.is_success()
        assert result.value == []

    @patch('host_service.run')
    def test_list_command_failure(self, mock_run):
        """Test list when command fails."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-ls"],
            returncode=2,
            stdout="",
            stderr="screen: command not found"
        )
        
        service = LinuxScreenService()
        result = service.list()
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED
        assert result.error.return_code == 2

    @patch('host_service.run')
    def test_create_success(self, mock_run):
        """Test successful screen creation."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-dmS", "test", "bash", "-c", "echo test"],
            returncode=0,
            stdout="",
            stderr=""
        )
        
        service = LinuxScreenService()
        result = service.create("test", "echo test")
        
        assert result.is_success()
        assert result.value is None

    @patch('host_service.run')
    def test_create_failure(self, mock_run):
        """Test screen creation failure."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-dmS", "test", "bash", "-c", "echo test"],
            returncode=1,
            stdout="",
            stderr="screen: failed to create session"
        )
        
        service = LinuxScreenService()
        result = service.create("test", "echo test")
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED
        assert "Failed to create screen session" in result.error.message

    @patch('host_service.run')
    def test_stuff_success(self, mock_run):
        """Test successful stuff command."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-S", "test", "-X", "stuff", "stop\n"],
            returncode=0,
            stdout="",
            stderr=""
        )
        
        service = LinuxScreenService()
        result = service.stuff("test", "stop")
        
        assert result.is_success()

    @patch('host_service.run')
    def test_stuff_failure(self, mock_run):
        """Test stuff command failure."""
        mock_run.return_value = CompletedProcess(
            args=["screen", "-S", "test", "-X", "stuff", "stop\n"],
            returncode=1,
            stdout="",
            stderr="No screen session found."
        )
        
        service = LinuxScreenService()
        result = service.stuff("test", "stop")
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED
        assert "Failed to send command" in result.error.message

    def test_wait_term_timeout(self):
        """Test wait_term timeout."""
        service = LinuxScreenService()
        
        # Mock exists to always return True (session never terminates)
        with patch.object(service, 'exists', return_value=True):
            result = service.wait_term("test", poll_interval=0.1, timeout=0.2)
            
            assert result.is_error()
            assert result.error.error_type == OperationErrorType.TIMEOUT
            assert "Timeout waiting" in result.error.message

    def test_wait_term_success(self):
        """Test wait_term success when session terminates."""
        service = LinuxScreenService()
        
        # Mock exists to return False (session terminated)
        with patch.object(service, 'exists', return_value=False):
            result = service.wait_term("test", poll_interval=0.1, timeout=1.0)
            
            assert result.is_success()


class TestScreenPlatformService:
    """Test ScreenPlatformService error handling."""

    def test_start_server_success(self):
        """Test successful server start."""
        mock_screen = Mock()
        mock_screen.create.return_value = Result.success(None)
        
        service = ScreenPlatformService(mock_screen)
        result = service.start_server("test", "/path/to/server", "java -jar server.jar")
        
        assert result.is_success()
        mock_screen.create.assert_called_once()

    def test_start_server_failure(self):
        """Test server start failure."""
        mock_screen = Mock()
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Failed to create session"
        )
        mock_screen.create.return_value = Result.failure(error)
        
        service = ScreenPlatformService(mock_screen)
        result = service.start_server("test", "/path/to/server", "java -jar server.jar")
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED

    def test_stop_server_success(self):
        """Test successful server stop."""
        mock_screen = Mock()
        mock_screen.stuff.return_value = Result.success(None)
        mock_screen.wait_term.return_value = Result.success(None)
        
        service = ScreenPlatformService(mock_screen)
        result = service.stop_server("test")
        
        assert result.is_success()
        mock_screen.stuff.assert_called_once()
        mock_screen.wait_term.assert_called_once()

    def test_stop_server_stuff_failure(self):
        """Test server stop when stuff fails."""
        mock_screen = Mock()
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Failed to send stop command"
        )
        mock_screen.stuff.return_value = Result.failure(error)
        
        service = ScreenPlatformService(mock_screen)
        result = service.stop_server("test")
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED
        # Should not call wait_term if stuff fails
        mock_screen.wait_term.assert_not_called()

    def test_stop_server_timeout(self):
        """Test server stop timeout."""
        mock_screen = Mock()
        mock_screen.stuff.return_value = Result.success(None)
        timeout_error = OperationError(
            error_type=OperationErrorType.TIMEOUT,
            message="Timeout waiting for termination"
        )
        mock_screen.wait_term.return_value = Result.failure(timeout_error)
        
        service = ScreenPlatformService(mock_screen)
        result = service.stop_server("test")
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.TIMEOUT

    def test_list_running_success(self):
        """Test successful list running."""
        mock_screen = Mock()
        mock_screen.list.return_value = Result.success(["12345.mcm-server1", "12346.mcm-server2"])
        mock_screen.trim_id.side_effect = lambda x: x.split(".")[1] if "." in x else x
        
        service = ScreenPlatformService(mock_screen)
        result = service.list_running()
        
        assert result.is_success()
        assert len(result.value) == 2
        assert result.value[0].name == "server1"
        assert result.value[1].name == "server2"

    def test_list_running_failure(self):
        """Test list running failure."""
        mock_screen = Mock()
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Failed to list sessions"
        )
        mock_screen.list.return_value = Result.failure(error)
        
        service = ScreenPlatformService(mock_screen)
        result = service.list_running()
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED

    def test_run_in_server_success(self):
        """Test successful run_in_server."""
        mock_screen = Mock()
        mock_screen.stuff.return_value = Result.success(None)
        
        service = ScreenPlatformService(mock_screen)
        result = service.run_in_server("test", "say Hello")
        
        assert result.is_success()
        mock_screen.stuff.assert_called_once()

    def test_run_in_server_failure(self):
        """Test run_in_server failure."""
        mock_screen = Mock()
        error = OperationError(
            error_type=OperationErrorType.COMMAND_FAILED,
            message="Failed to send command"
        )
        mock_screen.stuff.return_value = Result.failure(error)
        
        service = ScreenPlatformService(mock_screen)
        result = service.run_in_server("test", "say Hello")
        
        assert result.is_error()
        assert result.error.error_type == OperationErrorType.COMMAND_FAILED
