"""Enhanced session management for V2 with lifecycle handling."""

import signal
import logging
from contextlib import contextmanager
from typing import Generator, Any

# Import Proclaim components for integration
from caseguard.utils.session_manager import SessionManager as ProclaimSessionManager
from caseguard.proclaim.client import ProclaimClient

logger = logging.getLogger(__name__)


class V2SessionManager:
    """Enhanced session manager for V2 with Proclaim client integration."""

    def __init__(self):
        """Initialize V2 session manager with signal handlers."""
        self.proclaim_session_manager = ProclaimSessionManager()
        self._active_sessions = {}
        self._max_session_duration = 6 * 3600  # 6 hours in seconds
        self.setup_signal_handlers()

    def setup_signal_handlers(self) -> None:
        """Setup graceful shutdown signal handlers."""
        try:
            signal.signal(signal.SIGINT, self._graceful_shutdown)
            signal.signal(signal.SIGTERM, self._graceful_shutdown)
            logger.info("Signal handlers registered for graceful shutdown")
        except Exception as e:
            logger.warning(f"Could not setup signal handlers: {e}")

    def _graceful_shutdown(self, signum: int, frame: Any) -> None:
        """Handle graceful shutdown of active sessions.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        try:
            if self._active_sessions > 0:
                logger.info(f"Cleaning up {self._active_sessions} active sessions...")
                self.cleanup_session()
            logger.info("Graceful shutdown completed")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")

    @contextmanager
    def bulk_processing_session(self, max_duration_hours: int = 6) -> Generator[Any, None, None]:
        """Context manager for safe bulk case processing sessions.

        Args:
            max_duration_hours: Maximum session duration in hours

        Yields:
            Active session object for Proclaim API calls
        """
        session = None
        self._active_sessions += 1

        try:
            logger.info("Starting bulk processing session")
            session = self.get_session()

            if not session:
                raise RuntimeError("Failed to obtain Proclaim session")

            logger.info("Bulk processing session established")
            yield session

        except Exception as e:
            logger.error(f"Bulk processing session error: {e}")
            raise

        finally:
            self._active_sessions = max(0, self._active_sessions - 1)
            try:
                if session:
                    self.cleanup_session()
                    logger.info("Bulk processing session cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up bulk processing session: {e}")

    def get_proclaim_client(self, tenant_id: str) -> ProclaimClient:
        """Get configured ProclaimClient with session management.

        Args:
            tenant_id: Tenant identifier

        Returns:
            ProclaimClient instance
        """
        if tenant_id not in self._active_sessions:
            import os

            client = ProclaimClient(
                base_url=os.getenv('PROCLAIM_BASE_URL'),
                username=os.getenv('PROCLAIM_USERNAME'),
                password=os.getenv('PROCLAIM_PASSWORD'),
                tenant_id=tenant_id
            )
            self._active_sessions[tenant_id] = client

        return self._active_sessions[tenant_id]

    def _cleanup_sessions(self):
        """Clean up all active sessions."""
        for client in self._active_sessions.values():
            try:
                client._cleanup_session()
            except Exception as e:
                logger.warning(f"Error cleaning up session: {e}")
        self._active_sessions.clear()

    @contextmanager
    def transient_session(self) -> Generator[Any, None, None]:
        """Context manager for short-lived API operations.

        Yields:
            Temporary session that is automatically cleaned up
        """
        session = None
        try:
            session = self.get_session()
            yield session
        finally:
            # For transient sessions, we don't always cleanup
            # to allow session reuse within the same process
            pass

    def get_session_health(self) -> dict:
        """Get current session health status.

        Returns:
            Dictionary with session health information
        """
        try:
            session_info = self.get_session_info()

            if not session_info:
                return {
                    "status": "no_session",
                    "healthy": False,
                    "active_sessions": self._active_sessions
                }

            age_hours = session_info.get("age_hours", 0)
            is_healthy = age_hours < (self._max_session_duration / 3600)

            return {
                "status": "active" if is_healthy else "expired",
                "healthy": is_healthy,
                "age_hours": age_hours,
                "active_sessions": self._active_sessions,
                "username": session_info.get("username"),
                "max_duration_hours": self._max_session_duration / 3600
            }

        except Exception as e:
            logger.error(f"Error checking session health: {e}")
            return {
                "status": "error",
                "healthy": False,
                "error": str(e),
                "active_sessions": self._active_sessions
            }


# Global session manager instance for V2
_session_manager = None


def get_v2_session_manager() -> V2SessionManager:
    """Get global V2 session manager instance.

    Returns:
        Global V2SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = V2SessionManager()
    return _session_manager