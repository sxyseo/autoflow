"""
Pydantic schemas for Version validation and serialization.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class VersionBase(BaseModel):
    """Base schema with common version attributes."""
    version: str = Field(..., min_length=1, max_length=20, description="Version string")
    release_notes: Optional[str] = Field(None, description="Release notes")
    changelog: Optional[str] = Field(None, description="Detailed changelog")
    min_autoflow_version: Optional[str] = Field(None, max_length=20, description="Minimum compatible Autoflow version")
    max_autoflow_version: Optional[str] = Field(None, max_length=20, description="Maximum compatible Autoflow version")
    is_stable: bool = Field(True, description="Whether this is a stable release")

    @validator('version')
    def validate_version(cls, v):
        """Validate version format."""
        parts = v.split('.')
        if len(parts) < 2:
            raise ValueError('Version must have at least major.minor format (e.g., "1.0")')
        try:
            # Validate numeric parts
            major = int(parts[0].split('-')[0])  # Handle pre-release tags
            if major < 0:
                raise ValueError('Major version must be non-negative')
        except ValueError:
            raise ValueError('Version major part must be numeric')
        return v


class VersionCreate(VersionBase):
    """Schema for creating a new version."""
    download_url: Optional[str] = Field(None, max_length=500, description="Download URL")
    checksum: Optional[str] = Field(None, max_length=64, description="SHA-256 checksum")


class VersionUpdate(BaseModel):
    """Schema for updating an existing version."""
    release_notes: Optional[str] = None
    changelog: Optional[str] = None
    download_url: Optional[str] = Field(None, max_length=500)
    checksum: Optional[str] = Field(None, max_length=64)
    compatible: Optional[bool] = None
    validation_status: Optional[str] = Field(None, max_length=20)
    validation_results: Optional[str] = None


class VersionResponse(VersionBase):
    """Schema for version response with all fields."""
    id: int
    plugin_id: int
    semver: Optional[str]
    download_url: Optional[str]
    checksum: Optional[str]
    compatible: bool
    download_count: int
    install_count: int
    is_latest: bool
    validation_status: str
    validation_results: Optional[str]
    created_at: datetime
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """Schema for paginated version list response."""
    items: List[VersionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class VersionCompatibility(BaseModel):
    """Schema for version compatibility check."""
    compatible: bool
    plugin_version: str
    autoflow_version: str
    reason: Optional[str] = None
