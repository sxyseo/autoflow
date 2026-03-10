"""
Plugin repository for database CRUD operations.
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.plugin import Plugin, PluginType, PluginStatus
from app.schemas.plugin import PluginCreate, PluginUpdate, PluginSearchQuery
import re


class PluginRepository:
    """
    Repository for plugin database operations.

    Provides CRUD operations, search, filtering, and pagination
    for plugin management.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            db: Async database session
        """
        self.db = db

    async def create(self, plugin_data: PluginCreate) -> Plugin:
        """
        Create a new plugin.

        Args:
            plugin_data: Plugin creation data

        Returns:
            Created plugin instance

        Raises:
            IntegrityError: If plugin with same name/slug exists
        """
        # Generate slug from name
        slug = self._generate_slug(plugin_data.name)

        plugin = Plugin(
            name=plugin_data.name,
            slug=slug,
            description=plugin_data.description,
            long_description=plugin_data.long_description,
            author=plugin_data.author,
            author_email=plugin_data.author_email,
            plugin_type=plugin_data.plugin_type,
            category=plugin_data.category,
            tags=plugin_data.tags,
            repository_url=plugin_data.repository_url,
            homepage_url=plugin_data.homepage_url,
            documentation_url=plugin_data.documentation_url,
            current_version=plugin_data.current_version,
            min_autoflow_version=plugin_data.min_autoflow_version,
            max_autoflow_version=plugin_data.max_autoflow_version,
            status=PluginStatus.DRAFT,
        )

        self.db.add(plugin)
        await self.db.commit()
        await self.db.refresh(plugin)

        return plugin

    async def get_by_id(self, plugin_id: int) -> Optional[Plugin]:
        """
        Get plugin by ID.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin instance or None if not found
        """
        result = await self.db.execute(
            select(Plugin)
            .options(selectinload(Plugin.versions))
            .options(selectinload(Plugin.reviews))
            .where(Plugin.id == plugin_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Plugin]:
        """
        Get plugin by slug.

        Args:
            slug: Plugin slug

        Returns:
            Plugin instance or None if not found
        """
        result = await self.db.execute(
            select(Plugin)
            .options(selectinload(Plugin.versions))
            .options(selectinload(Plugin.reviews))
            .where(Plugin.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Plugin]:
        """
        Get plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        result = await self.db.execute(
            select(Plugin).where(Plugin.name == name)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[PluginStatus] = None,
    ) -> List[Plugin]:
        """
        List plugins with optional status filter and pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            status: Optional status filter

        Returns:
            List of plugins
        """
        query = select(Plugin).order_by(Plugin.created_at.desc())

        if status:
            query = query.where(Plugin.status == status)

        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        plugin_id: int,
        plugin_data: PluginUpdate
    ) -> Optional[Plugin]:
        """
        Update an existing plugin.

        Args:
            plugin_id: Plugin ID
            plugin_data: Plugin update data

        Returns:
            Updated plugin instance or None if not found
        """
        plugin = await self.get_by_id(plugin_id)

        if not plugin:
            return None

        # Update fields that are provided
        update_data = plugin_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(plugin, field):
                setattr(plugin, field, value)

        await self.db.commit()
        await self.db.refresh(plugin)

        return plugin

    async def delete(self, plugin_id: int) -> bool:
        """
        Delete a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if deleted, False if not found
        """
        plugin = await self.get_by_id(plugin_id)

        if not plugin:
            return False

        await self.db.delete(plugin)
        await self.db.commit()

        return True

    async def search(
        self,
        query_params: PluginSearchQuery
    ) -> tuple[List[Plugin], int]:
        """
        Search plugins with filtering and pagination.

        Args:
            query_params: Search and filter parameters

        Returns:
            Tuple of (list of plugins, total count)
        """
        # Build base query
        base_query = select(Plugin)

        # Build count query
        count_query = select(func.count()).select_from(Plugin)

        # Apply filters
        filters = []

        # Text search (name and description)
        if query_params.search:
            search_term = f"%{query_params.search}%"
            filters.append(
                or_(
                    Plugin.name.ilike(search_term),
                    Plugin.description.ilike(search_term),
                    Plugin.tags.ilike(search_term)
                )
            )

        # Plugin type filter
        if query_params.plugin_type:
            filters.append(Plugin.plugin_type == query_params.plugin_type)

        # Category filter
        if query_params.category:
            filters.append(Plugin.category == query_params.category)

        # Tags filter
        if query_params.tags:
            tag_list = [tag.strip() for tag in query_params.tags.split(',')]
            for tag in tag_list:
                filters.append(Plugin.tags.like(f"%{tag}%"))

        # Author filter
        if query_params.author:
            filters.append(Plugin.author.ilike(f"%{query_params.author}%"))

        # Status filter
        if query_params.status:
            filters.append(Plugin.status == query_params.status)

        # Featured filter
        if query_params.featured is not None:
            filters.append(Plugin.featured == query_params.featured)

        # Verified filter
        if query_params.verified is not None:
            filters.append(Plugin.verified == query_params.verified)

        # Minimum rating filter
        if query_params.min_rating is not None:
            filters.append(Plugin.average_rating >= query_params.min_rating)

        # Apply all filters
        if filters:
            base_query = base_query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply sorting
        sort_column = getattr(Plugin, query_params.sort_by, Plugin.created_at)

        if query_params.sort_order == "asc":
            base_query = base_query.order_by(sort_column.asc())
        else:
            base_query = base_query.order_by(sort_column.desc())

        # Apply pagination
        offset = (query_params.page - 1) * query_params.page_size
        base_query = base_query.offset(offset).limit(query_params.page_size)

        # Execute query
        result = await self.db.execute(base_query)
        plugins = list(result.scalars().all())

        return plugins, total

    async def get_featured(
        self,
        limit: int = 10
    ) -> List[Plugin]:
        """
        Get featured plugins.

        Args:
            limit: Maximum number of plugins to return

        Returns:
            List of featured plugins sorted by downloads
        """
        result = await self.db.execute(
            select(Plugin)
            .where(Plugin.featured == True)
            .where(Plugin.status == PluginStatus.APPROVED)
            .order_by(Plugin.total_downloads.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_top_rated(
        self,
        limit: int = 10
    ) -> List[Plugin]:
        """
        Get top rated plugins.

        Args:
            limit: Maximum number of plugins to return

        Returns:
            List of top rated plugins
        """
        result = await self.db.execute(
            select(Plugin)
            .where(Plugin.status == PluginStatus.APPROVED)
            .where(Plugin.rating_count >= 5)  # Minimum 5 reviews
            .order_by(Plugin.average_rating.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_most_downloaded(
        self,
        limit: int = 10
    ) -> List[Plugin]:
        """
        Get most downloaded plugins.

        Args:
            limit: Maximum number of plugins to return

        Returns:
            List of most downloaded plugins
        """
        result = await self.db.execute(
            select(Plugin)
            .where(Plugin.status == PluginStatus.APPROVED)
            .order_by(Plugin.total_downloads.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_downloads(self, plugin_id: int) -> bool:
        """
        Increment download count for a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if updated, False if not found
        """
        plugin = await self.get_by_id(plugin_id)

        if not plugin:
            return False

        plugin.total_downloads += 1
        await self.db.commit()

        return True

    async def increment_installs(self, plugin_id: int) -> bool:
        """
        Increment install count for a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if updated, False if not found
        """
        plugin = await self.get_by_id(plugin_id)

        if not plugin:
            return False

        plugin.total_installs += 1
        await self.db.commit()

        return True

    async def update_rating(
        self,
        plugin_id: int,
        new_rating: int
    ) -> bool:
        """
        Update plugin average rating.

        Args:
            plugin_id: Plugin ID
            new_rating: New rating value (1-5)

        Returns:
            True if updated, False if not found
        """
        plugin = await self.get_by_id(plugin_id)

        if not plugin:
            return False

        # Recalculate average rating
        total_rating = plugin.average_rating * plugin.rating_count
        plugin.rating_count += 1
        plugin.average_rating = (total_rating + new_rating) / plugin.rating_count

        await self.db.commit()

        return True

    async def set_status(
        self,
        plugin_id: int,
        status: PluginStatus
    ) -> Optional[Plugin]:
        """
        Update plugin status.

        Args:
            plugin_id: Plugin ID
            status: New status

        Returns:
            Updated plugin or None if not found
        """
        plugin = await self.get_by_id(plugin_id)

        if not plugin:
            return None

        plugin.status = status

        # Set published_at timestamp when approving
        if status == PluginStatus.APPROVED and not plugin.published_at:
            from datetime import datetime
            plugin.published_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(plugin)

        return plugin

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get plugin marketplace statistics.

        Returns:
            Dictionary containing various statistics
        """
        # Total plugins
        total_result = await self.db.execute(
            select(func.count()).select_from(Plugin)
        )
        total_plugins = total_result.scalar()

        # Total downloads
        downloads_result = await self.db.execute(
            select(func.sum(Plugin.total_downloads)).select_from(Plugin)
        )
        total_downloads = downloads_result.scalar() or 0

        # Total installs
        installs_result = await self.db.execute(
            select(func.sum(Plugin.total_installs)).select_from(Plugin)
        )
        total_installs = installs_result.scalar() or 0

        # By type
        type_result = await self.db.execute(
            select(Plugin.plugin_type, func.count())
            .group_by(Plugin.plugin_type)
        )
        by_type = {plugin_type: count for plugin_type, count in type_result.all()}

        # By category
        category_result = await self.db.execute(
            select(Plugin.category, func.count())
            .where(Plugin.category.isnot(None))
            .group_by(Plugin.category)
        )
        by_category = {category: count for category, count in category_result.all()}

        return {
            "total_plugins": total_plugins,
            "total_downloads": total_downloads,
            "total_installs": total_installs,
            "by_type": by_type,
            "by_category": by_category,
        }

    @staticmethod
    def _generate_slug(name: str) -> str:
        """
        Generate URL-friendly slug from plugin name.

        Args:
            name: Plugin name

        Returns:
            URL-friendly slug
        """
        # Convert to lowercase and replace spaces with hyphens
        slug = name.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug
