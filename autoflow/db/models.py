"""
Autoflow Database Models

Defines SQLAlchemy ORM models for users, roles, and permissions.
Supports enterprise SSO integration and role-based access control (RBAC).

Usage:
    from autoflow.db.models import User, Role, Permission, Base

    # Create a new user
    user = User(
        email="user@example.com",
        name="John Doe",
        sso_provider="saml"
    )

    # Query users with a specific role
    admins = session.query(User).join(User.roles).filter(Role.name == "admin").all()
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Many-to-many association tables
user_role_association = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", String, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permission_association = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", String, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", String, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class SSOProvider(str, Enum):
    """Supported SSO providers."""

    NONE = "none"
    SAML = "saml"
    OIDC = "oidc"
    LDAP = "ldap"


class UserStatus(str, Enum):
    """Status of a user account."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class User(Base):
    """
    Represents a user in the system.

    Supports both local authentication and SSO integration via SAML, OIDC, or LDAP.
    Users can have multiple roles for RBAC and are associated with an organization.

    Attributes:
        id: Unique user identifier (UUID)
        email: User's email address (unique)
        name: User's full display name
        sso_provider: SSO provider used for authentication
        sso_id: External ID from SSO provider
        status: Current account status
        is_superuser: Admin bypass for RBAC
        created_at: Account creation timestamp
        updated_at: Last update timestamp
        last_login: Most recent successful login
        roles: List of roles assigned to this user

    Example:
        >>> user = User(
        ...     email="admin@example.com",
        ...     name="System Administrator",
        ...     is_superuser=True
        ... )
        >>> session.add(user)
        >>> session.commit()
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # User information
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))

    # SSO integration fields
    sso_provider: Mapped[SSOProvider] = mapped_column(
        SQLEnum(SSOProvider),
        default=SSOProvider.NONE,
        nullable=False,
    )
    sso_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Account status and permissions
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus),
        default=UserStatus.PENDING,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=user_role_association,
        back_populates="users",
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("ix_users_sso_provider_sso_id", "sso_provider", "sso_id"),
        Index("ix_users_status", "status"),
    )

    def has_permission(self, session: Session, permission_name: str) -> bool:
        """
        Check if user has a specific permission via their roles.

        Args:
            session: Database session for querying
            permission_name: Name of the permission to check

        Returns:
            True if user has the permission, False otherwise

        Example:
            >>> if user.has_permission(session, "specs:write"):
            ...     print("User can write specs")
        """
        if self.is_superuser:
            return True

        if self.status != UserStatus.ACTIVE:
            return False

        # Query permissions through roles
        from sqlalchemy import select

        stmt = (
            select(Permission)
            .join(Role.permissions)
            .join(Role, Role.users)
            .where(User.id == self.id)
            .where(Permission.name == permission_name)
        )

        result = session.execute(stmt).first()
        return result is not None

    def add_role(self, session: Session, role_name: str) -> None:
        """
        Add a role to this user.

        Args:
            session: Database session
            role_name: Name of the role to add

        Raises:
            ValueError: If role doesn't exist

        Example:
            >>> user.add_role(session, "developer")
            >>> session.commit()
        """
        role = session.query(Role).filter(Role.name == role_name).first()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        if role not in self.roles:
            self.roles.append(role)
            self.touch()

    def remove_role(self, session: Session, role_name: str) -> None:
        """
        Remove a role from this user.

        Args:
            session: Database session
            role_name: Name of the role to remove

        Example:
            >>> user.remove_role(session, "viewer")
            >>> session.commit()
        """
        role = session.query(Role).filter(Role.name == role_name).first()
        if role and role in self.roles:
            self.roles.remove(role)
            self.touch()

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, email={self.email}, status={self.status.value})>"


class Role(Base):
    """
    Represents a role in the RBAC system.

    Roles are collections of permissions that can be assigned to users.
    Common roles include: admin, developer, viewer, auditor.

    Attributes:
        id: Unique role identifier (UUID)
        name: Unique role name (e.g., "admin", "developer")
        description: Human-readable role description
        is_system: System roles cannot be deleted
        created_at: Role creation timestamp
        updated_at: Last update timestamp
        users: List of users with this role
        permissions: List of permissions granted by this role

    Example:
        >>> role = Role(
        ...     name="developer",
        ...     description="Can create and modify specs and tasks"
        ... )
        >>> session.add(role)
        >>> session.commit()
    """

    __tablename__ = "roles"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Role information
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # System roles are protected from deletion
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    users: Mapped[list[User]] = relationship(
        "User",
        secondary=user_role_association,
        back_populates="roles",
        lazy="selectin",
    )
    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary=role_permission_association,
        back_populates="roles",
        lazy="selectin",
    )

    def grant_permission(self, session: Session, permission_name: str) -> None:
        """
        Grant a permission to this role.

        Args:
            session: Database session
            permission_name: Name of the permission to grant

        Raises:
            ValueError: If permission doesn't exist

        Example:
            >>> role.grant_permission(session, "specs:write")
            >>> session.commit()
        """
        permission = session.query(Permission).filter(
            Permission.name == permission_name
        ).first()
        if not permission:
            raise ValueError(f"Permission '{permission_name}' not found")

        if permission not in self.permissions:
            self.permissions.append(permission)
            self.touch()

    def revoke_permission(self, session: Session, permission_name: str) -> None:
        """
        Revoke a permission from this role.

        Args:
            session: Database session
            permission_name: Name of the permission to revoke

        Example:
            >>> role.revoke_permission(session, "runs:delete")
            >>> session.commit()
        """
        permission = session.query(Permission).filter(
            Permission.name == permission_name
        ).first()
        if permission and permission in self.permissions:
            self.permissions.remove(permission)
            self.touch()

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()

    def __repr__(self) -> str:
        """String representation of Role."""
        return f"<Role(id={self.id}, name={self.name})>"


class Permission(Base):
    """
    Represents a permission in the RBAC system.

    Permissions define specific actions that can be performed on resources.
    Format: "resource:action" (e.g., "specs:read", "tasks:write", "runs:delete").

    Attributes:
        id: Unique permission identifier (UUID)
        name: Unique permission name in "resource:action" format
        description: Human-readable permission description
        resource: Resource type (e.g., "specs", "tasks", "runs")
        action: Action type (e.g., "read", "write", "delete", "admin")
        created_at: Permission creation timestamp

    Example:
        >>> permission = Permission(
        ...     name="specs:write",
        ...     description="Can create and modify specifications"
        ... )
        >>> session.add(permission)
        >>> session.commit()
    """

    __tablename__ = "permissions"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Permission information
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resource: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=role_permission_association,
        back_populates="permissions",
        lazy="selectin",
    )

    def __init__(self, **kwargs):
        """
        Initialize a Permission.

        Automatically extracts resource and action from name if not provided.

        Args:
            **kwargs: Field values for the permission

        Example:
            >>> perm = Permission(name="specs:write")
            >>> assert perm.resource == "specs"
            >>> assert perm.action == "write"
        """
        super().__init__(**kwargs)
        # Auto-extract resource and action from name if not provided
        if self.name and ":" in self.name:
            if not kwargs.get("resource"):
                self.resource = self.name.split(":")[0]
            if not kwargs.get("action"):
                self.action = self.name.split(":")[1]

    def __repr__(self) -> str:
        """String representation of Permission."""
        return f"<Permission(id={self.id}, name={self.name})>"
