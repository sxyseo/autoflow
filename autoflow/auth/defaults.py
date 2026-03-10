"""
Autoflow Authentication Defaults

Provides default roles and permissions for RBAC.
Defines common permissions for specs, tasks, and runs resources.

Usage:
    from autoflow.auth.defaults import seed_roles_and_permissions, get_default_permissions
    from autoflow.db.models import SessionLocal

    # Seed default roles and permissions into the database
    db = SessionLocal()
    try:
        seed_roles_and_permissions(db)
        db.commit()
    finally:
        db.close()

    # Get list of default permissions (without DB access)
    perms = get_default_permissions()
    print(f"Default permissions: {[p['name'] for p in perms]}")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Default permissions for specs, tasks, and runs
DEFAULT_PERMISSIONS = [
    # Specs permissions
    {
        "id": str(uuid4()),
        "name": "specs:read",
        "description": "Can view and read specifications",
        "resource": "specs",
        "action": "read",
    },
    {
        "id": str(uuid4()),
        "name": "specs:write",
        "description": "Can create and modify specifications",
        "resource": "specs",
        "action": "write",
    },
    {
        "id": str(uuid4()),
        "name": "specs:delete",
        "description": "Can delete specifications",
        "resource": "specs",
        "action": "delete",
    },
    {
        "id": str(uuid4()),
        "name": "specs:admin",
        "description": "Full administrative access to specifications",
        "resource": "specs",
        "action": "admin",
    },
    # Tasks permissions
    {
        "id": str(uuid4()),
        "name": "tasks:read",
        "description": "Can view and read tasks",
        "resource": "tasks",
        "action": "read",
    },
    {
        "id": str(uuid4()),
        "name": "tasks:write",
        "description": "Can create and modify tasks",
        "resource": "tasks",
        "action": "write",
    },
    {
        "id": str(uuid4()),
        "name": "tasks:delete",
        "description": "Can delete tasks",
        "resource": "tasks",
        "action": "delete",
    },
    {
        "id": str(uuid4()),
        "name": "tasks:admin",
        "description": "Full administrative access to tasks",
        "resource": "tasks",
        "action": "admin",
    },
    # Runs permissions
    {
        "id": str(uuid4()),
        "name": "runs:read",
        "description": "Can view and read runs",
        "resource": "runs",
        "action": "read",
    },
    {
        "id": str(uuid4()),
        "name": "runs:write",
        "description": "Can create and modify runs",
        "resource": "runs",
        "action": "write",
    },
    {
        "id": str(uuid4()),
        "name": "runs:delete",
        "description": "Can delete runs",
        "resource": "runs",
        "action": "delete",
    },
    {
        "id": str(uuid4()),
        "name": "runs:admin",
        "description": "Full administrative access to runs",
        "resource": "runs",
        "action": "admin",
    },
]

# Default roles with their associated permissions
DEFAULT_ROLES = [
    {
        "id": str(uuid4()),
        "name": "admin",
        "description": "Full system access - can perform all actions",
        "is_system": True,
        "permissions": [
            "specs:read",
            "specs:write",
            "specs:delete",
            "specs:admin",
            "tasks:read",
            "tasks:write",
            "tasks:delete",
            "tasks:admin",
            "runs:read",
            "runs:write",
            "runs:delete",
            "runs:admin",
        ],
    },
    {
        "id": str(uuid4()),
        "name": "developer",
        "description": "Can create and modify specs, tasks, and runs",
        "is_system": True,
        "permissions": [
            "specs:read",
            "specs:write",
            "tasks:read",
            "tasks:write",
            "runs:read",
            "runs:write",
        ],
    },
    {
        "id": str(uuid4()),
        "name": "viewer",
        "description": "Read-only access to specs, tasks, and runs",
        "is_system": True,
        "permissions": [
            "specs:read",
            "tasks:read",
            "runs:read",
        ],
    },
    {
        "id": str(uuid4()),
        "name": "auditor",
        "description": "Can view all resources and audit logs",
        "is_system": True,
        "permissions": [
            "specs:read",
            "tasks:read",
            "runs:read",
        ],
    },
]


def get_default_permissions() -> list[dict]:
    """
    Get list of default permissions.

    Returns a copy of the default permissions dictionary.
    Use this function to inspect default permissions without database access.

    Returns:
        List of permission dictionaries

    Example:
        >>> perms = get_default_permissions()
        >>> specs_perms = [p for p in perms if p['resource'] == 'specs']
        >>> len(specs_perms)
        4
    """
    return [perm.copy() for perm in DEFAULT_PERMISSIONS]


def get_default_roles() -> list[dict]:
    """
    Get list of default roles.

    Returns a copy of the default roles dictionary.
    Use this function to inspect default roles without database access.

    Returns:
        List of role dictionaries with permission names

    Example:
        >>> roles = get_default_roles()
        >>> dev_role = next(r for r in roles if r['name'] == 'developer')
        >>> dev_role['permissions']
        ['specs:read', 'specs:write', 'tasks:read', 'tasks:write', 'runs:read', 'runs:write']
    """
    return [role.copy() for role in DEFAULT_ROLES]


def seed_roles_and_permissions(
    session: Session,
    *,
    skip_existing: bool = True,
) -> dict[str, int]:
    """
    Seed default roles and permissions into the database.

    Creates all default permissions and roles if they don't exist.
    This function is idempotent - it can be called multiple times safely.

    Args:
        session: SQLAlchemy database session
        skip_existing: If True, skip records that already exist (default: True)

    Returns:
        Dictionary with counts of created and existing records:
        {
            "permissions_created": int,
            "permissions_existing": int,
            "roles_created": int,
            "roles_existing": int,
        }

    Raises:
        Exception: If database operation fails (session rollback required)

    Example:
        >>> from autoflow.db.models import SessionLocal
        >>> db = SessionLocal()
        >>> try:
        ...     result = seed_roles_and_permissions(db)
        ...     print(f"Created {result['permissions_created']} permissions")
        ...     db.commit()
        ... finally:
        ...     db.close()

    Example:
        >>> # Force recreate all records (use with caution)
        >>> result = seed_roles_and_permissions(db, skip_existing=False)
    """
    from autoflow.db.models import Permission, Role

    counts = {
        "permissions_created": 0,
        "permissions_existing": 0,
        "roles_created": 0,
        "roles_existing": 0,
    }

    # Create permissions
    for perm_data in DEFAULT_PERMISSIONS:
        perm_id = perm_data["id"]
        perm_name = perm_data["name"]

        existing = session.query(Permission).filter(Permission.id == perm_id).first()

        if existing:
            counts["permissions_existing"] += 1
            if skip_existing:
                continue

        if not existing:
            permission = Permission(
                id=perm_id,
                name=perm_name,
                description=perm_data.get("description"),
                resource=perm_data["resource"],
                action=perm_data["action"],
            )
            session.add(permission)
            counts["permissions_created"] += 1

    # Flush to ensure permissions are persisted before creating roles
    session.flush()

    # Create roles and associate permissions
    for role_data in DEFAULT_ROLES:
        role_id = role_data["id"]
        role_name = role_data["name"]

        existing = session.query(Role).filter(Role.id == role_id).first()

        if existing:
            counts["roles_existing"] += 1
            if skip_existing:
                continue

        if not existing:
            role = Role(
                id=role_id,
                name=role_name,
                description=role_data.get("description"),
                is_system=role_data.get("is_system", False),
            )

            # Associate permissions with role
            for perm_name in role_data.get("permissions", []):
                permission = session.query(Permission).filter(
                    Permission.name == perm_name
                ).first()
                if permission:
                    role.permissions.append(permission)

            session.add(role)
            counts["roles_created"] += 1

    return counts


def ensure_default_permissions(session: Session) -> bool:
    """
    Ensure all default permissions exist in the database.

    Creates any missing default permissions. Returns True if all permissions
    exist or were successfully created.

    Args:
        session: SQLAlchemy database session

    Returns:
        True if all default permissions exist, False otherwise

    Example:
        >>> if ensure_default_permissions(session):
        ...     print("All default permissions are available")
        ...     session.commit()
    """
    try:
        result = seed_roles_and_permissions(session, skip_existing=True)
        session.commit()
        return (
            result["permissions_created"] == 0
            and result["permissions_existing"] == len(DEFAULT_PERMISSIONS)
        )
    except Exception:
        session.rollback()
        return False


def get_permission_by_name(session: Session, permission_name: str) -> Optional[dict]:
    """
    Get a default permission by name.

    Returns the permission dictionary if it's a default permission,
    None otherwise.

    Args:
        session: SQLAlchemy database session
        permission_name: Permission name to look up

    Returns:
        Permission dictionary or None

    Example:
        >>> perm = get_permission_by_name(session, "specs:write")
        >>> perm['description'] if perm else None
        'Can create and modify specifications'
    """
    default_perms = {p["name"]: p for p in DEFAULT_PERMISSIONS}
    return default_perms.get(permission_name)


def get_role_by_name(session: Session, role_name: str) -> Optional[dict]:
    """
    Get a default role by name.

    Returns the role dictionary if it's a default role,
    None otherwise.

    Args:
        session: SQLAlchemy database session
        role_name: Role name to look up

    Returns:
        Role dictionary or None

    Example:
        >>> role = get_role_by_name(session, "developer")
        >>> role['description'] if role else None
        'Can create and modify specs, tasks, and runs'
    """
    default_roles = {r["name"]: r for r in DEFAULT_ROLES}
    return default_roles.get(role_name)
