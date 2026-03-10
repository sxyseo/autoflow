"""
Pydantic schemas for Plugin validation and serialization.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, validator
from app.models.plugin import PluginType, PluginStatus


class PluginBase(BaseModel):
    """Base schema with common plugin attributes."""
    name: str = Field(..., min_length=1, max_length=100, description="Plugin name")
    description: str = Field(..., min_length=1, max_length=500, description="Short description")
    long_description: Optional[str] = Field(None, description="Detailed description")
    author: str = Field(..., min_length=1, max_length=100, description="Author name")
    author_email: Optional[str] = Field(None, max_length=255, description="Author email")
    plugin_type: PluginType = Field(..., description="Type of plugin")
    category: Optional[str] = Field(None, max_length=50, description="Plugin category")
    tags: Optional[str] = Field(None, max_length=500, description="Comma-separated tags")
    repository_url: str = Field(..., max_length=500, description="Git repository URL")
    homepage_url: Optional[str] = Field(None, max_length=500, description="Project homepage URL")
    documentation_url: Optional[str] = Field(None, max_length=500, description="Documentation URL")
    current_version: str = Field(..., max_length=20, description="Current version")
    min_autoflow_version: Optional[str] = Field(None, max_length=20, description="Minimum Autoflow version")
    max_autoflow_version: Optional[str] = Field(None, max_length=20, description="Maximum Autoflow version")

    @validator('repository_url')
    def validate_repository_url(cls, v):
        """Validate that repository URL is a valid Git URL."""
        if not any(v.startswith(prefix) for prefix in ['http://', 'https://', 'git@']):
            raise ValueError('Repository URL must be a valid HTTP or Git URL')
        return v

    @validator('name')
    def validate_name(cls, v):
        """Validate plugin name format."""
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Plugin name must contain only alphanumeric characters, hyphens, and underscores')
        return v.lower()


class PluginCreate(PluginBase):
    """Schema for creating a new plugin."""
    pass


class PluginUpdate(BaseModel):
    """Schema for updating an existing plugin."""
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    long_description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    tags: Optional[str] = Field(None, max_length=500)
    homepage_url: Optional[str] = Field(None, max_length=500)
    documentation_url: Optional[str] = Field(None, max_length=500)
    current_version: Optional[str] = Field(None, max_length=20)
    min_autoflow_version: Optional[str] = Field(None, max_length=20)
    max_autoflow_version: Optional[str] = Field(None, max_length=20)


class PluginResponse(PluginBase):
    """Schema for plugin response with all fields."""
    id: int
    slug: str
    status: PluginStatus
    featured: bool
    verified: bool
    total_downloads: int
    total_installs: int
    average_rating: float
    rating_count: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class PluginListResponse(BaseModel):
    """Schema for paginated plugin list response."""
    items: List[PluginResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PluginSearchQuery(BaseModel):
    """Schema for plugin search query parameters."""
    search: Optional[str] = Field(None, description="Search term for name/description")
    plugin_type: Optional[PluginType] = Field(None, description="Filter by plugin type")
    category: Optional[str] = Field(None, description="Filter by category")
    tags: Optional[str] = Field(None, description="Filter by tags (comma-separated)")
    author: Optional[str] = Field(None, description="Filter by author")
    status: Optional[PluginStatus] = Field(None, description="Filter by status")
    featured: Optional[bool] = Field(None, description="Filter featured plugins")
    verified: Optional[bool] = Field(None, description="Filter verified plugins")
    min_rating: Optional[float] = Field(None, ge=0, le=5, description="Minimum average rating")
    sort_by: Optional[str] = Field("created_at", description="Sort field")
    sort_order: Optional[str] = Field("desc", description="Sort order (asc/desc)")
    page: Optional[int] = Field(1, ge=1, description="Page number")
    page_size: Optional[int] = Field(20, ge=1, le=100, description="Items per page")


class PluginStats(BaseModel):
    """Schema for plugin statistics."""
    total_plugins: int
    total_downloads: int
    total_installs: int
    by_type: dict
    by_category: dict
    top_rated: List[PluginResponse]
    most_downloaded: List[PluginResponse]
