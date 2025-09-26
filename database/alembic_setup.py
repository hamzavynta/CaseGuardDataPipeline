"""Alembic setup for V2 PostgreSQL-only architecture."""

import os
from typing import Optional
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine


def get_postgres_url() -> str:
    """Get PostgreSQL connection URL from environment or config."""
    # Try environment variables first
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DATABASE", "caseguard_v2")
    username = os.getenv("POSTGRES_USERNAME", "")
    password = os.getenv("POSTGRES_PASSWORD", "")

    if not username or not password:
        raise ValueError("PostgreSQL credentials not found. Set POSTGRES_USERNAME and POSTGRES_PASSWORD environment variables.")

    return f"postgresql://{username}:{password}@{host}:{port}/{database}"


def setup_alembic(alembic_ini_path: str = "alembic.ini") -> Config:
    """Initialize Alembic configuration for PostgreSQL.

    Args:
        alembic_ini_path: Path to alembic.ini file

    Returns:
        Configured Alembic Config object
    """
    alembic_cfg = Config(alembic_ini_path)

    # Set PostgreSQL connection URL
    postgres_url = get_postgres_url()
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)

    # Set migration directory
    alembic_cfg.set_main_option("script_location", "v2/database/migrations")

    return alembic_cfg


def initialize_migrations(alembic_ini_path: str = "alembic.ini") -> None:
    """Initialize Alembic migrations directory.

    Args:
        alembic_ini_path: Path to alembic.ini file
    """
    try:
        alembic_cfg = setup_alembic(alembic_ini_path)

        # Initialize migrations directory
        command.init(alembic_cfg, "v2/database/migrations")
        print("✅ Alembic migrations initialized successfully")

    except Exception as e:
        print(f"❌ Failed to initialize Alembic: {e}")
        raise


def create_migration(message: str, alembic_ini_path: str = "alembic.ini") -> None:
    """Create a new migration.

    Args:
        message: Migration message/description
        alembic_ini_path: Path to alembic.ini file
    """
    try:
        alembic_cfg = setup_alembic(alembic_ini_path)
        command.revision(alembic_cfg, message=message, autogenerate=True)
        print(f"✅ Migration created: {message}")

    except Exception as e:
        print(f"❌ Failed to create migration: {e}")
        raise


def upgrade_database(revision: str = "head", alembic_ini_path: str = "alembic.ini") -> None:
    """Upgrade database to specified revision.

    Args:
        revision: Target revision (default: "head")
        alembic_ini_path: Path to alembic.ini file
    """
    try:
        alembic_cfg = setup_alembic(alembic_ini_path)
        command.upgrade(alembic_cfg, revision)
        print(f"✅ Database upgraded to {revision}")

    except Exception as e:
        print(f"❌ Failed to upgrade database: {e}")
        raise


def check_database_connection() -> bool:
    """Test PostgreSQL database connection.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        postgres_url = get_postgres_url()
        engine = create_engine(postgres_url)

        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            assert result.scalar() == 1

        print("✅ PostgreSQL connection successful")
        return True

    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python alembic_setup.py [init|check|migrate <message>|upgrade]")
        sys.exit(1)

    command_arg = sys.argv[1]

    if command_arg == "init":
        initialize_migrations()
    elif command_arg == "check":
        check_database_connection()
    elif command_arg == "migrate" and len(sys.argv) > 2:
        create_migration(sys.argv[2])
    elif command_arg == "upgrade":
        upgrade_database()
    else:
        print("Invalid command. Use: init, check, migrate <message>, or upgrade")
        sys.exit(1)