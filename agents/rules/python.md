# Python Usage Rules for Fall of Titans

## Type Safety

- **Never suppress type errors.** Do not use `# type: ignore`, or `typing.cast()` to silence Pylance diagnostics.
  - The Python equivalents of `as any` and `@ts-ignore` are `Any`, `cast()`, and `# type: ignore` — all are forbidden.

## Type Narrowing for Untyped Libraries

- **Use assert-based narrowing.** When a library has no type stubs (e.g. `pyradox`), narrow with `assert isinstance(x, ExpectedType)` so Pylance infers the correct type and runtime still fails fast on wrong types.

- **Create narrow-and-return helpers.** For repeated access patterns, extract small helpers that assert and return the narrowed type:

  ```python
  def _tree(value) -> Tree:
      """Assert a value is a Tree and return it (type narrowing for untyped pyradox)."""
      assert isinstance(value, Tree), f"Expected Tree, got {type(value).__name__}"
      return value


  def _tree_iter(values):
      """Yield only Tree items from an iterator, asserting each one."""
      for v in values:
          yield _tree(v)
  ```

  Call sites stay clean:

  ```python
  v_st = _tree(vanilla_tree["STATES"][f"s:{state_name}"])
  v_hl = set(v_st.find_all("add_homeland"))
  ```

## Toolchain

- **Use `uv` exclusively.** Always use `uv pip` instead of `pip` and `uv run` instead of `python3` for package management and script execution.

## Game File Parsing

- **Use `pyradox` for parsing Paradox `.txt` files.** Always parse vanilla or mod game files (states, countries, cultures, history, defines) through the `pyradox` library — never hand-roll a parser. PyPI package name is `pyradox-txt-parser` (`uv pip install pyradox-txt-parser`).
- **Prefer `open(path, encoding="utf-8-sig")` + `pyradox.parse(content)` over `pyradox.parse_file`** when working outside pyradox's game-directory config system. `parse_file` requires a `game=` argument that maps to a hardcoded encoding table; for mod scripts, reading the file yourself with `utf-8-sig` (Victoria 3's encoding) then calling `pyradox.parse(string)` is simpler and avoids the config dependency.

## pyradox API Usage Guide

The public API is re-exported from `pyradox.__init__`; the only import the repository needs:

```python
import pyradox
from pyradox.datatype.tree import Tree
```

### Tree — Reading

`Tree` is an ordered dict-like container; keys are matched case-insensitively but preserve original casing. Because pyradox ships no type stubs, wrap every access with the `_tree()` helper to narrow from `tuple[Unknown, ...] | None` to `Tree` (see "Type Narrowing" section above).

| Operation | Behavior |
|---|---|
| `tree["key"]` | Returns the **LAST** value matching `key`, or `None` if absent |
| `tree.find("key", default=None)` | Returns the **first** value matching `key`, or `default` |
| `tree.find_all("key", reverse=False, recurse=False)` | Iterator over **all** values matching `key`; set `recurse=True` to descend into nested Trees |
| `"key" in tree` | Same as `tree.contains("key")` |
| `tree.items()`, `.keys()`, `.values()` | OrderedDict-style iteration |
| `len(tree)` | Number of key-value pairs at this level |
| `tree.at(i)`, `.key_at(i)`, `.value_at(i)` | Positional access |

```python
states = _tree(tree["STATES"])
for cs_tree in _tree_iter(states.find_all("create_state")):
    country = cs_tree["country"]              # last-value semantics, None-safe
    provinces = list(cs_tree.find_all("owned_provinces"))
```

### Tree — Mutation

| Operation | Behavior |
|---|---|
| `tree.append(key, value, in_group=False, operator='=')` | Add a new item at the end |
| `tree.insert(i, key, value)` | Insert at index `i` |
| `tree[key] = value` | Replace the **LAST** item with `key` if it exists, else append |
| `del tree[key]` | Delete by key (last match by default) |
| `tree += other` | Append deep-copied items from `other` |
| `tree.merge(other, merge_levels=0)` | Recursive merge; `merge_levels=-1` means fully recursive |
| `tree.update(other)` / `tree.weak_update(other)` | Shallow / insert-if-absent |

### Groups

A Paradox "group" line like `owned_provinces = { xA1B2C xD3E4F }` parses as multiple `_Item`s sharing one key with `in_group=True`. To build a group programmatically, pass `in_group=True` on each appended value:

```python
cs = Tree()
cs.append("country", "c:MRL")
for p in province_ids:
    cs.append("owned_provinces", p, in_group=True)
state.append("create_state", cs)
```

`find_all("owned_provinces")` over a group yields every grouped value in order.

### Serialization

`str(tree)` and `tree.prettyprint(level=0, indent_string='    ', include_comments=True)` produce canonical Paradox `.txt` output with 4-space indentation and preserved comments. Victoria 3 mod files typically use **tab** indentation, so when writing mod output, prefer a custom `serialize()` walker that iterates `tree._data` directly (see `scripts/generate_states.py:112` for the reference implementation) and emits `\t` indentation. Custom walkers must handle the `in_group` flag to reconstruct `{ a b c }` one-line groups.

```python
def serialize(tree, level=0, indent="\t"):
    result = ""
    group_key = None
    for item in tree._data:
        if group_key is not None:
            if item.in_group and _match(item.key, group_key):
                result += f"{item.value} "
                continue
            else:
                result = result.rstrip() + " }\n"
                group_key = None
        if item.in_group:
            group_key = item.key
            result += f"{indent * level}{item.key} = {{ {item.value} "
        elif isinstance(item.value, Tree):
            result += f"{indent * level}{item.key} = {{\n"
            result += serialize(item.value, level + 1, indent)
            result += f"{indent * level}}}\n"
        else:
            result += f"{indent * level}{item.key} = {item.value}\n"
    if group_key is not None:
        result = result.rstrip() + " }\n"
    return result
```

### Common pitfalls

- `[]` access returns the **last** match, not the first; for singletons both are equivalent, but for groups use `find_all`.
- `find_all` is a generator, not a list — wrap in `list(...)` if you need length or reiteration.
- pyradox has **no type stubs**; every subscript result must be narrowed with `_tree()` / `_tree_iter()` (see "Type Narrowing for Untyped Libraries"). `tree["key"]` returns `tuple[Unknown, ...] | None` to Pylance.
- `parse_file` without `game=` raises `KeyError` because `game_encodings` has no Vic3 entry — read the file yourself and use `parse(string)`.
- `Tree.__setitem__` replaces only the **last** matching item; to replace all, delete then append, or use `merge`.

## Rationale

These rules keep the codebase statically typed end-to-end without stubs, while preserving runtime safety. They were adopted during the `scripts/generate_states.py` migration to `pyradox`, which remains the canonical reference for parsing, mutating, and serializing Victoria 3 `.txt` files in this repo.
