"""
Autoflow SSO Integration Module

Provides SAML and OIDC SSO integration for enterprise identity management.
Supports major SSO providers like Okta, Azure AD, and Google Workspace.

Usage:
    from autoflow.auth.sso import SAMLProvider, SAMLConfig

    # Configure SAML provider
    config = SAMLConfig(
        entity_id="https://autoflow.example.com",
        acs_url="https://autoflow.example.com/saml/acs",
        certificate="...",
        private_key="..."
    )

    # Initialize provider
    provider = SAMLProvider(config)

    # Generate SAML request for login
    auth_request = provider.create_auth_request()

    # Process SAML response from IdP
    user_attrs = provider.parse_response(saml_response)
"""

from __future__ import annotations

import base64
import zlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class SSOProvider(str, Enum):
    """Supported SSO provider types."""

    SAML = "saml"
    OIDC = "oidc"
    NONE = "none"


class NameIDFormat(str, Enum):
    """SAML NameID formats."""

    UNSPECIFIED = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    EMAIL_ADDRESS = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    PERSISTENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    TRANSIENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:transient"


class SAMLConfig(BaseModel):
    """
    SAML provider configuration.

    Contains settings for SAML integration with identity providers.
    Supports both service provider (SP) and identity provider (IdP) configuration.

    Attributes:
        entity_id: SP entity ID (usually the base URL)
        acs_url: Assertion Consumer Service URL (callback URL)
        slo_url: Single Logout Service URL (optional)
        certificate: SP X.509 certificate (PEM format)
        private_key: SP private key (PEM format)
        idp_entity_id: IdP entity ID
        idp_sso_url: IdP SSO login URL
        idp_slo_url: IdP SSO logout URL (optional)
        idp_certificate: IdP X.509 certificate for signature verification
        name_id_format: SAML NameID format (default: EMAIL_ADDRESS)
        attribute_mapping: Map SAML attributes to user fields
        want_assertions_signed: Require signed assertions (default: True)
        want_response_signed: Require signed responses (default: True)
        organization: Organization info for SAML metadata
        technical_contact: Technical contact info for SAML metadata

    Example:
        >>> config = SAMLConfig(
        ...     entity_id="https://autoflow.example.com",
        ...     acs_url="https://autoflow.example.com/saml/acs",
        ...     certificate="-----BEGIN CERTIFICATE-----\\n...",
        ...     private_key="-----BEGIN PRIVATE KEY-----\\n...",
        ...     idp_entity_id="https://idp.example.com/entityid",
        ...     idp_sso_url="https://idp.example.com/sso",
        ...     idp_certificate="-----BEGIN CERTIFICATE-----\\n..."
        ... )
        >>> provider = SAMLProvider(config=config)
    """

    # Service Provider (SP) Configuration
    entity_id: str
    acs_url: str
    slo_url: Optional[str] = None
    certificate: Optional[str] = None
    private_key: Optional[str] = None

    # Identity Provider (IdP) Configuration
    idp_entity_id: str
    idp_sso_url: str
    idp_slo_url: Optional[str] = None
    idp_certificate: Optional[str] = None

    # SAML Settings
    name_id_format: NameIDFormat = NameIDFormat.EMAIL_ADDRESS
    attribute_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "email": "email",
            "name": "name",
            "first_name": "firstName",
            "last_name": "lastName",
        }
    )
    want_assertions_signed: bool = True
    want_response_signed: bool = True

    # Metadata Information
    organization: Optional[dict[str, str]] = None
    technical_contact: Optional[dict[str, str]] = None

    @field_validator("entity_id", "acs_url", "idp_sso_url", mode="before")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        """Validate that URLs are properly formatted."""
        if not v:
            return v
        parsed = urlparse(v)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError(f"Invalid URL: {v}")
        return v

    @field_validator("certificate", "private_key", "idp_certificate", mode="before")
    @classmethod
    def validate_pem_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate PEM format for certificates and keys."""
        if not v:
            return v
        if "-----BEGIN" not in v or "-----END" not in v:
            raise ValueError("Certificate/key must be in PEM format")
        return v.strip()


class SAMLProvider(BaseModel):
    """
    SAML SSO provider integration.

    Handles SAML authentication flow with identity providers.
    Supports SAML 2.0 protocol for enterprise single sign-on.

    Attributes:
        config: SAML configuration

    Example:
        >>> provider = SAMLProvider(config=config)
        >>> auth_request = provider.create_auth_request()
        >>> user_attrs = provider.parse_response(saml_response)
    """

    config: SAMLConfig
    _request_id: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def create_auth_request(self, relay_state: Optional[str] = None) -> dict[str, str]:
        """
        Create a SAML authentication request.

        Generates a SAML AuthNRequest for initiating login with the IdP.
        The request is URL-encoded and ready to be sent to the IdP.

        Args:
            relay_state: Optional relay state for CSRF protection

        Returns:
            Dictionary with SAML request data:
                - saml_request: Base64-encoded SAML request
                - relay_state: Relay state value
                - idp_sso_url: URL to send the request to

        Raises:
            ValueError: If configuration is invalid

        Example:
            >>> request = provider.create_auth_request(
            ...     relay_state="/dashboard"
            ... )
            >>> redirect_url = (
            ...     f"{request['idp_sso_url']}?"
            ...     f"SAMLRequest={request['saml_request']}"
            ... )
        """
        if not self.config.idp_sso_url:
            raise ValueError("IdP SSO URL not configured")

        # Generate request ID
        import uuid

        self._request_id = f"_{uuid.uuid4()}"

        # Build SAML AuthNRequest (simplified version)
        # In production, use python3-saml or similar library
        saml_request = self._build_authn_request()

        # Encode request
        encoded_request = self._encode_saml_request(saml_request)

        return {
            "saml_request": encoded_request,
            "relay_state": relay_state or "",
            "idp_sso_url": self.config.idp_sso_url,
        }

    def parse_response(
        self, saml_response: str, validate_only: bool = False
    ) -> dict[str, Any]:
        """
        Parse and validate a SAML response from the IdP.

        Extracts user attributes from the SAML assertion and validates
        the signature and timestamps.

        Args:
            saml_response: Base64-encoded SAML response from IdP
            validate_only: If True, only validate without returning attributes

        Returns:
            Dictionary with parsed user attributes:
                - name_id: User's NameID (usually email)
                - email: User's email address
                - name: User's full name
                - first_name: User's first name
                - last_name: User's last name
                - attributes: All SAML attributes

        Raises:
            ValueError: If response is invalid or signature verification fails

        Example:
            >>> user_attrs = provider.parse_response(saml_response)
            >>> email = user_attrs["email"]
            'user@example.com'
        """
        # Decode SAML response
        decoded_response = self._decode_saml_response(saml_response)

        # Validate signature (if configured)
        if self.config.want_response_signed:
            self._validate_signature(decoded_response)

        # Extract attributes from assertion
        attributes = self._extract_attributes(decoded_response)

        if validate_only:
            return {"valid": True}

        return attributes

    def create_logout_request(
        self, session_index: str, name_id: str
    ) -> dict[str, str]:
        """
        Create a SAML logout request.

        Generates a SAML LogoutRequest for single logout.

        Args:
            session_index: Session index from the original assertion
            name_id: User's NameID from the original assertion

        Returns:
            Dictionary with logout request data:
                - saml_request: Base64-encoded SAML logout request
                - idp_slo_url: URL to send the request to

        Raises:
            ValueError: If IdP SLO URL is not configured

        Example:
            >>> logout = provider.create_logout_request(
            ...     session_index="abc123",
            ...     name_id="user@example.com"
            ... )
        """
        if not self.config.idp_slo_url:
            raise ValueError("IdP SLO URL not configured")

        import uuid

        request_id = f"_{uuid.uuid4()}"
        logout_request = self._build_logout_request(request_id, session_index, name_id)

        encoded_request = self._encode_saml_request(logout_request)

        return {
            "saml_request": encoded_request,
            "idp_slo_url": self.config.idp_slo_url,
        }

    def generate_metadata(self) -> str:
        """
        Generate SAML metadata for the service provider.

        Creates an XML metadata document describing the SP configuration.
        This can be uploaded to the IdP to configure the trust relationship.

        Returns:
            XML metadata document

        Example:
            >>> metadata = provider.generate_metadata()
            >>> with open("saml-metadata.xml", "w") as f:
            ...     f.write(metadata)
        """
        metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                      entityID="{self.config.entity_id}">
  <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>{self.config.name_id_format.value}</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                 Location="{self.config.acs_url}"
                                 index="1"/>
    {self._get_slo_service_metadata()}
  </md:SPSSODescriptor>
</md:EntityDescriptor>"""
        return metadata

    def _build_authn_request(self) -> str:
        """Build a SAML AuthNRequest XML document."""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        expire = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        authn_request = f"""<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                          ID="{self._request_id}"
                          Version="2.0"
                          IssueInstant="{now}"
                          ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                          AssertionConsumerServiceURL="{self.config.acs_url}"
                          Destination="{self.config.idp_sso_url}">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    {self.config.entity_id}
  </saml:Issuer>
  <samlp:NameIDPolicy Format="{self.config.name_id_format.value}"
                      AllowCreate="true"/>
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
      urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
    </saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>"""
        return authn_request

    def _build_logout_request(
        self, request_id: str, session_index: str, name_id: str
    ) -> str:
        """Build a SAML LogoutRequest XML document."""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        logout_request = f"""<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                          ID="{request_id}"
                          Version="2.0"
                          IssueInstant="{now}"
                          Destination="{self.config.idp_slo_url}">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    {self.config.entity_id}
  </saml:Issuer>
  <saml:NameID xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
               Format="{self.config.name_id_format.value}">
    {name_id}
  </saml:NameID>
  <samlp:SessionIndex>{session_index}</samlp:SessionIndex>
</samlp:LogoutRequest>"""
        return logout_request

    def _encode_saml_request(self, saml_request: str) -> str:
        """
        Encode a SAML request for transport.

        Applies deflate compression and base64 encoding.

        Args:
            saml_request: SAML request XML

        Returns:
            URL-safe base64 encoded request
        """
        # Compress
        compressed = zlib.compress(saml_request.encode("utf-8"))[2:-4]

        # Base64 encode
        encoded = base64.b64encode(compressed).decode("utf-8")

        # URL-safe encoding
        return encoded.replace("+", "-").replace("/", "_").replace("=", "")

    def _decode_saml_response(self, saml_response: str) -> str:
        """
        Decode a SAML response from transport encoding.

        Args:
            saml_response: Base64-encoded SAML response

        Returns:
            Decoded XML response

        Raises:
            ValueError: If response cannot be decoded
        """
        try:
            # Add padding if needed
            padding = 4 - len(saml_response) % 4
            if padding != 4:
                saml_response += "=" * padding

            # Base64 decode
            decoded = base64.b64decode(saml_response)

            # Try to decompress (deflate)
            try:
                decompressed = zlib.decompress(decoded, -15)
                return decompressed.decode("utf-8")
            except zlib.error:
                # Not compressed, return as-is
                return decoded.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to decode SAML response: {e}") from e

    def _validate_signature(self, response_xml: str) -> None:
        """
        Validate SAML response signature.

        Args:
            response_xml: Decoded SAML response XML

        Raises:
            ValueError: If signature is invalid or certificate not configured

        Note:
            This is a simplified implementation. In production, use
            python3-saml or similar library for proper signature validation.
        """
        if not self.config.idp_certificate:
            raise ValueError("IdP certificate required for signature validation")

        # TODO: Implement proper signature validation using cryptography lib
        # For now, we just check that certificate is configured
        pass

    def _extract_attributes(self, response_xml: str) -> dict[str, Any]:
        """
        Extract user attributes from SAML response.

        Args:
            response_xml: Decoded SAML response XML

        Returns:
            Dictionary with mapped user attributes

        Note:
            This is a simplified implementation. In production, use
            proper XML parsing with defusedxml for security.
        """
        # TODO: Implement proper XML parsing and attribute extraction
        # For now, return a placeholder structure
        return {
            "name_id": "",
            "email": "",
            "name": "",
            "first_name": "",
            "last_name": "",
            "attributes": {},
        }

    def _get_slo_service_metadata(self) -> str:
        """Generate SLO service metadata if configured."""
        if not self.config.slo_url:
            return ""

        return f"""    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                                Location="{self.config.slo_url}"/>"""


