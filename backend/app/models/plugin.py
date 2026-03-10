"""
Plugin model for plugin registry.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from app.core.database import Base


class PluginType(str, Enum):
    """Types of plugins in the marketplace."""
    SKILL = "skill"
    INTEGRATION = "integration"
    TEMPLATE = "template"


class PluginStatus(str, Enum):
    """Status of plugin in marketplace."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Plugin(Base):
    """
    Plugin model representing a marketplace plugin.

    Plugins can be skills, integrations, or templates that extend
    Autoflow's functionality.
    """
    __tablename__ = "plugins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    long_description = Column(Text)

    # Author information
    author = Column(String(100), nullable=False, index=True)
    author_email = Column(String(255))

    # Plugin metadata
    plugin_type = Column(SQLEnum(PluginType), nullable=False, index=True)
    category = Column(String(50), index=True)
    tags = Column(String(500))  # Comma-separated tags

    # Repository information
    repository_url = Column(String(500), nullable=False)
    homepage_url = Column(String(500))
    documentation_url = Column(String(500))

    # Version information
    current_version = Column(String(20), nullable=False)
    min_autoflow_version = Column(String(20))
    max_autoflow_version = Column(String(20))

    # Status and moderation
    status = Column(SQLEnum(PluginStatus), default=PluginStatus.DRAFT, index=True)
    featured = Column(Boolean, default=False, index=True)
    verified = Column(Boolean, default=False)

    # Metrics
    total_downloads = Column(Integer, default=0)
    total_installs = Column(Integer, default=0)
    average_rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    published_at = Column(DateTime)

    # Relationships
    versions = relationship("Version", back_populates="plugin", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="plugin", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="plugin", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Plugin(id={self.id}, name='{self.name}', type='{self.plugin_type}')>"
