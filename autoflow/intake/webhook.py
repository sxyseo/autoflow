"""
Autoflow Intake Webhook Module

Provides FastAPI-based webhook server for receiving issue events from
external sources like GitHub, GitLab, and Linear. Handles event parsing,
signature verification, and routing to appropriate handlers.

Usage:
    from autoflow.intake.webhook import WebhookServer, WebhookConfig

    config = WebhookConfig(host="0.0.0.0", port=8080)
    server = WebhookServer(config=config)
    await server.start()
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class WebhookSourceType(str, Enum):
    """
    Supported webhook source types.

    - GITHUB: GitHub webhooks
    - GITLAB: GitLab webhooks
    - LINEAR: Linear webhooks
    """

    GITHUB = "github"
    GITLAB = "gitlab"
    LINEAR = "linear"


class WebhookEventType(str, Enum):
    """Types of webhook events."""

    # Issue events
    ISSUES_OPENED = "issues_opened"
    ISSUES_CLOSED = "issues_closed"
    ISSUES_REOPENED = "issues_reopened"
    ISSUES_EDITED = "issues_edited"
    ISSUES_ASSIGNED = "issues_assigned"
    ISSUES_LABELED = "issues_labeled"
    ISSUES_UNLABELED = "issues_unlabeled"

    # Comment events
    ISSUE_COMMENT_CREATED = "issue_comment_created"
    ISSUE_COMMENT_EDITED = "issue_comment_edited"
    ISSUE_COMMENT_DELETED = "issue_comment_deleted"

    # PR/MR events
    PULL_REQUEST_OPENED = "pull_request_opened"
    PULL_REQUEST_CLOSED = "pull_request_closed"
    PULL_REQUEST_MERGED = "pull_request_merged"
    PULL_REQUEST_REVIEWED = "pull_request_reviewed"

    # Unknown/ping events
    PING = "ping"
    UNKNOWN = "unknown"


class WebhookEvent(BaseModel):
    """
    Represents a normalized webhook event.

    Attributes:
        id: Unique event identifier
        source_type: Type of source (github, gitlab, linear)
        event_type: Type of event (issue opened, closed, etc.)
        source_id: Issue/PR identifier from source
        source_url: URL to the issue/PR in source
        action: Action that occurred (opened, closed, edited, etc.)
        payload: Raw webhook payload
        headers: HTTP headers from webhook request
        signature: Webhook signature (if verified)
        received_at: When the webhook was received
        processed_at: When the webhook was processed
        metadata: Additional event metadata
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_type: WebhookSourceType
    event_type: WebhookEventType
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    action: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    signature: Optional[str] = None
    received_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_processed(self) -> None:
        """Mark the event as processed."""
        self.processed_at = datetime.utcnow()


class WebhookConfig(BaseModel):
    """
    Configuration for the webhook server.

    Attributes:
        host: Host to bind the server to
        port: Port to listen on
        path: Webhook endpoint path (e.g., "/webhook")
        verify_signatures: Whether to verify webhook signatures
        allowed_sources: List of allowed source types
        secret: Default webhook secret (can be overridden per source)
        sources: Per-source configuration
        max_payload_size: Maximum webhook payload size in bytes
        timeout_seconds: Request timeout in seconds
        metadata: Additional configuration metadata
    """

    host: str = "127.0.0.1"
    port: int = 8080
    path: str = "/webhook"
    verify_signatures: bool = True
    allowed_sources: list[WebhookSourceType] = Field(
        default_factory=lambda: [
            WebhookSourceType.GITHUB,
            WebhookSourceType.GITLAB,
            WebhookSourceType.LINEAR,
        ]
    )
    secret: Optional[str] = None
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)
    max_payload_size: int = 10 * 1024 * 1024  # 10 MB
    timeout_seconds: int = 30
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_source_secret(self, source_type: WebhookSourceType) -> Optional[str]:
        """
        Get webhook secret for a specific source.

        Args:
            source_type: The source type

        Returns:
            Webhook secret if configured, None otherwise
        """
        # Check source-specific config first
        if source_type.value in self.sources:
            return self.sources[source_type.value].get("webhook_secret")

        # Fall back to default secret
        return self.secret


