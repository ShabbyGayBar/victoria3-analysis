import os
import pyradox

# Determine the game root directory based on the operating system
if os.name == "nt":  # Windows
    VIC3_DIR = "C:/Program Files (x86)/Steam/steamapps/common/Victoria 3/game"
elif os.name == "posix":  # macOS or Linux
    VIC3_DIR = os.path.expanduser(
        "~/.local/share/Steam/steamapps/common/Victoria 3/game"
    )

replace_strings = [
    '?=',
    '!=',
]

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
            for old, new in replace_strings:
                content = content.replace(old, new)
            tree = pyradox.parse(content)
            result.merge(tree, merge_levels)
    return result
