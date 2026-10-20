"""Pure field-level three-way merge helpers for the Activity Workbench."""
from copy import deepcopy

ENTITY_LISTS = {"events", "tasks", "assets", "changes", "suppliers", "workPackages", "venues"}


def _same(a, b):
    return a == b


def _merge_value(base, current, incoming, path, conflicts):
    if _same(incoming, base):
        return deepcopy(current)
    if _same(current, base) or _same(current, incoming):
        return deepcopy(incoming)
    if isinstance(base, dict) and isinstance(current, dict) and isinstance(incoming, dict):
        result = {}
        for key in set(base) | set(current) | set(incoming):
            b = base.get(key, _MISSING)
            c = current.get(key, _MISSING)
            i = incoming.get(key, _MISSING)
            if b is _MISSING:
                if c is _MISSING:
                    result[key] = deepcopy(i)
                elif i is _MISSING or _same(c, i):
                    result[key] = deepcopy(c)
                else:
                    conflicts.append({"path": f"{path}.{key}", "base": None, "current": c, "incoming": i})
                    result[key] = deepcopy(c)
            elif c is _MISSING or i is _MISSING:
                if c is _MISSING and i is _MISSING:
                    continue
                survivor = i if c is _MISSING else c
                if _same(survivor, b):
                    if c is not _MISSING and i is _MISSING:
                        continue
                    if i is not _MISSING:
                        result[key] = deepcopy(i)
                else:
                    conflicts.append({"path": f"{path}.{key}", "base": b, "current": None if c is _MISSING else c, "incoming": None if i is _MISSING else i})
                    if c is not _MISSING:
                        result[key] = deepcopy(c)
            else:
                result[key] = _merge_value(b, c, i, f"{path}.{key}", conflicts)
        return result
    conflicts.append({"path": path or "$", "base": _display(base), "current": _display(current), "incoming": _display(incoming)})
    return deepcopy(current)


class _Missing:
    pass

_MISSING = _Missing()


def _display(value):
    return None if value is _MISSING else value


def _merge_entity_list(base_list, current_list, incoming_list, key, conflicts, collection):
    base_map = {x.get("id"): x for x in base_list if isinstance(x, dict) and x.get("id") is not None}
    current_map = {x.get("id"): x for x in current_list if isinstance(x, dict) and x.get("id") is not None}
    incoming_map = {x.get("id"): x for x in incoming_list if isinstance(x, dict) and x.get("id") is not None}
    result = {}
    ids = set(base_map) | set(current_map) | set(incoming_map)
    for entity_id in ids:
        b = base_map.get(entity_id, _MISSING)
        c = current_map.get(entity_id, _MISSING)
        i = incoming_map.get(entity_id, _MISSING)
        path = f"{collection}[{entity_id}]"
        if collection == "changes":
            # Audit-style entries are append-only. Keep server entries and append client entries once.
            chosen = c if i is _MISSING else i if c is _MISSING else c
            result[entity_id] = deepcopy(chosen)
            continue
        if b is _MISSING:
            if c is _MISSING and i is not _MISSING:
                result[entity_id] = deepcopy(i)
            elif i is _MISSING and c is not _MISSING:
                result[entity_id] = deepcopy(c)
            elif c is not _MISSING and i is not _MISSING:
                result[entity_id] = _merge_value({}, c, i, path, conflicts)
            continue
        if c is _MISSING and i is _MISSING:
            continue
        if i is _MISSING:
            if _same(c, b):
                continue
            conflicts.append({"path": path, "base": b, "current": c, "incoming": None})
            result[entity_id] = deepcopy(c)
            continue
        if c is _MISSING:
            if _same(i, b):
                continue
            conflicts.append({"path": path, "base": b, "current": None, "incoming": i})
            continue
        result[entity_id] = _merge_value(b, c, i, path, conflicts)
    # Keep client/server ordering stable: incoming order first, then server-only records.
    ordered = []
    seen = set()
    for item in incoming_list + current_list:
        entity_id = item.get("id") if isinstance(item, dict) else None
        if entity_id in result and entity_id not in seen:
            ordered.append(result[entity_id]); seen.add(entity_id)
    for entity_id, item in result.items():
        if entity_id not in seen:
            ordered.append(item)
    return ordered


def merge_state(base, current, incoming):
    """Merge a client's edits against the latest server state, returning conflicts per field."""
    conflicts = []
    result = {}
    for key in set(base) | set(current) | set(incoming):
        b = base.get(key, _MISSING)
        c = current.get(key, _MISSING)
        i = incoming.get(key, _MISSING)
        if key in ENTITY_LISTS and isinstance(b, list) and isinstance(c, list) and isinstance(i, list):
            result[key] = _merge_entity_list(b, c, i, "id", conflicts, key)
        elif b is _MISSING:
            if c is _MISSING:
                result[key] = deepcopy(i)
            elif i is _MISSING or _same(c, i):
                result[key] = deepcopy(c)
            else:
                conflicts.append({"path": key, "base": None, "current": c, "incoming": i})
                result[key] = deepcopy(c)
        elif c is _MISSING or i is _MISSING:
            survivor = i if c is _MISSING else c
            if _same(survivor, b):
                if i is not _MISSING:
                    result[key] = deepcopy(i)
            else:
                conflicts.append({"path": key, "base": b, "current": None if c is _MISSING else c, "incoming": None if i is _MISSING else i})
                if c is not _MISSING:
                    result[key] = deepcopy(c)
        else:
            result[key] = _merge_value(b, c, i, key, conflicts)
    return result, conflicts