class WebhookResult(BaseModel):
    """
    Result of webhook processing.

    Attributes:
        success: Whether the webhook was processed successfully
        event: The processed webhook event
        error: Error message if processing failed
        status_code: HTTP status code to return
        response_data: Additional response data
        metadata: Additional result metadata
    """

    success: bool
    event: Optional[WebhookEvent] = None
    error: Optional[str] = None
    status_code: int = 200
    response_data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_success(
        cls,
        event: WebhookEvent,
        status_code: int = 200,
        response_data: Optional[dict[str, Any]] = None,
    ) -> WebhookResult:
        """
        Create a successful webhook result.

        Args:
            event: The processed webhook event
            status_code: HTTP status code
            response_data: Additional response data

        Returns:
            WebhookResult with success=True
        """
        return cls(
            success=True,
            event=event,
            status_code=status_code,
            response_data=response_data or {},
        )

    @classmethod
    def from_error(
        cls,
        error: str,
        status_code: int = 400,
        event: Optional[WebhookEvent] = None,
    ) -> WebhookResult:
        """
        Create an error webhook result.

        Args:
            error: Error message
            status_code: HTTP status code
            event: The webhook event (if parsing succeeded)

        Returns:
            WebhookResult with success=False
        """
        return cls(
            success=False,
            error=error,
            status_code=status_code,
            event=event,
        )


