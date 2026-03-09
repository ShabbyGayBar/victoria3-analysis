import os
from glob import glob
import errno
import pyradox

# If you know the location of your games but it is not being found automatically, add it to the top of this list.
# Uses glob, but not recursively (no **).
prefixes = [
    r"/Program Files*/Steam/steamapps/common/",  # windows
    r"/Steam/steamapps/common/",
    r"~/Library/Application Support/Steam/steamapps/common/",  # mac
    r"~/*steam/steam/SteamApps/common",  # linux
]

replace_strings = [
    "?=",
    "!=",
]

game_directories = {}


def get_vic3_directory() -> str:
    game_suffix = "Victoria 3/game"

    for prefix in prefixes:
        pattern = os.path.join(prefix, game_suffix)
        candidates = glob(pattern)
        if len(candidates) > 0:
            return candidates[0]
    else:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), game_suffix)


def parse_merge(path, merge_levels: int = 0):
    """Given a directory, return a Tree as if all .txt files in the directory were a single file"""

    result = pyradox.Tree()
    for filename in sorted(os.listdir(path)):
        fullpath = os.path.join(path, filename)
        with open(fullpath, "r", encoding="utf-8-sig") as f:
            if filename.endswith(".md"):
                continue  # Skip markdown files
            content = f.read()
            # Replace all special strings with '=' to prevent pyradox from treating them as merge directives
            for str in replace_strings:
                content = content.replace(str, "=")
            tree = pyradox.parse(content)
            result.merge(tree, merge_levels)
    return result
