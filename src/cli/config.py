from pathlib import Path
from profiles import FileProfileRepository, ProfileRepository
from rich.console import Console
from host_service import create_os_host_service


def create_user_profile_repo() -> ProfileRepository:
    path = Path("~/minecraft-manager/profiles")
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return FileProfileRepository(path)



__version__ = "0.0.1"
profile_repository = create_user_profile_repo()
server_service = create_os_host_service()
console = Console()