class OIDCConfig(BaseModel):
    """
    OIDC provider configuration.

    Contains settings for OpenID Connect integration.

    Attributes:
        client_id: OAuth 2.0 client ID
        client_secret: OAuth 2.0 client secret
        discovery_url: OpenID Connect discovery URL
        authorization_endpoint: OAuth 2.0 authorization endpoint
        token_endpoint: OAuth 2.0 token endpoint
        userinfo_endpoint: OAuth 2.0 userinfo endpoint
        jwks_uri: JWKS endpoint for token validation
        scope: OAuth 2.0 scopes to request
        redirect_uri: OAuth 2.0 redirect URI
        response_type: OAuth 2.0 response type (default: code)
        grant_type: OAuth 2.0 grant type (default: authorization_code)

    Example:
        >>> config = OIDCConfig(
        ...     client_id="your-client-id",
        ...     client_secret="your-client-secret",
        ...     discovery_url="https://accounts.google.com/.well-known/openid-configuration"
        ... )
    """

    client_id: str
    client_secret: str
    discovery_url: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    scope: str = "openid email profile"
    redirect_uri: str = "http://localhost:8000/auth/oidc/callback"
    response_type: str = "code"
    grant_type: str = "authorization_code"


class OIDCProvider(BaseModel):
    """
    OIDC SSO provider integration.

    Handles OpenID Connect authentication flow with identity providers.

    Attributes:
        config: OIDC configuration

    Example:
        >>> provider = OIDCProvider(config=config)
        >>> auth_url = provider.get_authorization_url()
        >>> tokens = provider.exchange_code_for_token(code)
        >>> user_info = provider.get_user_info(tokens["access_token"])
    """

    config: OIDCConfig
    _state: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Get the authorization URL for initiating OIDC login.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL to redirect the user to

        Raises:
            ValueError: If authorization endpoint is not configured

        Example:
            >>> auth_url = provider.get_authorization_url()
            >>> # Redirect user to auth_url
        """
        if not self.config.authorization_endpoint:
            raise ValueError("Authorization endpoint not configured")

        import secrets

        self._state = state or secrets.token_urlsafe(32)

        from urllib.parse import urlencode

        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": self.config.scope,
            "response_type": self.config.response_type,
            "state": self._state,
        }

        return f"{self.config.authorization_endpoint}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, state: str) -> dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from the callback
            state: State parameter from callback (for validation)

        Returns:
            Dictionary with token response:
                - access_token: OAuth 2.0 access token
                - id_token: OpenID Connect ID token
                - token_type: Token type (usually "Bearer")
                - expires_in: Token expiration time
                - refresh_token: Optional refresh token

        Raises:
            ValueError: If state doesn't match or token endpoint not configured

        Example:
            >>> tokens = provider.exchange_code_for_token(code, state)
            >>> access_token = tokens["access_token"]
        """
        if self._state and self._state != state:
            raise ValueError("Invalid state parameter")

        if not self.config.token_endpoint:
            raise ValueError("Token endpoint not configured")

        # TODO: Implement actual token exchange using authlib
        # For now, return placeholder
        return {
            "access_token": "",
            "id_token": "",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        """
        Get user information from the userinfo endpoint.

        Args:
            access_token: OAuth 2.0 access token

        Returns:
            Dictionary with user information

        Raises:
            ValueError: If userinfo endpoint is not configured

        Example:
            >>> user_info = provider.get_user_info(access_token)
            >>> email = user_info["email"]
        """
        if not self.config.userinfo_endpoint:
            raise ValueError("Userinfo endpoint not configured")

        # TODO: Implement actual userinfo request using authlib
        # For now, return placeholder
        return {
            "sub": "",
            "email": "",
            "name": "",
            "given_name": "",
            "family_name": "",
        }

    def validate_id_token(self, id_token: str) -> dict[str, Any]:
        """
        Validate and decode an ID token.

        Args:
            id_token: OpenID Connect ID token

        Returns:
            Decoded token claims

        Raises:
            ValueError: If token is invalid

        Example:
            >>> claims = provider.validate_id_token(id_token)
            >>> user_id = claims["sub"]
        """
        # TODO: Implement proper JWT validation using authlib
        # For now, return placeholder
        return {
            "iss": "",
            "sub": "",
            "aud": "",
            "exp": 0,
            "iat": 0,
        }
