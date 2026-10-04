"""Owner, editor, and viewer rules. All permission logic lives here, in Python."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Role hierarchy: higher number means more permissions
ROLE_LEVELS = {
    "owner": 3,
    "editor": 2,
    "viewer": 1,
}

def role_level(role: Optional[str]) -> int:
    """Return the numeric level of a role, 0 if the role is not recognized."""
    level = ROLE_LEVELS.get(role, 0)
    if role is not None and level == 0:
        logger.warning(f"Unrecognized role '{role}' treated as having no permissions")
    return level

def has_permission(user_role: Optional[str], required_permission: str) -> bool:
    """
    Check if a user with the given role has at least the required permission.

    Args:
        user_role: The user's role on the resource (e.g., "owner", "editor", "viewer", or None).
        required_permission: The permission to check (must be one of "owner", "editor", "viewer").

    Returns:
        True if the user has the required permission or higher, False otherwise.
    """
    if required_permission not in ROLE_LEVELS:
        logger.error(f"Invalid required permission: {required_permission}")
        raise ValueError(f"Invalid required permission: {required_permission}")

    return role_level(user_role) >= role_level(required_permission)