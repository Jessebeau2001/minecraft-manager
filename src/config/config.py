from typing import Any, NamedTuple, Protocol, List
from dataclasses import asdict, dataclass, fields

class Options(NamedTuple):
    config_dir: str

options = Options('./tmp/configs')

@dataclass
class Config:
    name: str
    server_location: str
    server_version: str
    backup_location: str

    def as_dict(self):
        return asdict(self)


@dataclass
class ConfigInfo:
    location: str
    config: Config


class ConfigRepository(Protocol):
    def load(self, name: str) -> Config:
        ...

    def save(self, name: str, config: Config) -> None:
        ...

    def list(self) -> List[ConfigInfo]:
        ...

    def exists(self, name: str) -> bool:
        ...
    

import yaml
from pathlib import Path


def try_safe_cast(data: Any) -> Config | None:
    if not isinstance(data, dict):
        return None
    try:
        config_fields = {f.name for f in fields(Config)}
        filtered_data: dict[str, Any] = {k: data[k] for k in config_fields if k in data}
        return Config(**filtered_data)
    except TypeError:
        return None
    

class FileConfigRepo:
    def __init__(self, path: str):
        self.storage_dir = Path(path)
        self.storage_dir.mkdir(parents=True, exist_ok=True)


    def _get_path_for(self, name: str) -> Path:
        return self.storage_dir.joinpath(f"{name}.yml")
    

    def _try_load(self, path: Path | str) -> Config | None:
        if isinstance(path, str):
            path = self._get_path_for(path)

        if not path.is_file():
            return None
        
        try:
            read = path.read_text()
            parsed = yaml.safe_load(read)
            return try_safe_cast(parsed)
        except (yaml.YAMLError):
            return None
        

    def load(self, name: str) -> Config:
        loaded = self._try_load(name)
        if loaded != None:
            return loaded
        else:
            raise Exception()
        

    def save(self, name: str, config: Config, overwrite: bool = False) -> None:
        path = self.storage_dir.joinpath(f"{name}.yml")
        serialized = yaml.safe_dump(config.as_dict(), sort_keys=False)

        with open(path, 'w+') as file:
            file.write(serialized)


    def list(self) -> List[ConfigInfo]:
        return [
            ConfigInfo(path.name, cfg)
            for path in self.storage_dir.glob("*.yml")
            if (cfg := self._try_load(path)) is not None
        ]


    def exists(self, name: str) -> bool:
        return self._try_load(name) != None