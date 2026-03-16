"""
Autoflow Node Communication Server

Provides async HTTP server for node-to-node communication in distributed
agent coordination. Handles node registration, heartbeats, work assignment,
and status queries for the cluster.

Usage:
    from autoflow.coordination.server import create_node_server
    from autoflow.coordination.registry import NodeRegistry

    # Create a registry and server
    registry = NodeRegistry()
    server = create_node_server(
        node_id="node-001",
        host="localhost",
        port=8080,
        registry=registry
    )

    # Start the server
    await server.start()

    # Or use as context manager
    async with await server.start():
        # Server is running
        pass
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Optional

from aiohttp import web
from pydantic import ValidationError

from autoflow.coordination.node import Node, NodeStatus
from autoflow.coordination.registry import NodeRegistry
from autoflow.coordination.work_queue import WorkItem, WorkItemStatus


class NodeServer:
    """
    HTTP server for node-to-node communication.

    Provides REST API endpoints for cluster coordination including
    node registration, heartbeat, work assignment, and status queries.

    The server integrates with a NodeRegistry to maintain cluster state
    and handles incoming requests from other nodes in the cluster.

    Attributes:
        node_id: This node's ID
        host: Host to bind to
        port: Port to listen on
        registry: NodeRegistry instance for cluster state

    Example:
        >>> registry = NodeRegistry()
        >>> server = NodeServer(
        ...     node_id="node-001",
        ...     host="0.0.0.0",
        ...     port=8080,
        ...     registry=registry
        ... )
        >>> await server.start()
    """

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        registry: NodeRegistry,
    ) -> None:
        """
        Initialize the NodeServer.

        Args:
            node_id: This node's unique ID
            host: Host to bind the server to
            port: Port to listen on
            registry: NodeRegistry instance for managing cluster state

        Example:
            >>> server = NodeServer(
            ...     node_id="node-001",
            ...     host="localhost",
            ...     port=8080,
            ...     registry=NodeRegistry()
            ... )
        """
        self._node_id = node_id
        self._host = host
        self._port = port
        self._registry = registry
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._work_items: dict[str, WorkItem] = {}

    def _setup_routes(self) -> web.RouteTableDef:
        """
        Set up the HTTP routes for the server.

        Returns:
            Route table with all endpoints registered
        """
        routes = web.RouteTableDef()

        # Node registration and discovery
        routes.post("/api/v1/nodes/register")(self._register_node)
        routes.post("/api/v1/nodes/{node_id}/heartbeat")(self._heartbeat)
        routes.get("/api/v1/nodes")(self._list_nodes)
        routes.get("/api/v1/status")(self._get_status)

        # Work management
        routes.post("/api/v1/work/assign")(self._assign_work)
        routes.get("/api/v1/work/{work_id}/status")(self._get_work_status)
        routes.post("/api/v1/work/{work_id}/status")(self._update_work_status)

        # Health check
        routes.get("/api/v1/ping")(self._ping)

        return routes

    async def _register_node(self, request: web.Request) -> web.Response:
        """
        Handle node registration requests.

        Registers a new node with the cluster. If the node already
        exists, updates its information.

        Args:
            request: HTTP request with node registration data

        Returns:
            JSON response with registered node info
        """
        try:
            data = await request.json()

            node_id = data.get("node_id")
            address = data.get("address")
            capabilities = data.get("capabilities", [])
            metadata = data.get("metadata", {})

            if not node_id or not address:
                return web.json_response(
                    {"error": "Missing required fields: node_id, address"},
                    status=400,
                )

            # Create or update node
            node = Node(
                id=node_id,
                address=address,
                capabilities=capabilities,
                status=NodeStatus.ONLINE,
                metadata=metadata,
            )

            self._registry.register(node)
            self._registry.update_heartbeat(node_id)

            return web.json_response({
                "node": node.model_dump(),
                "message": "Node registered successfully",
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Registration failed: {str(e)}"},
                status=500,
            )

    async def _heartbeat(self, request: web.Request) -> web.Response:
        """
        Handle heartbeat requests from nodes.

        Updates the last_seen timestamp for a node, indicating
        it is still online and healthy.

        Args:
            request: HTTP request with node_id in URL

        Returns:
            JSON response acknowledging the heartbeat
        """
        try:
            node_id = request.match_info["node_id"]

            # Update heartbeat in registry
            node = self._registry.lookup(node_id)
            if not node:
                return web.json_response(
                    {"error": "Node not found"},
                    status=404,
                )

            self._registry.update_heartbeat(node_id)

            return web.json_response({
                "node_id": node_id,
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Heartbeat failed: {str(e)}"},
                status=500,
            )

    async def _list_nodes(self, request: web.Request) -> web.Response:
        """
        Handle node discovery/listing requests.

        Returns a list of all known nodes in the cluster.

        Args:
            request: HTTP request

        Returns:
            JSON response with list of nodes
        """
        try:
            nodes = self._registry.list_nodes()

            return web.json_response({
                "nodes": [node.model_dump() for node in nodes],
                "count": len(nodes),
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Failed to list nodes: {str(e)}"},
                status=500,
            )

    async def _get_status(self, request: web.Request) -> web.Response:
        """
        Handle status requests for this node.

        Returns information about this node's current status,
        capabilities, and health.

        Args:
            request: HTTP request

        Returns:
            JSON response with node status
        """
        try:
            # Get this node from registry
            node = self._registry.lookup(self._node_id)

            if not node:
                # Return basic info if not yet registered
                return web.json_response({
                    "node_id": self._node_id,
                    "status": "starting",
                    "capabilities": [],
                    "last_seen": datetime.utcnow().isoformat(),
                })

            return web.json_response({
                "node_id": self._node_id,
                "status": node.status.value,
                "capabilities": node.capabilities,
                "last_seen": node.last_seen.isoformat(),
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Failed to get status: {str(e)}"},
                status=500,
            )

    async def _assign_work(self, request: web.Request) -> web.Response:
        """
        Handle work assignment requests.

        Accepts a new work item and assigns it to this node for execution.

        Args:
            request: HTTP request with work assignment data

        Returns:
            JSON response with assigned work item info
        """
        try:
            data = await request.json()

            work_id = data.get("work_id")
            task = data.get("task")
            priority = data.get("priority", 5)
            metadata = data.get("metadata", {})

            if not work_id or not task:
                return web.json_response(
                    {"error": "Missing required fields: work_id, task"},
                    status=400,
                )

            # Create work item
            work = WorkItem(
                id=work_id,
                task=task,
                priority=priority,
                metadata=metadata,
            )

            # Assign to this node
            work.assign_to(self._node_id)

            # Store work item
            self._work_items[work_id] = work

            return web.json_response({
                "work": work.model_dump(),
                "message": "Work assigned successfully",
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Work assignment failed: {str(e)}"},
                status=500,
            )

    async def _get_work_status(self, request: web.Request) -> web.Response:
        """
        Handle work status queries.

        Returns the current status of a work item assigned to this node.

        Args:
            request: HTTP request with work_id in URL

        Returns:
            JSON response with work status
        """
        try:
            work_id = request.match_info["work_id"]

            work = self._work_items.get(work_id)
            if not work:
                return web.json_response(
                    {"error": "Work item not found"},
                    status=404,
                )

            return web.json_response({
                "work_id": work.id,
                "task": work.task,
                "status": work.status.value,
                "assigned_node": work.assigned_node,
                "priority": work.priority,
                "created_at": work.created_at.isoformat(),
                "started_at": work.started_at.isoformat() if work.started_at else None,
                "completed_at": work.completed_at.isoformat() if work.completed_at else None,
                "error": work.error,
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Failed to get work status: {str(e)}"},
                status=500,
            )

    async def _update_work_status(self, request: web.Request) -> web.Response:
        """
        Handle work status update requests.

        Updates the status of a work item (e.g., to mark it as
        started, completed, or failed).

        Args:
            request: HTTP request with work_id in URL and status data

        Returns:
            JSON response acknowledging the update
        """
        try:
            work_id = request.match_info["work_id"]
            data = await request.json()

            work = self._work_items.get(work_id)
            if not work:
                return web.json_response(
                    {"error": "Work item not found"},
                    status=404,
                )

            status_str = data.get("status")
            error = data.get("error")

            if not status_str:
                return web.json_response(
                    {"error": "Missing required field: status"},
                    status=400,
                )

            # Update work status
            try:
                status = WorkItemStatus(status_str)

                if status == WorkItemStatus.RUNNING:
                    work.start()
                elif status in (WorkItemStatus.COMPLETED, WorkItemStatus.FAILED):
                    if status == WorkItemStatus.FAILED and error:
                        work.fail(error)
                    else:
                        work.complete(status=status)
                elif status == WorkItemStatus.CANCELLED:
                    work.complete(status=WorkItemStatus.CANCELLED)

            except ValueError:
                return web.json_response(
                    {"error": f"Invalid status: {status_str}"},
                    status=400,
                )

            return web.json_response({
                "work_id": work_id,
                "status": work.status.value,
                "message": "Work status updated successfully",
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Failed to update work status: {str(e)}"},
                status=500,
            )

    async def _ping(self, request: web.Request) -> web.Response:
        """
        Handle ping requests for health checks.

        Returns a simple pong response to indicate the node is running.

        Args:
            request: HTTP request

        Returns:
            JSON response with pong
        """
        return web.json_response({
            "status": "pong",
            "node_id": self._node_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def start(self) -> NodeServer:
        """
        Start the HTTP server.

        Creates and starts the aiohttp server with all routes configured.

        Returns:
            Self for chaining or context manager usage

        Example:
            >>> server = NodeServer(...)
            >>> await server.start()
            >>> # Server is now running
        """
        self._app = web.Application()
        routes = self._setup_routes()
        routes.register(self._app.router)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        return self

    async def stop(self) -> None:
        """
        Stop the HTTP server.

        Cleans up the server and releases resources.

        Example:
            >>> await server.stop()
        """
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            self._app = None

    async def __aenter__(self) -> NodeServer:
        """Enter async context manager and start server."""
        return await self.start()

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager and stop server."""
        await self.stop()

    @property
    def url(self) -> str:
        """
        Get the base URL for this server.

        Returns:
            URL string (e.g., "http://localhost:8080")
        """
        return f"http://{self._host}:{self._port}"

    @property
    def is_running(self) -> bool:
        """
        Check if the server is currently running.

        Returns:
            True if server is running, False otherwise
        """
        return self._site is not None

    def __repr__(self) -> str:
        """Return string representation of the server."""
        return (
            f"NodeServer("
            f"node_id={self._node_id!r}, "
            f"host={self._host!r}, "
            f"port={self._port}, "
            f"running={self.is_running})"
        )


def create_node_server(
    node_id: str,
    host: str = "localhost",
    port: int = 8080,
    registry: Optional[NodeRegistry] = None,
) -> NodeServer:
    """
    Create a node server for cluster communication.

    Convenience function to create and configure a NodeServer instance.
    If no registry is provided, creates a new one.

    Args:
        node_id: Unique ID for this node
        host: Host to bind to (defaults to "localhost")
        port: Port to listen on (defaults to 8080)
        registry: Optional NodeRegistry instance (creates new if None)

    Returns:
        Configured NodeServer instance

    Example:
        >>> server = create_node_server(
        ...     node_id="node-001",
        ...     host="0.0.0.0",
        ...     port=8080
        ... )
        >>> await server.start()
    """
    if registry is None:
        registry = NodeRegistry()

    # Register this node in the registry
    node = Node(
        id=node_id,
        address=f"{host}:{port}",
        status=NodeStatus.ONLINE,
    )
    registry.register(node)

    return NodeServer(
        node_id=node_id,
        host=host,
        port=port,
        registry=registry,
    )
