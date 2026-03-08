"""
Autoflow RBAC Models

Provides Pydantic models for Role-Based Access Control (RBAC).
These models integrate with the database layer while providing clean
API interfaces for authorization operations.

Usage:
    from autoflow.auth.rbac import Role, Permission, Policy, PolicyEffect

    # Create a permission model
    permission = Permission(
        id="perm-123",
        name="specs:write",
        resource="specs",
        action="write"
    )

    # Create a role with permissions
    role = Role(
        id="role-123",
        name="developer",
        description="Can create and modify specs and tasks",
        permissions=[permission]
    )

    # Create an access policy
    policy = Policy(
        id="policy-123",
        name="Allow developers to write specs",
        effect=PolicyEffect.ALLOW,
        resources=["specs/*"],
        actions=["specs:write"],
        conditions={"role": "developer"}
    )
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from autoflow.db.models import Permission as DBPermission
    from autoflow.db.models import Role as DBRole


class PolicyEffect(str, Enum):
    """Effect of an access policy."""

    ALLOW = "allow"
    DENY = "deny"


class Permission(BaseModel):
    """
    Represents a permission in the authentication layer.

    This is a Pydantic model that wraps the database Permission model,
    providing a clean interface for authorization operations.
    Permissions define specific actions that can be performed on resources.

    Attributes:
        id: Unique permission identifier
        name: Permission name in "resource:action" format
        description: Human-readable permission description
        resource: Resource type (e.g., "specs", "tasks", "runs")
        action: Action type (e.g., "read", "write", "delete")
        created_at: Permission creation timestamp

    Example:
        >>> permission = Permission(
        ...     id="perm-123",
        ...     name="specs:write",
        ...     resource="specs",
        ...     action="write"
        ... )
        >>> permission.resource
        'specs'
    """

    id: str
    name: str
    description: Optional[str] = None
    resource: str
    action: str
    created_at: datetime

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """
        Validate permission name format.

        Ensures the name follows the "resource:action" format.

        Args:
            v: Permission name to validate

        Returns:
            Validated permission name

        Raises:
            ValueError: If name format is invalid
        """
        if not isinstance(v, str) or ":" not in v:
            raise ValueError(
                f"Invalid permission name '{v}'. Must be in format 'resource:action'"
            )
        return v

    @classmethod
    def from_db_permission(cls, db_permission: "DBPermission") -> "Permission":
        """
        Create a Permission model from a database Permission.

        Args:
            db_permission: SQLAlchemy database Permission model

        Returns:
            Permission model instance

        Example:
            >>> permission = Permission.from_db_permission(db_permission)
            >>> permission.name
            'specs:write'
        """
        return cls(
            id=db_permission.id,
            name=db_permission.name,
            description=db_permission.description,
            resource=db_permission.resource,
            action=db_permission.action,
            created_at=db_permission.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert permission to dictionary representation.

        Returns:
            Dictionary with permission data

        Example:
            >>> perm_dict = permission.to_dict()
            >>> perm_dict["resource"]
            'specs'
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "resource": self.resource,
            "action": self.action,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        """String representation of Permission."""
        return f"<Permission(id={self.id}, name={self.name})>"


class Role(BaseModel):
    """
    Represents a role in the authentication layer.

    This is a Pydantic model that wraps the database Role model,
    providing a clean interface for authorization operations.
    Roles are collections of permissions that can be assigned to users.

    Attributes:
        id: Unique role identifier
        name: Unique role name (e.g., "admin", "developer")
        description: Human-readable role description
        is_system: System roles cannot be deleted
        created_at: Role creation timestamp
        updated_at: Last update timestamp
        permissions: List of permissions granted by this role

    Example:
        >>> role = Role(
        ...     id="role-123",
        ...     name="developer",
        ...     description="Can create and modify specs and tasks"
        ... )
        >>> role.has_permission("specs:write")
        True
    """

    id: str
    name: str
    description: Optional[str] = None
    is_system: bool = False
    created_at: datetime
    updated_at: datetime
    permissions: list[Permission] = Field(default_factory=list)

    @property
    def permission_names(self) -> set[str]:
        """Get set of permission names granted by this role."""
        return {perm.name for perm in self.permissions}

    def has_permission(self, permission_name: str) -> bool:
        """
        Check if role has a specific permission.

        Args:
            permission_name: Permission name to check (e.g., "specs:write")

        Returns:
            True if role has the permission, False otherwise

        Example:
            >>> role.has_permission("specs:write")
            True
        """
        return permission_name in self.permission_names

    def has_any_permission(self, permission_names: list[str]) -> bool:
        """
        Check if role has any of the specified permissions.

        Args:
            permission_names: List of permission names to check

        Returns:
            True if role has at least one of the permissions

        Example:
            >>> role.has_any_permission(["specs:read", "specs:write"])
            True
        """
        return any(perm in self.permission_names for perm in permission_names)

    def has_all_permissions(self, permission_names: list[str]) -> bool:
        """
        Check if role has all of the specified permissions.

        Args:
            permission_names: List of permission names to check

        Returns:
            True if role has all of the permissions

        Example:
            >>> role.has_all_permissions(["specs:read", "tasks:read"])
            True
        """
        return all(perm in self.permission_names for perm in permission_names)

    @classmethod
    def from_db_role(cls, db_role: "DBRole") -> "Role":
        """
        Create a Role model from a database Role.

        Args:
            db_role: SQLAlchemy database Role model

        Returns:
            Role model instance

        Example:
            >>> role = Role.from_db_role(db_role)
            >>> role.name
            'developer'
        """
        permissions = [
            Permission.from_db_permission(perm)
            for perm in db_role.permissions
        ]

        return cls(
            id=db_role.id,
            name=db_role.name,
            description=db_role.description,
            is_system=db_role.is_system,
            created_at=db_role.created_at,
            updated_at=db_role.updated_at,
            permissions=permissions,
        )

    def to_dict(self, include_permissions: bool = True) -> dict[str, Any]:
        """
        Convert role to dictionary representation.

        Args:
            include_permissions: Whether to include permissions list

        Returns:
            Dictionary with role data

        Example:
            >>> role_dict = role.to_dict()
            >>> role_dict["name"]
            'developer'
        """
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "permission_count": len(self.permissions),
        }

        if include_permissions:
            data["permissions"] = [perm.to_dict() for perm in self.permissions]
            data["permission_names"] = list(self.permission_names)

        return data

    def __repr__(self) -> str:
        """String representation of Role."""
        return f"<Role(id={self.id}, name={self.name})>"


class PolicyCondition(BaseModel):
    """
    Represents a condition for policy evaluation.

    Conditions can be used to create fine-grained access control rules
    based on attributes like user role, resource ownership, time, etc.

    Attributes:
        operator: Comparison operator (eq, ne, in, not_in, etc.)
        key: Attribute key to check (e.g., "role", "owner", "team")
        value: Expected value or list of values

    Example:
        >>> condition = PolicyCondition(
        ...     operator="eq",
        ...     key="role",
        ...     value="developer"
        ... )
    """

    operator: str = "eq"
    key: str
    value: Any

    def matches(self, context: dict[str, Any]) -> bool:
        """
        Check if condition matches the given context.

        Args:
            context: Context data to evaluate against

        Returns:
            True if condition matches, False otherwise

        Example:
            >>> condition = PolicyCondition(operator="eq", key="role", value="admin")
            >>> condition.matches({"role": "admin"})
            True
        """
        context_value = context.get(self.key)

        if self.operator == "eq":
            return context_value == self.value
        elif self.operator == "ne":
            return context_value != self.value
        elif self.operator == "in":
            return context_value in self.value if isinstance(self.value, (list, set)) else False
        elif self.operator == "not_in":
            return context_value not in self.value if isinstance(self.value, (list, set)) else True
        elif self.operator == "exists":
            return self.key in context
        elif self.operator == "not_exists":
            return self.key not in context
        else:
            return False


class Policy(BaseModel):
    """
    Represents an access control policy.

    Policies define fine-grained access rules with conditions,
    supporting complex authorization scenarios beyond simple RBAC.
    Policies can allow or deny access based on resources, actions,
    and contextual conditions.

    Attributes:
        id: Unique policy identifier
        name: Human-readable policy name
        description: Policy description
        effect: Policy effect (allow or deny)
        resources: List of resource patterns (supports wildcards)
        actions: List of action patterns
        conditions: List of conditions that must be satisfied
        priority: Policy priority (higher = evaluated first)
        is_active: Whether the policy is currently active
        created_at: Policy creation timestamp
        updated_at: Last update timestamp

    Example:
        >>> policy = Policy(
        ...     id="policy-123",
        ...     name="Allow developers to write their own specs",
        ...     effect=PolicyEffect.ALLOW,
        ...     resources=["specs/*"],
        ...     actions=["specs:write"],
        ...     conditions=[{"operator": "eq", "key": "role", "value": "developer"}]
        ... )
        >>> policy.matches_resource("specs/my-spec")
        True
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    effect: PolicyEffect = PolicyEffect.ALLOW
    resources: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    priority: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("resources", "actions")
    @classmethod
    def validate_patterns(cls, v: list[str]) -> list[str]:
        """
        Validate resource and action patterns.

        Ensures patterns are valid strings.

        Args:
            v: List of patterns to validate

        Returns:
            Validated patterns

        Raises:
            ValueError: If any pattern is invalid
        """
        for pattern in v:
            if not isinstance(pattern, str) or not pattern:
                raise ValueError(f"Invalid pattern '{pattern}'. Must be a non-empty string")
        return v

    def matches_resource(self, resource: str) -> bool:
        """
        Check if policy matches a specific resource.

        Supports wildcard patterns (* for any characters).

        Args:
            resource: Resource path to check

        Returns:
            True if policy resource patterns match

        Example:
            >>> policy.matches_resource("specs/my-spec")
            True
        """
        if not self.resources:
            return True

        for pattern in self.resources:
            # Simple wildcard matching
            regex_pattern = pattern.replace("*", ".*")
            import re

            if re.fullmatch(regex_pattern, resource):
                return True

        return False

    def matches_action(self, action: str) -> bool:
        """
        Check if policy matches a specific action.

        Supports wildcard patterns.

        Args:
            action: Action to check (e.g., "specs:write")

        Returns:
            True if policy action patterns match

        Example:
            >>> policy.matches_action("specs:write")
            True
        """
        if not self.actions:
            return True

        for pattern in self.actions:
            # Simple wildcard matching
            regex_pattern = pattern.replace("*", ".*")
            import re

            if re.fullmatch(regex_pattern, action):
                return True

        return False

    def evaluate_conditions(self, context: dict[str, Any]) -> bool:
        """
        Evaluate all policy conditions against context.

        All conditions must be satisfied for the policy to apply.

        Args:
            context: Context data (user, resource, environment)

        Returns:
            True if all conditions are satisfied

        Example:
            >>> policy.evaluate_conditions({"role": "developer", "team": "engineering"})
            True
        """
        if not self.conditions:
            return True

        for condition_dict in self.conditions:
            condition = PolicyCondition(**condition_dict)
            if not condition.matches(context):
                return False

        return True

    def applies_to(self, resource: str, action: str, context: dict[str, Any]) -> bool:
        """
        Check if policy applies to a specific request.

        Args:
            resource: Resource being accessed
            action: Action being performed
            context: Request context

        Returns:
            True if policy applies to the request

        Example:
            >>> policy.applies_to(
            ...     "specs/my-spec",
            ...     "specs:write",
            ...     {"role": "developer"}
            ... )
            True
        """
        if not self.is_active:
            return False

        return (
            self.matches_resource(resource)
            and self.matches_action(action)
            and self.evaluate_conditions(context)
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert policy to dictionary representation.

        Returns:
            Dictionary with policy data

        Example:
            >>> policy_dict = policy.to_dict()
            >>> policy_dict["effect"]
            'allow'
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "effect": self.effect.value,
            "resources": self.resources,
            "actions": self.actions,
            "conditions": self.conditions,
            "priority": self.priority,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        """String representation of Policy."""
        return f"<Policy(id={self.id}, name={self.name}, effect={self.effect.value})>"
