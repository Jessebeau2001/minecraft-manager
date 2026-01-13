
from pydantic import ValidationError
import yaml

from profiles import Profile


def test_hello():
    data = """
        name: test profile
        server_location: /home/jesse/mc-manager/tmp/servers/test-server
        backup_dir: /dev/null
        mc_version: 1.21.10-vanilla
        entrypoint: java -jar server.jar --nogui"""
    
    try:
        loaded = yaml.safe_load(data)
        profile = Profile(**loaded)
        print(profile)
    except ValidationError as e:
        print(e)