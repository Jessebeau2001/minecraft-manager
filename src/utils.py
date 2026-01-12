from pathlib import Path
import re
from typing import Callable


def sanitize_filename(name: str) -> str:
    illegals = r'[<>:"/\\|?*\s]+'
    name = name.lower().strip(" ")     # lowercase & trim whitespace 
    name = re.sub(illegals, "_", name) # collapse illegals chars into one underscore
    return name


def sanitize_extension(extension: str | None) -> str:
    if extension == None:
        return ""

    extension = extension.strip()
    if len(extension) == 0:
        return ""
    
    if extension.startswith("."):
        return extension
    else:
        return extension[1:]
    

def generate_unique_path(root: Path, name_generator: Callable[[], str], extension: str) -> Path:
    base_name = name_generator()
    extension = sanitize_extension(extension)

    path = root.joinpath(f"{base_name}.{extension}")
    index = 1
    while path.exists():
        path = root.joinpath(f"{base_name}-{index}.{extension}")
        index += 1
    return path