import tarfile
import typer
from typing import Annotated, Any, Iterator
from config.profile import Profile, ProfileRepository, FileProfileRepository
from utils import generate_unique_path, sanitize_filename
from pathlib import Path
from datetime import datetime
from click import ParamType
from rich.progress import track, Progress, SpinnerColumn, TextColumn


repo: ProfileRepository = FileProfileRepository("./tmp/configs")
app = typer.Typer()


def typer_load_profile(name: str) -> Profile:
    try:
        return repo.load(name)
    except Exception:
        typer.echo(f"The server profile '{name}' does not exist")
        raise typer.Abort()
    
    
class ProfileParser(ParamType):
    name = "Profile"

    def convert(self, value: str, param: Any, ctx: Any):
        return typer_load_profile(value)


@app.command()
def backup(
    profile: Annotated[Profile, typer.Argument(help="The name of the profile.", click_type=ProfileParser())],
    progress: Annotated[bool, typer.Option(help="Show backup progress.")] = False,
    world: Annotated[bool, typer.Option(help="Only backup the server world.")] = False
):
    """
    Create a server backup based on the provided configuration.
    """

    backup_dir = Path(profile.backup_location)
    dir_to_backup = Path(profile.server_location)
    if world:
        dir_to_backup = dir_to_backup.joinpath("./world")

    if not dir_to_backup.exists():
        typer.echo(f"Cannot create backup, the directory '{dir_to_backup}' does not exist.")
        raise typer.Abort()
    
    if not backup_dir.exists():
        try:
            backup_dir.mkdir(parents=True)
            typer.echo(f"Created new backup directory at '{backup_dir}'")
        except Exception:
            typer.echo(f"Cannot create backup, the backup directory '{backup_dir}' cannot be accessed or created")
            raise

    backup_file = generate_unique_path(
        backup_dir,
        lambda: generate_backup_name(profile.name, world),
        "tar.gz"
    )

    create_backup(dir_to_backup, backup_file, progress)

    print(f"Successfully backed up '{profile.name}' to {backup_file}")


def generate_backup_name(name: str, isWorldOnly: bool) -> str:
    name = sanitize_filename(name)
    now = datetime.today()
    timestamp = now.strftime('%Y-%m-%d')
    flag = "[world]" if isWorldOnly else "[server]"
    return f"{name} {timestamp} {flag}"


def iter_files(path: Path) -> Iterator[Path]:
    if path.is_file():
        yield path
    elif path.is_dir():
        for p in path.rglob("*"):
            if p.is_file():
                yield p
    else:
        raise ValueError(f"{path} is not a file or directory")


def create_tar(root: Path, output: Path) -> Iterator[Path]:
    iterator = iter_files(root)
    with tarfile.open(output, "w:gz") as tar:
        if root.is_dir():
            root_name = root.name
            for file in iterator:
                name = str(root_name / file.relative_to(root))
                tar.add(file, arcname=name)
                yield file
        else:
            for file in iterator:
                tar.add(file, arcname=file.name)
                yield file

            
def create_backup(
    dir: Path,
    output: Path,
    show_progress: bool = False,
):
    if not show_progress:
        for _ in create_tar(dir, output):
            pass
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as spinner:
            spinner.add_task(description="Indexing...")
            files = [*iter_files(dir)]

        for _ in track(
            create_tar(dir, output),
            total=len(files),
            description="Archiving..."
        ):
            pass