class WebhookServer:
    """
    FastAPI-based webhook server for receiving issue events.

    The server listens for webhook POST requests from external issue
    trackers, verifies signatures, parses events, and routes them to
    appropriate handlers.

    Attributes:
        config: Server configuration
        app: FastAPI application instance
        event_handlers: Registered event handlers

    Example:
        >>> config = WebhookConfig(host="0.0.0.0", port=8080)
        >>> server = WebhookServer(config=config)
        >>> await server.start()
        >>> # Server now listening on http://0.0.0.0:8080/webhook
    """

    def __init__(self, config: WebhookConfig) -> None:
        """
        Initialize the webhook server.

        Args:
            config: Server configuration
        """
        self.config = config
        self.app: Optional[Any] = None
        self.event_handlers: dict[WebhookEventType, list[Any]] = {}
        self._server: Optional[Any] = None

    def _create_app(self) -> Any:
        """
        Create the FastAPI application.

        Returns:
            FastAPI application instance
        """
        try:
            from fastapi import FastAPI, Request, Response
            from fastapi.responses import JSONResponse

            app = FastAPI(
                title="Autoflow Issue Intake Webhook Server",
                description="Receives and processes webhooks from GitHub, GitLab, and Linear",
                version="1.0.0",
            )

            @app.get("/")
            async def root() -> dict[str, str]:
                """Health check endpoint."""
                return {
                    "status": "ok",
                    "service": "autoflow-webhook-server",
                    "version": "1.0.0",
                }

            @app.post(self.config.path)
            async def receive_webhook(request: Request) -> JSONResponse:
                """
                Receive and process webhook events.

                Args:
                    request: FastAPI request object

                Returns:
                    JSON response with processing status
                """
                return await self._handle_webhook(request)

            return app

        except ImportError as e:
            raise ImportError(
                "FastAPI is required for webhook server. "
                f"Install it with: pip install fastapi uvicorn. Error: {e}"
            )

    async def _handle_webhook(self, request: Any) -> Any:
        """
        Handle an incoming webhook request.

        Args:
            request: FastAPI request object

        Returns:
            JSON response with processing result
        """
        from fastapi.responses import JSONResponse

        try:
            # Get request details
            headers = dict(request.headers)
            payload_bytes = await request.body()

            # Check payload size
            if len(payload_bytes) > self.config.max_payload_size:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "Payload too large",
                        "max_size": self.config.max_payload_size,
                    },
                )

            # Parse payload
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid JSON payload"},
                )

            # Determine source type
            source_type = self._detect_source_type(headers, payload)

            if source_type not in self.config.allowed_sources:
                return JSONResponse(
                    status_code=403,
                    content={"error": f"Source type {source_type} not allowed"},
                )

            # Verify signature if required
            if self.config.verify_signatures:
                signature = headers.get("x-hub-signature-256") or headers.get(
                    "x-gitlab-token"
                ) or headers.get("linear-signature")

                if not signature:
                    return JSONResponse(
                        status_code=401,
                        content={"error": "Missing signature header"},
                    )

                secret = self.config.get_source_secret(source_type)
                if not secret:
                    return JSONResponse(
                        status_code=500,
                        content={"error": "No secret configured for signature verification"},
                    )

                if not await self._verify_signature(
                    payload_bytes, signature, source_type, secret
                ):
                    return JSONResponse(
                        status_code=401,
                        content={"error": "Invalid signature"},
                    )

            # Parse event
            event = self._parse_event(source_type, payload, headers)
            event.signature = headers.get(
                "x-hub-signature-256"
            ) or headers.get("x-gitlab-token") or headers.get("linear-signature")

            # Process event
            result = await self._process_event(event)

            return JSONResponse(
                status_code=result.status_code,
                content={
                    "success": result.success,
                    "event_id": result.event.id if result.event else None,
                    "error": result.error,
                    **result.response_data,
                },
            )

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Internal server error: {str(e)}"},
            )

    def _detect_source_type(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookSourceType:
        """
        Detect the webhook source type from headers or payload.

        Args:
            headers: HTTP headers
            payload: Webhook payload

        Returns:
            Detected source type
        """
        # Check headers first
        if "x-hub-signature-256" in headers or "x-github-event" in headers:
            return WebhookSourceType.GITHUB
        if "x-gitlab-token" in headers or "x-gitlab-event" in headers:
            return WebhookSourceType.GITLAB
        if "linear-signature" in headers:
            return WebhookSourceType.LINEAR

        # Check payload structure
        if "action" in payload and "issue" in payload:
            # GitHub-style payload
            return WebhookSourceType.GITHUB
        if "object_kind" in payload:
            # GitLab-style payload
            return WebhookSourceType.GITLAB
        if "data" in payload and "type" in str(payload.get("data", {})):
            # Linear-style payload
            return WebhookSourceType.LINEAR

        # Default to GitHub (most common)
        return WebhookSourceType.GITHUB

    def _parse_event(
        self,
        source_type: WebhookSourceType,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> WebhookEvent:
        """
        Parse a webhook event from the payload.

        Args:
            source_type: Type of webhook source
            payload: Raw webhook payload
            headers: HTTP headers

        Returns:
            Parsed WebhookEvent
        """
        # Determine event type
        event_type = self._detect_event_type(source_type, payload)

        # Extract common fields
        source_id: Optional[str] = None
        source_url: Optional[str] = None
        action: Optional[str] = None

        if source_type == WebhookSourceType.GITHUB:
            action = payload.get("action")
            issue_data = payload.get("issue") or payload.get("pull_request") or {}
            source_id = str(issue_data.get("id")) or str(issue_data.get("number"))
            source_url = issue_data.get("html_url")

        elif source_type == WebhookSourceType.GITLAB:
            action = payload.get("object_attributes", {}).get("action")
            issue_data = payload.get("issue") or payload.get("merge_request") or {}
            source_id = str(issue_data.get("id") or issue_data.get("iid"))
            source_url = issue_data.get("url")

        elif source_type == WebhookSourceType.LINEAR:
            data = payload.get("data", {})
            action = data.get("type")
            issue_data = data.get("issue") or {}
            source_id = issue_data.get("id")
            # Linear typically provides IDs without URLs in webhooks

        return WebhookEvent(
            source_type=source_type,
            event_type=event_type,
            source_id=source_id,
            source_url=source_url,
            action=action,
            payload=payload,
            headers=headers,
        )

    def _detect_event_type(
        self,
        source_type: WebhookSourceType,
        payload: dict[str, Any],
    ) -> WebhookEventType:
        """
        Detect the type of webhook event.

        Args:
            source_type: Type of webhook source
            payload: Raw webhook payload

        Returns:
            Detected event type
        """
        if source_type == WebhookSourceType.GITHUB:
            github_event = payload.get("action", "unknown")
            return self._map_github_event(github_event, payload)

        elif source_type == WebhookSourceType.GITLAB:
            object_kind = payload.get("object_kind", "unknown")
            return self._map_gitlab_event(object_kind, payload)

        elif source_type == WebhookSourceType.LINEAR:
            data_type = payload.get("data", {}).get("type", "unknown")
            return self._map_linear_event(data_type)

        return WebhookEventType.UNKNOWN

    def _map_github_event(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> WebhookEventType:
        """Map GitHub webhook action to event type."""
        mapping = {
            "opened": WebhookEventType.ISSUES_OPENED,
            "closed": WebhookEventType.ISSUES_CLOSED,
            "reopened": WebhookEventType.ISSUES_REOPENED,
            "edited": WebhookEventType.ISSUES_EDITED,
            "assigned": WebhookEventType.ISSUES_ASSIGNED,
            "labeled": WebhookEventType.ISSUES_LABELED,
            "unlabeled": WebhookEventType.ISSUES_UNLABELED,
            "created": (
                WebhookEventType.ISSUE_COMMENT_CREATED
                if "comment" in payload
                else WebhookEventType.PULL_REQUEST_OPENED
            ),
            "synchronize": WebhookEventType.ISSUES_EDITED,
        }
        return mapping.get(action, WebhookEventType.UNKNOWN)

    def _map_gitlab_event(
        self,
        object_kind: str,
        payload: dict[str, Any],
    ) -> WebhookEventType:
        """Map GitLab webhook object_kind to event type."""
        mapping = {
            "issue": WebhookEventType.ISSUES_OPENED,
            "issue_update": WebhookEventType.ISSUES_EDITED,
            "issue_close": WebhookEventType.ISSUES_CLOSED,
            "issue_reopen": WebhookEventType.ISSUES_REOPENED,
            "merge_request": WebhookEventType.PULL_REQUEST_OPENED,
            "merge_request_update": WebhookEventType.ISSUES_EDITED,
            "merge_request_close": WebhookEventType.ISSUES_CLOSED,
            "merge_request_merge": WebhookEventType.PULL_REQUEST_MERGED,
            "note": WebhookEventType.ISSUE_COMMENT_CREATED,
        }

        # Check action attribute
        if object_kind == "issue":
            action = payload.get("object_attributes", {}).get("action")
            if action == "close":
                return WebhookEventType.ISSUES_CLOSED
            elif action == "reopen":
                return WebhookEventType.ISSUES_REOPENED
            elif action == "update":
                return WebhookEventType.ISSUES_EDITED

        return mapping.get(object_kind, WebhookEventType.UNKNOWN)

    def _map_linear_event(self, event_type: str) -> WebhookEventType:
        """Map Linear webhook type to event type."""
        mapping = {
            "Issue": WebhookEventType.ISSUES_OPENED,
            "IssueUpdate": WebhookEventType.ISSUES_EDITED,
            "IssueStatusUpdate": WebhookEventType.ISSUES_EDITED,
            "IssueComment": WebhookEventType.ISSUE_COMMENT_CREATED,
        }
        return mapping.get(event_type, WebhookEventType.UNKNOWN)

    async def _verify_signature(
        self,
        payload: bytes,
        signature: str,
        source_type: WebhookSourceType,
        secret: str,
    ) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Raw payload bytes
            signature: Signature from headers
            source_type: Type of webhook source
            secret: Webhook secret

        Returns:
            True if signature is valid, False otherwise
        """
        import hashlib
        import hmac

        try:
            if source_type == WebhookSourceType.GITHUB:
                # GitHub uses HMAC-SHA256
                expected_signature = f"sha256={hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()}"
                return hmac.compare_digest(expected_signature, signature)

            elif source_type == WebhookSourceType.GITLAB:
                # GitLab uses a simple token comparison
                return hmac.compare_digest(secret, signature)

            elif source_type == WebhookSourceType.LINEAR:
                # Linear uses HMAC-SHA256
                expected_signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
                return hmac.compare_digest(expected_signature, signature)

            return False

        except Exception:
            return False

    async def _process_event(self, event: WebhookEvent) -> WebhookResult:
        """
        Process a webhook event by calling registered handlers.

        Args:
            event: The webhook event to process

        Returns:
            WebhookResult with processing outcome
        """
        try:
            # Get handlers for this event type
            handlers = self.event_handlers.get(event.event_type, [])

            # Call all handlers
            for handler in handlers:
                if hasattr(handler, "__await__"):
                    await handler(event)
                else:
                    handler(event)

            # Mark event as processed
            event.mark_processed()

            return WebhookResult.from_success(
                event=event,
                status_code=200,
                response_data={"handlers_called": len(handlers)},
            )

        except Exception as e:
            return WebhookResult.from_error(
                error=str(e),
                status_code=500,
                event=event,
            )

    def register_handler(
        self,
        event_type: WebhookEventType,
        handler: Any,
    ) -> None:
        """
        Register an event handler.

        Args:
            event_type: Type of event to handle
            handler: Async or sync function to call

        Example:
            >>> async def handle_issue_opened(event: WebhookEvent):
            ...     print(f"Issue opened: {event.source_id}")
            >>> server.register_handler(WebhookEventType.ISSUES_OPENED, handle_issue_opened)
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    async def start(self) -> None:
        """
        Start the webhook server.

        Raises:
            ImportError: If FastAPI or uvicorn are not installed

        Example:
            >>> await server.start()
        """
        if self.app is None:
            self.app = self._create_app()

        try:
            import uvicorn

            config = uvicorn.Config(
                app=self.app,
                host=self.config.host,
                port=self.config.port,
                log_level="info",
            )
            self._server = uvicorn.Server(config)
            await self._server.serve()

        except ImportError as e:
            raise ImportError(
                "uvicorn is required to run the webhook server. "
                f"Install it with: pip install uvicorn. Error: {e}"
            )

    async def stop(self) -> None:
        """Stop the webhook server."""
        if self._server:
            self._server.should_exit = True
            self._server = None

    def __repr__(self) -> str:
        """Return string representation of the server."""
        return (
            f"WebhookServer(host={self.config.host!r}, "
            f"port={self.config.port}, "
            f"path={self.config.path!r})"
        )
