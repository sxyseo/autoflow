"""
Version model for plugin version management.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


class Version(Base):
    """
    Version model for tracking plugin versions.

    Supports semantic versioning and tracks download counts,
    compatibility, and release notes for each version.
    """
    __tablename__ = "versions"

    id = Column(Integer, primary_key=True, index=True)
    plugin_id = Column(Integer, ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)

    # Version information
    version = Column(String(20), nullable=False, index=True)
    semver = Column(String(50))  # Full semver string (e.g., "1.2.3-beta.1")

    # Release metadata
    release_notes = Column(Text)
    changelog = Column(Text)
    download_url = Column(String(500))
    checksum = Column(String(64))  # SHA-256 checksum

    # Compatibility
    min_autoflow_version = Column(String(20))
    max_autoflow_version = Column(String(20))
    compatible = Column(Boolean, default=True)

    # Metrics
    download_count = Column(Integer, default=0)
    install_count = Column(Integer, default=0)

    # Status
    is_latest = Column(Boolean, default=False, index=True)
    is_stable = Column(Boolean, default=True)

    # Validation status
    validation_status = Column(String(20), default="pending")  # pending, passed, failed
    validation_results = Column(Text)  # JSON string of validation results

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime)

    # Relationship
    plugin = relationship("Plugin", back_populates="versions")

    def __repr__(self) -> str:
        return f"<Version(id={self.id}, plugin_id={self.plugin_id}, version='{self.version}')>"
