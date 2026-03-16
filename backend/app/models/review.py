"""
Review model for plugin ratings and reviews.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


class Review(Base):
    """
    Review model for user ratings and reviews of plugins.

    Supports star ratings (1-5) and detailed text reviews.
    Used for ranking and surfacing the best plugins.
    """
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    plugin_id = Column(Integer, ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)

    # Reviewer information
    reviewer_name = Column(String(100), nullable=False)
    reviewer_email = Column(String(255))
    reviewer_id = Column(String(100), index=True)  # External user ID

    # Rating
    rating = Column(Integer, nullable=False, index=True)  # 1-5 stars

    # Review content
    title = Column(String(200))
    comment = Column(Text)

    # Moderation
    verified_purchase = Column(Boolean, default=False)  # User has installed the plugin
    flagged = Column(Boolean, default=False)
    admin_response = Column(Text)

    # Helpful votes
    helpful_count = Column(Integer, default=0)
    not_helpful_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    plugin = relationship("Plugin", back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review(id={self.id}, plugin_id={self.plugin_id}, rating={self.rating})>"
