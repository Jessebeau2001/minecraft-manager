from pathlib import Path
from profiles import FileProfileRepository, ProfileRepository
from rich.console import Console
from host_service import create_os_host_service

APP_NAME = "mc-manager"


def get_app_dir() -> Path:
    return Path(f"~/{APP_NAME}").expanduser().resolve()


def create_user_profile_repo() -> ProfileRepository:
    path = get_app_dir().joinpath("profiles")
    path.mkdir(parents=True, exist_ok=True)
    return FileProfileRepository(path)


__version__ = "0.0.1"
profile_repository = create_user_profile_repo()
server_service = create_os_host_service()
console = Console()