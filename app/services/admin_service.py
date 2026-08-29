"""Dynamic admin management backed by a JSON file."""

import json
import os
from typing import Set

from app.config.settings import settings

_ADMINS_FILE = os.path.join("data", "admins.json")


def _load_dynamic_admins() -> Set[int]:
    if not os.path.exists(_ADMINS_FILE):
        return set()
    try:
        with open(_ADMINS_FILE, "r") as f:
            data = json.load(f)
        return set(data.get("admin_ids", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def _save_dynamic_admins(admins: Set[int]) -> None:
    os.makedirs(os.path.dirname(_ADMINS_FILE), exist_ok=True)
    with open(_ADMINS_FILE, "w") as f:
        json.dump({"admin_ids": sorted(admins)}, f, indent=2)


def get_admin_ids() -> Set[int]:
    """Get all admin IDs: static from .env + dynamic from JSON file."""
    static_ids = set()
    if settings.admin_ids.strip():
        static_ids = {
            int(admin_id.strip())
            for admin_id in settings.admin_ids.split(",")
            if admin_id.strip()
        }
    dynamic_ids = _load_dynamic_admins()
    return static_ids | dynamic_ids


def add_admin(user_id: int) -> bool:
    """Add a user ID to dynamic admins. Returns True if added, False if already exists."""
    admins = _load_dynamic_admins()
    if user_id in admins:
        return False
    admins.add(user_id)
    _save_dynamic_admins(admins)
    return True


def remove_admin(user_id: int) -> bool:
    """Remove a user ID from dynamic admins. Returns True if removed, False if not found."""
    admins = _load_dynamic_admins()
    if user_id not in admins:
        return False
    admins.discard(user_id)
    _save_dynamic_admins(admins)
    return True
