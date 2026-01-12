import re


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