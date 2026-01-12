from typing import Annotated
import typer

import cli.server

app = typer.Typer()
app.add_typer(cli.server.app, name="server")


# @app.command()
def hello(name: str):
    print(f"Hello {name}")


# @app.command()
def goodbye(name: str, formal: bool = False):
    """
    Say goodbye to a certain person
    """
    if formal:
        print(f"Goodbye Ms. {name}. Have a good day.")
    else:
        print(f"Bye {name}!")


# @app.command()
def greet(
    name: Annotated[str, typer.Argument(help="The name of the person to greet")],
    greeter: Annotated[str | None, typer.Option(help="The person who greets")] = None,
    formal: Annotated[bool, typer.Option()] = False,
):
    """
    Greet someone
    """
    if formal:
        if greeter != None:
            print(f"{greeter} asks how you are doing {name}?")
        else:
            print(f"How are you doing {name}?")
    else:
        if greeter != None:
            print(f"{greeter} says hey {name}")
        else:
            print(f"Hey {name}")

if __name__ == "__main__":
    app()

# mcm servers list
# mcm servers create (interactive)
# mcm servers backup (--world)
#
#
#
#
#
