from abc import ABC
from pydantic import AfterValidator, BaseModel, ValidationError
import yaml
from typing import Annotated, Any, Callable, List
from pathlib import Path
from dataclasses import dataclass, fields
from pathlib import Path
from utils import sanitize_filename


def parse_path(path: str | None) -> Path:
    if path is None:
        raise ValueError("path cannot be None")
    try:
        return Path(path).expanduser().resolve()
    except Exception:
        raise ValueError(f"path {path} cannot resolved")


class Profile(BaseModel):
    name: str
    server_location: Annotated[Path, AfterValidator(parse_path)]
    backup_location: Annotated[Path, AfterValidator(parse_path)]
    server_version: str
    entrypoint: str
    

    def as_dict(self) -> dict[str, Any]:
        # json mode normalizes values to primitive types
        # e.g. Path -> str
        return self.model_dump(mode="json")
    

class TypeNotSupportedError(Exception):
    def __init__(self, name: str):
        super().__init__(f"Unsupported type {name}")


class ParseError(Exception):
    def __init__(self):
        super().__init__("Cannot parse data")


class DynamicParser:
    Parser = Callable[[str], dict[str, Any]]

    __parsers: dict[str, Parser] = {
        "yml": yaml.safe_load,
        "yaml": yaml.safe_load,
    }

    def __get_parser(self, typename: str) -> Parser:
        parser = self.__parsers.get(typename)
        if parser is None:
            raise TypeNotSupportedError(typename)
        return parser
            

    def supports(self, typename: str) -> bool:
        return typename in self.__parsers


    def parse(self, typename: str, data: str) -> dict[str, Any]:
        parser = self.__get_parser(typename)
        try:
            return parser(data)
        except Exception as e:
            raise ParseError() from e



@dataclass
class ProfileInfo:
    location: str
    profile: Profile | None
    
    def is_valid(self) -> bool:
        return self.profile != None


class ProfileRepository(ABC):
    def load(self, name: str) -> Profile:
        ...

    def save(self, name: str, config: Profile) -> str:
        ...

    def list(self) -> List[ProfileInfo]:
        ...

    def exists(self, name: str) -> bool:
        ...


class ProfileNotFoundError(Exception):
    def __init__(self, name: str):
        super().__init__(f"Profile {name} does not exist")


def try_safe_cast(data: Any) -> Profile | None:
    if isinstance(data, Profile):
        return data
    if not isinstance(data, dict):
        return None
    try:
        config_fields = {f.name for f in fields(Profile)}
        filtered_data: dict[str, Any] = {k: data[k] for k in config_fields if k in data}
        return Profile(**filtered_data)
    except (TypeError, ValueError):
        return None


class FileProfileRepository(ProfileRepository):
    __storage_dir: Path
    __parser: DynamicParser

    def __init__(self, path: Path):
        if not path.exists() or not path.is_dir():
            raise RuntimeError(f"Path {path} is not a directory or does not exist")
        self.__storage_dir = Path(path)
        self.__parser = DynamicParser()


    def __scoped_name(self, name: str) -> str:
        return sanitize_filename(name)


    def __scoped_path(self, name: str) -> Path:
        return self.__storage_dir.joinpath(f"{name}.yml")
    
    
    def __try_load(self, path: Path) -> Profile | None:
        if not path.is_file():
            return None
        try:
            read = path.read_text()
            parsed = self.__parser.parse("yml", read)
            return Profile(**parsed)
        except TypeNotSupportedError:
            return None # Don't swallow this
        except ParseError:
            return None # Don't swallow this
        except ValidationError:
            return None # Don't swallow this

    
    def __find_profile(self, query: str):
        expected_path = self.__scoped_path(self.__scoped_name(query))
        
        # Try expected location
        current = self.__try_load(expected_path)
        if current != None and current.name == query:
            return current # Profile found in expected file
        
        # Fishing in the dark... 
        # iter all yml files in profile dir, and check if any match the provided name
        for path in self.__storage_dir.glob("*.yml"):
            current = self.__try_load(path)
            if current != None and current.name == query:
                return current # Profile found in different file
            
        return None # Profile not found

        
    def load(self, name: str) -> Profile:
        loaded = self.__find_profile(name)
        if loaded != None:
            return loaded
        else:
            raise ProfileNotFoundError(name)
        

    def save(self, name: str, config: Profile) -> str:
        name = self.__scoped_name(name)
        path = self.__storage_dir.joinpath(f"{name}.yml")
        serialized = yaml.safe_dump(config.as_dict(), sort_keys=False)

        with open(path, 'w+') as file:
            file.write(serialized)

        return str(path)


    def list(self) -> List[ProfileInfo]:
        return [
            ProfileInfo(path.name, self.__try_load(path))
            for path in self.__storage_dir.glob("*.yml")
        ]


    def exists(self, name: str) -> bool:
        return self.__find_profile(name) != None