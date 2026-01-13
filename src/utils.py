from pathlib import Path
import random
import re
from typing import Callable, TypeVar


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
        return extension[1:]
    else:
        return extension
    

def generate_unique_path(root: Path, name_generator: Callable[[], str], extension: str) -> Path:
    base_name = name_generator()
    extension = sanitize_extension(extension)

    path = root.joinpath(f"{base_name}.{extension}")
    index = 1
    while path.exists():
        path = root.joinpath(f"{base_name}-{index}.{extension}")
        index += 1
    return path


def random_craft_name(separator: str = "-") -> str:
    prefixes= [ "white", "orange", "magenta", "blue", "yellow", "red", "lime", "green", "black", "gray", "pink", "cyan", "purple", "brown", "small", "large" ]
    names = [ "stone", "granite", "andesite", "diorite", "dirt", "podzol", "cobble", "spruce", "oak", "birch" ]
    suffixes = [ "sapling", "planks", "log", "wood", "sand", "leaves", "block", "stairs", "chest", "barrel" ]
    
    prefix = random.choice(prefixes)
    name = random.choice(names)
    suffix = random.choice(suffixes)

    return f"{prefix}{separator}{name}{separator}{suffix}"


T = TypeVar('T')
E = TypeVar('E')

def fallback(base: T, optional: T | None) -> T:
    return base if optional is None else optional

def if_present(optional: T | None, func: Callable[[T], E]) -> E | None:
    return func(optional) if not optional is None else None

def resolve_value(base: E, optional: T | None, resolver: Callable[[T], E]) -> E:
    return fallback(base, if_present(optional, lambda value: resolver(value)))