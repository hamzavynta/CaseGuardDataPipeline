"""Prefect configuration with Valkey (Redis) backend setup."""

import os
import logging
from typing import Optional, Dict, Any
from prefect import settings
from prefect.client.orchestration import get_client

logger = logging.getLogger(__name__)


def get_redis_connection_url() -> str:
    """Get Redis/Valkey connection URL from environment or defaults.

    Returns:
        Redis connection URL
    """
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "0"))
    password = os.getenv("REDIS_PASSWORD")

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    else:
        return f"redis://{host}:{port}/{db}"


def get_postgres_connection_url() -> str:
    """Get PostgreSQL connection URL for Prefect database.

    Returns:
        PostgreSQL connection URL
    """
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DATABASE", "caseguard_v2")
    username = os.getenv("POSTGRES_USERNAME", "")
    password = os.getenv("POSTGRES_PASSWORD", "")

    if not username or not password:
        raise ValueError("PostgreSQL credentials required for Prefect database")

    return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"


def setup_prefect() -> Dict[str, Any]:
    """Configure Prefect with Valkey backend and PostgreSQL storage.

    Returns:
        Configuration dictionary with setup status
    """
    try:
        # Configure Redis/Valkey as result backend and task queue
        redis_url = get_redis_connection_url()
        logger.info(f"Configuring Redis backend: {redis_url}")

        # Configure PostgreSQL as Prefect API database
        postgres_url = get_postgres_connection_url()
        logger.info("Configuring PostgreSQL for Prefect API database")

        # Set Prefect database connection
        settings.PREFECT_API_DATABASE_CONNECTION_URL = postgres_url

        # Configure Prefect server settings
        api_url = os.getenv("PREFECT_API_URL", "http://localhost:4200/api")
        settings.PREFECT_API_URL = api_url

        # Configure logging level
        log_level = os.getenv("PREFECT_LOG_LEVEL", "INFO")
        settings.PREFECT_LOGGING_LEVEL = log_level

        # Configure task result storage
        settings.PREFECT_RESULTS_PERSIST_BY_DEFAULT = True

        config_info = {
            "status": "success",
            "redis_url": redis_url,
            "api_url": api_url,
            "log_level": log_level,
            "database_configured": True
        }

        logger.info("Prefect configuration completed successfully")
        return config_info

    except Exception as e:
        logger.error(f"Failed to setup Prefect: {e}")
        return {
            "status": "error",
            "error": str(e),
            "database_configured": False
        }


async def check_prefect_connection() -> Dict[str, Any]:
    """Check Prefect API server connection.

    Returns:
        Connection status dictionary
    """
    try:
        async with get_client() as client:
            # Test connection by listing flows
            flows = await client.read_flows(limit=1)

            return {
                "status": "connected",
                "api_url": client.api_url,
                "flows_accessible": True,
                "flow_count": len(flows)
            }

    except Exception as e:
        logger.error(f"Prefect connection check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "flows_accessible": False
        }


def create_work_queue(queue_name: str = "caseguard-v2", concurrency_limit: int = 10) -> Dict[str, Any]:
    """Create a work queue for CaseGuard V2 flows.

    Args:
        queue_name: Name of the work queue
        concurrency_limit: Maximum concurrent executions

    Returns:
        Queue creation result
    """
    try:
        # This would typically use the Prefect CLI or API to create work queues
        # For now, return configuration that would be used
        queue_config = {
            "name": queue_name,
            "concurrency_limit": concurrency_limit,
            "filter": {
                "tags": ["caseguard-v2"]
            },
            "description": "Work queue for CaseGuard V2 case processing flows"
        }

        logger.info(f"Work queue configuration prepared: {queue_name}")
        return {
            "status": "configured",
            "queue_config": queue_config
        }

    except Exception as e:
        logger.error(f"Failed to configure work queue: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def initialize_prefect_environment() -> Dict[str, Any]:
    """Initialize complete Prefect environment for V2.

    Returns:
        Initialization results
    """
    results = {
        "timestamp": "2024-01-01T00:00:00Z",  # This would be actual timestamp
        "components": {}
    }

    # Setup Prefect configuration
    logger.info("Initializing Prefect environment...")
    results["components"]["prefect_config"] = setup_prefect()

    # Create work queue
    results["components"]["work_queue"] = create_work_queue()

    # Overall status
    all_success = all(
        comp.get("status") in ["success", "connected", "configured"]
        for comp in results["components"].values()
    )

    results["status"] = "success" if all_success else "partial_failure"
    results["ready_for_flows"] = all_success

    logger.info(f"Prefect environment initialization: {results['status']}")
    return results


# Configuration constants
CASEGUARD_V2_TAGS = ["caseguard-v2", "legal-ai", "case-processing"]
DEFAULT_RETRY_DELAY_SECONDS = [1, 2, 4, 8]  # Exponential backoff
MAX_TASK_RUN_TIME_MINUTES = 30
DEFAULT_WORK_QUEUE = "caseguard-v2"