"""ProclaimClient for REST API integration with tenant support."""

import atexit
import base64
import logging
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from ..utils.session_manager import SessionManager

logger = logging.getLogger(__name__)


class ProclaimClient:
    """Client for interacting with Proclaim REST API with DataPipelines tenant support."""

    def __init__(self, base_url: str, username: str, password: str,
                 tenant_id: str = None, timeout: int = 30):
        """Initialize Proclaim client.

        Args:
            base_url: Proclaim API base URL
            username: Proclaim username
            password: Proclaim password
            tenant_id: Tenant identifier for multi-tenant isolation
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.tenant_id = tenant_id
        self.timeout = timeout
        self.session_token = None
        self.session_manager = SessionManager()

        self._register_cleanup_handlers()
        self._authenticate()

    def _register_cleanup_handlers(self) -> None:
        """Register cleanup handlers for graceful session cleanup."""
        atexit.register(self._cleanup_session)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle process signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, cleaning up Proclaim session...")
        self._cleanup_session()
        sys.exit(0)

    def _authenticate(self) -> None:
        """Authenticate with Proclaim API and obtain session token."""
        # Try to load existing session first
        session_data = self.session_manager.load_session()
        if session_data and session_data.get('username') == self.username:
            self.session_token = session_data['token']
            logger.info(f"Loaded existing session for {self.username}")
            return

        # Create new session
        try:
            logger.info(f"Authenticating with Proclaim API for {self.username}")

            auth_url = f"{self.base_url}/api/session"
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()

            headers = {
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }

            response = requests.post(auth_url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            auth_data = response.json()
            self.session_token = auth_data.get('sessionToken')

            if not self.session_token:
                raise ValueError("No session token received from authentication")

            # Save session for reuse
            self.session_manager.save_session(
                token=self.session_token,
                username=self.username,
                additional_data={'tenant_id': self.tenant_id}
            )

            logger.info(f"Successfully authenticated with Proclaim API")

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def _cleanup_session(self) -> None:
        """Clean up session and logout from Proclaim API."""
        if self.session_token:
            try:
                logout_url = f"{self.base_url}/api/session"
                headers = self._get_headers()

                response = requests.delete(logout_url, headers=headers, timeout=self.timeout)
                logger.info("Logged out from Proclaim API")

            except Exception as e:
                logger.warning(f"Error during logout: {e}")

            finally:
                self.session_token = None
                self.session_manager.clear_session()

    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for API requests."""
        if not self.session_token:
            raise RuntimeError("No session token available")

        return {
            'Authorization': f'Bearer {self.session_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated request to Proclaim API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            requests.RequestException: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        # Merge any additional headers
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                timeout=self.timeout,
                **kwargs
            )

            # Handle authentication errors
            if response.status_code == 401:
                logger.warning("Session expired, re-authenticating...")
                self._authenticate()
                headers = self._get_headers()
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs
                )

            response.raise_for_status()
            self.session_manager.refresh_session()
            return response

        except requests.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {e}")
            raise

    def get_case_data(self, case_ref: str) -> Dict[str, Any]:
        """Get comprehensive case data from Proclaim API.

        Args:
            case_ref: Case reference number

        Returns:
            Dictionary containing case data
        """
        logger.info(f"Fetching case data for {case_ref}")

        try:
            # Get basic case information
            case_endpoint = f"/api/case/{quote(case_ref)}"
            response = self._make_request('GET', case_endpoint)
            case_data = response.json()

            # Get case history
            history_endpoint = f"/api/case/{quote(case_ref)}/history"
            history_response = self._make_request('GET', history_endpoint)
            case_data['history'] = history_response.json()

            # Get case parties
            parties_endpoint = f"/api/case/{quote(case_ref)}/parties"
            parties_response = self._make_request('GET', parties_endpoint)
            case_data['parties'] = parties_response.json()

            # Get document manifest
            docs_endpoint = f"/api/case/{quote(case_ref)}/documents"
            try:
                docs_response = self._make_request('GET', docs_endpoint)
                case_data['document_manifest'] = docs_response.json()
            except requests.RequestException as e:
                logger.warning(f"Could not fetch document manifest for {case_ref}: {e}")
                case_data['document_manifest'] = []

            logger.info(f"Successfully fetched case data for {case_ref}")
            return case_data

        except Exception as e:
            logger.error(f"Failed to fetch case data for {case_ref}: {e}")
            raise

    def get_case_data_with_tenant_context(self, case_ref: str) -> Dict[str, Any]:
        """Get case data with tenant metadata for isolation.

        Args:
            case_ref: Case reference number

        Returns:
            Case data with tenant context
        """
        case_data = self.get_case_data(case_ref)
        if self.tenant_id:
            case_data['tenant_id'] = self.tenant_id
        return case_data

    def get_multiple_cases(self, case_refs: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get data for multiple cases efficiently.

        Args:
            case_refs: List of case reference numbers

        Returns:
            Dictionary mapping case_ref to case data
        """
        results = {}

        for case_ref in case_refs:
            try:
                case_data = self.get_case_data_with_tenant_context(case_ref)
                results[case_ref] = case_data

                # Add small delay to avoid overwhelming the API
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to fetch case {case_ref}: {e}")
                results[case_ref] = {'error': str(e)}

        return results

    def search_cases(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search for cases using Proclaim API.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of case summaries
        """
        search_endpoint = f"/api/search/cases"
        params = {
            'q': query,
            'limit': limit
        }

        try:
            response = self._make_request('GET', search_endpoint, params=params)
            results = response.json()

            # Add tenant context to results
            if self.tenant_id:
                for result in results:
                    result['tenant_id'] = self.tenant_id

            return results

        except Exception as e:
            logger.error(f"Case search failed: {e}")
            raise

    def get_session_health(self) -> Dict[str, Any]:
        """Get current session health status.

        Returns:
            Dictionary with session health information
        """
        try:
            # Test session with a simple API call
            test_endpoint = "/api/user"
            response = self._make_request('GET', test_endpoint)

            session_info = self.session_manager.get_session_info()

            return {
                'status': 'healthy',
                'session_valid': True,
                'tenant_id': self.tenant_id,
                'username': self.username,
                'session_info': session_info
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'session_valid': False,
                'error': str(e),
                'tenant_id': self.tenant_id,
                'username': self.username
            }