from pathlib import Path
from typing import Annotated, Any
from config.profile import FileProfileRepository, Profile, ProfileRepository

import yaml
import typer
from click import ParamType
from rich.console import Console
from rich.table import Table


profileRepository: ProfileRepository = FileProfileRepository("./tmp/configs") # TODO: Move to central file
app = typer.Typer()
console = Console()


def profile_to_string(profile: Profile) -> str:
    # Just serialize as yaml, this is fine for printing
    return yaml.safe_dump(profile.as_dict(), sort_keys=False)


def profile_to_table(profile: Profile) -> Table:
    table = Table(show_header=False)
    for key, value in profile.as_dict().items():
        table.add_row(key, str(value))
    return table



def typer_load_profile(name: str) -> Profile:
    try:
        return profileRepository.load(name)
    except Exception:
        typer.echo(f"The server profile '{name}' does not exist")
        raise typer.Abort()
    
    
class ClickProfileParser(ParamType):
    name = "Profile"

    def convert(self, value: str, param: Any, ctx: Any):
        return typer_load_profile(value)
    

def prompt_unique_name(name: str | None) -> str:
    if name == None:
        name = str(typer.prompt("Profile name"))

    if profileRepository.exists(name):
        overwrite = typer.confirm(f"Profile with name {name} already exists, overwrite?")
        if not overwrite:
            raise typer.BadParameter(f"Profile with name '{name}' already exists.")
        
    return name


def prompt_dir(name: str, value: str | None) -> Path:
    path: Path | None = None
    while path is None:
        if value is None or not value.strip():
            value = str(typer.prompt(f"Please enter the {name}"))

        try:
            path = Path(value).expanduser()
            try:
                path = path.resolve()
            except FileNotFoundError:
                path = path.absolute()
        except Exception as e:
            typer.echo(f"Invalid path: {e}")
            value = None
            path = None
            continue

        if not path.exists():
            if not typer.confirm(f"The directory {path} does not exist. Use anyway?"):
                value = None
                path = None
    return path


def prompt_str(name: str, value: str | None) -> str:
    if value == None:
        return str(typer.prompt(f"Enter the {name}"))
    return value

    
@app.command()
def create(
    name: Annotated[str | None, typer.Option(help="The name of the profile")] = None,
    server_dir: Annotated[str | None, typer.Option(help="The location of the server")] = None,
    mc_version: Annotated[str | None, typer.Option(help="The version of minecraft e.g. [1.20.4/fabric]")] = None,
    backup_dir: Annotated[str | None, typer.Option(help="The location to store server backups in")] = None,
):
    """
    Create a new profile explicitly or interactively.
    """

    # I dislike Typers implicit prompt system for this. Doing it manually gives us way more control
    name = prompt_unique_name(name)
    server_path = prompt_dir("server directory", server_dir)
    version = prompt_str("Minecraft version", mc_version)
    backup_path = prompt_dir("backup directory", backup_dir)

    new_profile = Profile(
        name,
        str(server_path),
        version,
        str(backup_path),
        "java -jar server.jar"
    )

    console.print("Creating the following profile:")
    console.print(profile_to_table(new_profile))

    confirm = typer.confirm("Is this OK?")
    if not confirm:
        raise typer.Abort()

    location = profileRepository.save(new_profile.name, new_profile)
    typer.echo(f"Saved new profile to {location}!")


@app.command()
def list(
    verbose: Annotated[bool, typer.Option(help="Show the full properties of each profile.")] = False,
):
    """
    List all the profiles.
    """

    list = profileRepository.list()
    typer.echo(f"Listing {len(list)} profiles:")

    if not verbose:
        for info in list:
            typer.echo(f"* {info.profile.name} [{info.location}]")
    else:
        for info in list:
            table = profile_to_table(info.profile)
            typer.echo(f"* {info.profile.name} [{info.location}]")
            console.print(table)
            