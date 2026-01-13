from typing import Any, NamedTuple, Protocol, List
from dataclasses import asdict, dataclass, fields

from utils import sanitize_filename

class Options(NamedTuple):
    config_dir: str

options = Options('./tmp/configs')

@dataclass
class Profile:
    name: str
    server_location: str
    server_version: str
    backup_location: str
    entrypoint: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProfileInfo:
    location: str
    profile: Profile | None
    
    def is_valid(self) -> bool:
        return self.profile != None


class ProfileRepository(Protocol):
    def load(self, name: str) -> Profile:
        ...

    def save(self, name: str, config: Profile) -> str:
        ...

    def list(self) -> List[ProfileInfo]:
        ...

    def exists(self, name: str) -> bool:
        ...
    

import yaml
from pathlib import Path


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
    

def generate_profile_filename(name: str) -> str:
    return sanitize_filename(name)


class FileProfileRepository:
    def __init__(self, path: Path):
        self.storage_dir = Path(path)
        if not path.exists() or not path.is_dir():
            raise RuntimeError(f"Path {path} is not a directory or does not exist")


    def __sanitize_name(self, name: str) -> str:
        return sanitize_filename(name)


    def __local_path_for(self, name: str) -> Path:
        return self.storage_dir.joinpath(f"{name}.yml")
    
    
    def __try_load(self, path: Path) -> Profile | None:
        if not path.is_file():
            return None
        try:
            read = path.read_text()
            parsed = yaml.safe_load(read)
            return try_safe_cast(parsed)
        except (yaml.YAMLError):
            return None

    
    def __find_profile(self, query: str):
        expected_path = self.__local_path_for(self.__sanitize_name(query))
        
        # Try expected location
        current = self.__try_load(expected_path)
        if current != None and current.name == query:
            return current # Profile found in expected file
        
        # Fishing in the dark... 
        # iter all yml files in profile dir, and check if any match the provided name
        for path in self.storage_dir.glob("*.yml"):
            current = self.__try_load(path)
            if current != None and current.name == query:
                return current # Profile found in different file
            
        return None # Profile not found

        
    def load(self, name: str) -> Profile:
        loaded = self.__find_profile(name)
        if loaded != None:
            return loaded
        else:
            raise Exception() # TODO: Actual ProfileNotFoundException
        

    def save(self, name: str, config: Profile) -> str:
        generated_name = self.__sanitize_name(name)
        path = self.storage_dir.joinpath(f"{generated_name}.yml")
        serialized = yaml.safe_dump(config.as_dict(), sort_keys=False)

        with open(path, 'w+') as file:
            file.write(serialized)

        return str(path)


    def list(self) -> List[ProfileInfo]:
        return [
            ProfileInfo(path.name, self.__try_load(path))
            for path in self.storage_dir.glob("*.yml")
        ]


    def exists(self, name: str) -> bool:
        return self.__find_profile(name) != None