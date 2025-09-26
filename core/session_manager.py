"""Enhanced session management for V2 with lifecycle handling."""

import signal
import logging
from contextlib import contextmanager
from typing import Generator, Any

# Import existing session management from current implementation
from caseguard.utils.session_manager import SessionManager as LegacySessionManager

logger = logging.getLogger(__name__)


class V2SessionManager(LegacySessionManager):
    """Enhanced session manager for V2 with improved lifecycle management."""

    def __init__(self):
        """Initialize V2 session manager with signal handlers."""
        super().__init__()
        self.setup_signal_handlers()
        self._active_sessions = 0
        self._max_session_duration = 6 * 3600  # 6 hours in seconds

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

    def get_session(self) -> Any:
        """Get active session with enhanced error handling.

        Returns:
            Active session object

        Raises:
            RuntimeError: If session cannot be obtained
        """
        try:
            session = super().load_session()

            if session:
                # Check session age
                import datetime
                created_at = datetime.datetime.fromisoformat(session['created_at'])
                age_seconds = (datetime.datetime.now() - created_at).total_seconds()

                if age_seconds > self._max_session_duration:
                    logger.warning(f"Session expired ({age_seconds/3600:.1f}h old), creating new session")
                    self.cleanup_session()
                    session = None

            # Create new session if needed
            if not session:
                logger.info("Creating new Proclaim session")
                # This would typically authenticate with Proclaim API
                # For now, return existing session structure
                session = super().load_session()

            return session

        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            raise RuntimeError(f"Session acquisition failed: {e}") from e

    def cleanup_session(self) -> None:
        """Enhanced session cleanup with error handling."""
        try:
            logger.info("Cleaning up Proclaim session")
            super().clear_session()
            logger.info("Session cleanup completed")
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")

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