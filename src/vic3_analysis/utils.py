"""
Utility helpers for locating the Victoria 3 game installation and parsing
Paradox script files.
"""
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
    """Search common Steam library paths and return the Victoria 3 game directory.

    Returns:
        The absolute path to the ``Victoria 3/game`` directory.

    Raises:
        FileNotFoundError: If the Victoria 3 game directory cannot be found
            in any of the known Steam library locations.
    """
    game_suffix = "Victoria 3/game"

    for prefix in prefixes:
        pattern = os.path.join(prefix, game_suffix)
        candidates = glob(pattern)
        if len(candidates) > 0:
            return candidates[0]
    else:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), game_suffix)


def parse_merge(path: str, merge_levels: int = 0) -> pyradox.Tree:
    """Parse all ``.txt`` files in *path* and merge them into a single Tree.

    Args:
        path: Directory containing the Paradox script (``.txt``) files to parse.
        merge_levels: Number of levels deep to merge nested Trees. Passed
            directly to ``pyradox.Tree.merge``.  Defaults to ``0``.

    Returns:
        A ``pyradox.Tree`` representing the merged contents of all ``.txt``
        files found in *path* (sorted alphabetically).
    """

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
