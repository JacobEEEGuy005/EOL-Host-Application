"""Simple on-disk DBC store and metadata index helpers.

Functions here centralize where persisted DBC files and an index.json live.
The store location is controlled by the environment variable DBCS_PATH. If not
set, it defaults to <repo_root>/backend/data/dbcs.
"""
from __future__ import annotations

import os
import json
import pathlib
from datetime import datetime
from typing import Dict, Any, Tuple

import cantools


def get_repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def get_dbcs_dir() -> str:
    env = os.environ.get("DBCS_PATH")
    if env:
        return os.path.abspath(env)
    repo_root = get_repo_root()
    return os.path.join(repo_root, "backend", "data", "dbcs")


def ensure_dir() -> str:
    d = get_dbcs_dir()
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)
    return d


def _index_path(dbcs_dir: str) -> str:
    return os.path.join(dbcs_dir, "index.json")


def load_index(dbcs_dir: str) -> Dict[str, Any]:
    p = _index_path(dbcs_dir)
    if not os.path.exists(p):
        return {"files": {}}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"files": {}}


def save_index(dbcs_dir: str, index: Dict[str, Any]) -> None:
    p = _index_path(dbcs_dir)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, sort_keys=True)


def _unique_name(dbcs_dir: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    candidate = name
    i = 1
    while os.path.exists(os.path.join(dbcs_dir, candidate)):
        candidate = f"{base}-{i}{ext}"
        i += 1
    return candidate


def save_dbc(name: str, contents: bytes) -> str:
    """Save DBC bytes to the store. If a name conflict exists, generate a unique name.

    Returns the actual filename used.
    """
    dbcs_dir = ensure_dir()
    final_name = name
    path = os.path.join(dbcs_dir, final_name)
    if os.path.exists(path):
        final_name = _unique_name(dbcs_dir, name)
        path = os.path.join(dbcs_dir, final_name)
    with open(path, "wb") as fh:
        fh.write(contents)
    # update index
    idx = load_index(dbcs_dir)
    idx.setdefault("files", {})[final_name] = {
        "filename": final_name,
        "original_name": name,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    save_index(dbcs_dir, idx)
    return final_name


def load_all_dbcs() -> Dict[str, cantools.database.Database]:
    dbs: Dict[str, cantools.database.Database] = {}
    dbcs_dir = ensure_dir()
    for fname in sorted(os.listdir(dbcs_dir)):
        if not fname.lower().endswith(".dbc"):
            continue
        path = os.path.join(dbcs_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                contents = fh.read()
            db = cantools.database.load_string(contents)
            dbs[fname] = db
        except Exception:
            # ignore load errors but continue
            continue
    return dbs


def delete_dbc(name: str) -> bool:
    dbcs_dir = ensure_dir()
    path = os.path.join(dbcs_dir, name)
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
    except Exception:
        return False
    idx = load_index(dbcs_dir)
    idx.get("files", {}).pop(name, None)
    save_index(dbcs_dir, idx)
    return True


def rename_dbc(old: str, new: str) -> Tuple[bool, str]:
    dbcs_dir = ensure_dir()
    old_path = os.path.join(dbcs_dir, old)
    if not os.path.exists(old_path):
        return False, "old not found"
    new_path = os.path.join(dbcs_dir, new)
    if os.path.exists(new_path):
        return False, "new exists"
    try:
        os.rename(old_path, new_path)
    except Exception as e:
        return False, str(e)
    idx = load_index(dbcs_dir)
    meta = idx.get("files", {}).pop(old, None)
    if meta is None:
        meta = {"filename": new, "original_name": old, "uploaded_at": datetime.utcnow().isoformat() + "Z"}
    meta["filename"] = new
    idx.setdefault("files", {})[new] = meta
    save_index(dbcs_dir, idx)
    return True, ""


def get_index() -> Dict[str, Any]:
    dbcs_dir = ensure_dir()
    return load_index(dbcs_dir)
