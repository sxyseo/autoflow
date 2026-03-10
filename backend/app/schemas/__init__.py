"""
Pydantic schemas for plugin marketplace.
"""
from app.schemas.plugin import (
    PluginBase,
    PluginCreate,
    PluginUpdate,
    PluginResponse,
    PluginListResponse,
    PluginSearchQuery,
    PluginStats,
)
from app.schemas.version import (
    VersionBase,
    VersionCreate,
    VersionUpdate,
    VersionResponse,
    VersionListResponse,
    VersionCompatibility,
)
from app.schemas.review import (
    ReviewBase,
    ReviewCreate,
    ReviewUpdate,
    ReviewResponse,
    ReviewListResponse,
    ReviewHelpfulVote,
    ReviewAdminResponse,
    ReviewAggregates,
)

__all__ = [
    # Plugin schemas
    "PluginBase",
    "PluginCreate",
    "PluginUpdate",
    "PluginResponse",
    "PluginListResponse",
    "PluginSearchQuery",
    "PluginStats",
    # Version schemas
    "VersionBase",
    "VersionCreate",
    "VersionUpdate",
    "VersionResponse",
    "VersionListResponse",
    "VersionCompatibility",
    # Review schemas
    "ReviewBase",
    "ReviewCreate",
    "ReviewUpdate",
    "ReviewResponse",
    "ReviewListResponse",
    "ReviewHelpfulVote",
    "ReviewAdminResponse",
    "ReviewAggregates",
]
