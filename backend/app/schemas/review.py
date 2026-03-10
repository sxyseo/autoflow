"""
Pydantic schemas for Review validation and serialization.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class ReviewBase(BaseModel):
    """Base schema with common review attributes."""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    title: Optional[str] = Field(None, max_length=200, description="Review title")
    comment: Optional[str] = Field(None, description="Review comment")

    @validator('comment')
    def validate_comment(cls, v, values):
        """Validate that either title or comment is provided."""
        if v is None and not values.get('title'):
            raise ValueError('Either title or comment must be provided')
        return v


class ReviewCreate(ReviewBase):
    """Schema for creating a new review."""
    reviewer_name: str = Field(..., min_length=1, max_length=100, description="Reviewer name")
    reviewer_email: Optional[str] = Field(None, max_length=255, description="Reviewer email")
    reviewer_id: Optional[str] = Field(None, max_length=100, description="External user ID")

    @validator('reviewer_email')
    def validate_email(cls, v):
        """Validate email format if provided."""
        if v and '@' not in v:
            raise ValueError('Invalid email format')
        return v


class ReviewUpdate(BaseModel):
    """Schema for updating an existing review."""
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = Field(None, max_length=200)
    comment: Optional[str] = None


class ReviewResponse(ReviewBase):
    """Schema for review response with all fields."""
    id: int
    plugin_id: int
    reviewer_name: str
    reviewer_email: Optional[str]
    reviewer_id: Optional[str]
    verified_purchase: bool
    flagged: bool
    admin_response: Optional[str]
    helpful_count: int
    not_helpful_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    """Schema for paginated review list response."""
    items: List[ReviewResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    average_rating: float


class ReviewHelpfulVote(BaseModel):
    """Schema for voting on review helpfulness."""
    helpful: bool = Field(..., description="Whether the review was helpful")


class ReviewAdminResponse(BaseModel):
    """Schema for admin response to review."""
    response: str = Field(..., min_length=1, description="Admin response text")


class ReviewAggregates(BaseModel):
    """Schema for review aggregate statistics."""
    total_reviews: int
    average_rating: float
    rating_distribution: dict  # {1: count, 2: count, 3: count, 4: count, 5: count}
    verified_purchase_count: int
    five_star_count: int
    four_star_count: int
    three_star_count: int
    two_star_count: int
    one_star_count: int
