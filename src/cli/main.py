from typing import Annotated
import typer

import cli.server
import cli.profile

app = typer.Typer()
app.add_typer(cli.profile.app, name="profile")
app.add_typer(cli.server.app, name="server")


__version__ = "0.0.1"


def version_callback(value: bool):
    if value:
        typer.echo(f"Minecraft CLI Manager version {__version__}")
        raise typer.Exit()


@app.callback()
def version(
    version: Annotated[bool, typer.Option("--version", callback=version_callback, help="Show the current app version.")] = False
):
    pass


if __name__ == "__main__":
    app()
