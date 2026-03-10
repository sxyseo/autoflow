"""
Metric model for tracking plugin usage and health metrics.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


class Metric(Base):
    """
    Metric model for tracking plugin usage and health.

    Tracks downloads, installs, errors, and other metrics to
    monitor plugin health and popularity.
    """
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    plugin_id = Column(Integer, ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)

    # Metric type and value
    metric_type = Column(String(50), nullable=False, index=True)  # download, install, error, etc.
    metric_value = Column(Float, default=1.0)

    # Additional metadata
    additional_metadata = Column(Text)  # JSON string for additional context

    # Timestamps
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    plugin = relationship("Plugin", back_populates="metrics")

    def __repr__(self) -> str:
        return f"<Metric(id={self.id}, plugin_id={self.plugin_id}, type='{self.metric_type}')>"

    # Define composite indexes for common queries
    __table_args__ = (
        Index('ix_metrics_plugin_type_date', 'plugin_id', 'metric_type', 'recorded_at'),
    )
