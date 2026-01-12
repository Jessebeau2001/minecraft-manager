from datetime import datetime
import re
import tarfile
from typing import Annotated, Any, Callable, Iterator
from rich.progress import track, Progress, SpinnerColumn, TextColumn
import typer

from config.config import Config, ConfigRepository, FileConfigRepo
from pathlib import Path


configs: ConfigRepository = FileConfigRepo("./tmp/configs")
app = typer.Typer()

def print_list_value(key: str, value: Any):
    print(f"    - {key}: {value}")

def print_list_item(key: str, value: Any):
     print(f"- {key}: {value}")

def print_config(config: Config):
    print_list_item("name", config.name)
    print_list_item("location", config.server_location)
    print_list_item("version", config.server_version)


@app.command()
def create(
    name: Annotated[str, typer.Option(help="The name of the profile", prompt=True)],
    location: Annotated[str, typer.Option(help="The location of the server", prompt=True)] ,
    version: Annotated[str, typer.Option(help="The version of minecraft e.g. [1.20.4/fabric]", prompt=True)],
    backup_location: Annotated[str, typer.Option(help="The location to store server backups in", prompt=True)],
):
    # Can we eager this?
    if configs.exists(name):
        overwrite = typer.confirm(f"Profile with name {name} already exists, overwrite?")
        if not overwrite:
            raise typer.Abort()

    config = Config(name, location, version, backup_location)
    print_config(config)

    confirm = typer.confirm("Is the profile ok?")
    if not confirm:
        raise typer.Abort()

    configs.save(config.name, config)
    print(f"Saved new profile {config.name}!")


@app.command()
def delete(item: str):
    print(f"Selling item: {item}")

@app.command()
def list(
    verbose: Annotated[bool, typer.Option(help="List the full server specification.")] = False,
):
    """List all server configs."""

    list = configs.list()
    print(f"Found {len(list)} server configs:")

    if not verbose:
        for info in list:
            print(f"* {info.config.name} [{info.location}]")
    else:
        for info in list:
            cfg = info.config
            print(f"* ({cfg.name})/[{info.location}]:")
            print_list_value("version", cfg.server_version)
            print_list_value("location", cfg.server_location)


@app.command()
def backup(
    name: Annotated[str, typer.Argument(help="The config name.")],
    progress: Annotated[bool, typer.Option(help="Show backup progress")] = False,
    world: Annotated[bool, typer.Option(help="Only backup the servers world.")] = False
):
    """Create a server backup based to the provided config."""

    config: Config # todo: this can be a typer task perhaps
    try:
        config = configs.load(name)
    except Exception:
        typer.echo(f"The server profile '{name}' does not exist")
        raise typer.Abort()

    backup_dir = Path(config.backup_location)
    dir_to_backup = Path(config.server_location)
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
        lambda: generate_backup_name(config.name, world),
        "tar.gz"
    )

    create_backup(dir_to_backup, backup_file, progress)

    print(f"Successfully backed up '{config.name}' to {backup_file}")


def sanitize_name(name: str) -> str:
    illegals = r'[<>:"/\\|?*\s]+'
    name = name.lower().strip(" ")     # lowercase & trim whitespace 
    name = re.sub(illegals, "_", name) # collapse illegals chars into one underscore
    return name


def sanitize_extension(extension: str) -> str:
    return extension if not extension.startswith(".") else extension[1:]


def generate_backup_name(name: str, isWorldOnly: bool) -> str:
    name = sanitize_name(name)
    now = datetime.today()
    timestamp = now.strftime('%Y-%m-%d')
    flag = "[world]" if isWorldOnly else "[server]"
    return f"{name} {timestamp} {flag}"


def generate_unique_path(root: Path, name_generator: Callable[[], str], extension: str) -> Path:
    base_name = name_generator()
    extension = sanitize_extension(extension)

    path = root.joinpath(f"{base_name}.{extension}")
    index = 1
    while path.exists():
        path = root.joinpath(f"{base_name}-{index}.{extension}")
        index += 1
    return path



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