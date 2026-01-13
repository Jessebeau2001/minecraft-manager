from profiles import Profile, ProfileNotFoundError
import yaml
import typer
from pathlib import Path
from typing import Annotated, Any, Final
from cli.config import get_app_dir, profile_repository, console
from click import ParamType
from rich.table import Table
from rich.text import Text
from utils import fallback, random_craft_name, resolve_value


app = typer.Typer()


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
        return profile_repository.load(name)
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

    if profile_repository.exists(name):
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


def generate_unique_random_name() -> str:
    generated = random_craft_name()
    while profile_repository.exists(generated):
        generated = random_craft_name()
    return generated


def make_unique(basename: str) -> str:
    generated = basename
    suffix = 1
    while profile_repository.exists(generated):
        generated = f"{basename}-{suffix}"
        suffix += 1
    return generated


DEFAULT_ENTRYPOINT: Final[str] = "java -jar server.jar nogui"

@app.command()
def create(
    name: Annotated[str | None, typer.Option(help="The name of the profile.")] = None,
    server_dir: Annotated[str | None, typer.Option(help="The location of the server.")] = None,
    backup_dir: Annotated[str | None, typer.Option(help="The location to store server backups in.")] = None,
    mc_version: Annotated[str | None, typer.Option(help="The version of minecraft e.g. 1.20.4-fabric")] = None,

    template: Annotated[str | None, typer.Option(help="Create a profile by using another profile as template.")] = None,
    defaults: Annotated[bool, typer.Option("--defaults", help="Use the default values for omitted profile configurations.")] = False
):
    """
    Create a new profile explicitly, interactively or via template.
    """

    if defaults and template:
        raise typer.BadParameter("Cannot use defaults with templates")

    template_profile = None

    if defaults:
        generated_name = generate_unique_random_name()
        app_dir = get_app_dir()
        template_profile = Profile(
            name            = generated_name,
            server_location = app_dir.joinpath(f"servers/{generated_name}"),
            backup_location      = app_dir.joinpath(f"backups/{generated_name}"),
            server_version      = "minecraft",
            entrypoint      = DEFAULT_ENTRYPOINT
        )
    elif template:
        try:
            template_profile = profile_repository.load(template)
            template_profile.name = make_unique(template_profile.name)
        except ProfileNotFoundError:
            raise typer.BadParameter(f"Profile template {template} does not exist")
    
    if template_profile == None:
        # Query-validate all
        new_profile = Profile(
            name            = prompt_unique_name(name),
            server_location = prompt_dir("server directory", server_dir),
            backup_location      = prompt_dir("backup directory", backup_dir),
            server_version      = prompt_str("Minecraft version", mc_version),
            entrypoint      = DEFAULT_ENTRYPOINT
        )
    else:
        # Query-validate what is given
        new_profile = Profile(
            name            = resolve_value(template_profile.name, name, lambda value: prompt_str("name", value)),
            server_location = resolve_value(template_profile.server_location, server_dir, lambda value: prompt_dir("server directory", value)),
            backup_location      = resolve_value(template_profile.backup_location, backup_dir, lambda value: prompt_dir("backup directory", value)),
            server_version      = fallback(template_profile.server_version, mc_version),
            entrypoint      = template_profile.entrypoint
        )


    console.print("Creating the following profile:")
    console.print(profile_to_table(new_profile))

    confirm = typer.confirm("Is this OK?")
    if not confirm:
        raise typer.Abort()

    location = profile_repository.save(new_profile.name, new_profile)
    typer.echo(f"Saved new profile to {location}!")


@app.command()
def list(
    verbose: Annotated[bool, typer.Option(help="Show the full properties of each profile.")] = False,
):
    """
    List all the profiles.
    """

    list = profile_repository.list()
    typer.echo(f"Listing {len(list)} profiles:")

    if not verbose:
        for info in list:
            if info.profile != None:
                typer.echo(f"* {info.profile.name} [{info.location}]")
            else:
                console.print(Text(f"* INVALID [{info.location}]", style="red"))
    else:
        for info in list:
            if info.profile != None:
                table = profile_to_table(info.profile)
                typer.echo(f"* {info.profile.name} [{info.location}]")
                console.print(table)
            else:
                console.print(Text(f"* INVALID [{info.location}]", style="red"))