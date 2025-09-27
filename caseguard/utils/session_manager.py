"""Session management utilities for Proclaim API integration."""

import atexit
import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Proclaim API session tokens with persistence and cleanup."""

    def __init__(self, session_file: Optional[str] = None):
        """Initialize session manager.

        Args:
            session_file: Optional path to session file (defaults to ~/.caseguard/proclaim_session.json)
        """
        self.session_file = session_file or self._get_default_session_file()
        self.session_data = None
        self._lock = threading.Lock()
        self._cleanup_registered = False

        # Register cleanup handlers
        self._register_cleanup_handlers()

    def _get_default_session_file(self) -> str:
        """Get default session file path."""
        session_dir = Path.home() / '.caseguard'
        session_dir.mkdir(exist_ok=True)
        return str(session_dir / 'proclaim_session.json')

    def _register_cleanup_handlers(self):
        """Register cleanup handlers for graceful session cleanup."""
        if not self._cleanup_registered:
            atexit.register(self.clear_session)
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            self._cleanup_registered = True
            logger.debug("Session cleanup handlers registered")

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle process signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, cleaning up session...")
        self.clear_session()
        sys.exit(0)

    def save_session(self, token: str, username: str, additional_data: Optional[Dict] = None) -> None:
        """Save session token and metadata to persistent storage.

        Args:
            token: Session token from Proclaim API
            username: Username used for authentication
            additional_data: Optional additional session metadata
        """
        with self._lock:
            session_data = {
                'token': token,
                'username': username,
                'created_at': datetime.now().isoformat(),
                'last_used': datetime.now().isoformat(),
                **(additional_data or {})
            }

            try:
                # Ensure session directory exists
                Path(self.session_file).parent.mkdir(parents=True, exist_ok=True)

                with open(self.session_file, 'w') as f:
                    json.dump(session_data, f, indent=2)

                self.session_data = session_data
                logger.info(f"Session saved for user {username}")

            except Exception as e:
                logger.error(f"Failed to save session: {e}")
                raise

    def load_session(self) -> Optional[Dict[str, Any]]:
        """Load session from persistent storage.

        Returns:
            Session data dictionary or None if no valid session exists
        """
        with self._lock:
            try:
                if not os.path.exists(self.session_file):
                    logger.debug("No session file found")
                    return None

                with open(self.session_file, 'r') as f:
                    session_data = json.load(f)

                # Check if session is still valid (not expired)
                created_at = datetime.fromisoformat(session_data['created_at'])
                session_timeout = int(os.getenv('PROCLAIM_SESSION_TIMEOUT_HOURS', '6'))

                if datetime.now() - created_at > timedelta(hours=session_timeout):
                    logger.warning("Session expired, clearing old session")
                    self.clear_session()
                    return None

                # Update last used timestamp
                session_data['last_used'] = datetime.now().isoformat()
                with open(self.session_file, 'w') as f:
                    json.dump(session_data, f, indent=2)

                self.session_data = session_data
                logger.debug(f"Session loaded for user {session_data.get('username')}")
                return session_data

            except Exception as e:
                logger.error(f"Failed to load session: {e}")
                self.clear_session()
                return None

    def clear_session(self) -> None:
        """Clear session from persistent storage."""
        with self._lock:
            try:
                if os.path.exists(self.session_file):
                    os.remove(self.session_file)
                    logger.info("Session file cleared")

                self.session_data = None

            except Exception as e:
                logger.error(f"Failed to clear session: {e}")

    def get_session_info(self) -> Optional[Dict[str, Any]]:
        """Get current session information.

        Returns:
            Session information including age and validity
        """
        session_data = self.load_session()
        if not session_data:
            return None

        created_at = datetime.fromisoformat(session_data['created_at'])
        last_used = datetime.fromisoformat(session_data['last_used'])
        age_hours = (datetime.now() - created_at).total_seconds() / 3600

        return {
            'username': session_data.get('username'),
            'created_at': session_data['created_at'],
            'last_used': session_data['last_used'],
            'age_hours': age_hours,
            'is_valid': True  # If we got here, session is valid
        }

    def refresh_session(self) -> None:
        """Refresh session last_used timestamp."""
        if self.session_data:
            self.session_data['last_used'] = datetime.now().isoformat()
            with open(self.session_file, 'w') as f:
                json.dump(self.session_data, f, indent=2)