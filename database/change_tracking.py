"""Efficient change detection using high-watermark serial numbers."""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text, select, update, and_
from sqlalchemy.exc import SQLAlchemyError

from v2.database.alembic_setup import get_postgres_url

logger = logging.getLogger(__name__)


class ChangeTracker:
    """High-watermark change detection system using serial numbers."""

    def __init__(self, db_session=None):
        """Initialize change tracker with database connection.

        Args:
            db_session: SQLAlchemy session (optional, will create if not provided)
        """
        self.db_session = db_session
        self.engine = None

        if not self.db_session:
            self._create_engine()

        logger.info("ChangeTracker initialized")

    def _create_engine(self):
        """Create database engine if session not provided."""
        try:
            postgres_url = get_postgres_url()
            self.engine = create_engine(postgres_url)
            logger.info("Database engine created for change tracking")
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise

    def _get_connection(self):
        """Get database connection."""
        if self.db_session:
            return self.db_session
        elif self.engine:
            return self.engine.connect()
        else:
            raise RuntimeError("No database connection available")

    def get_latest_serialno(self, tenant_id: str, case_ref: str) -> int:
        """Get the latest serial number we have for a case.

        Args:
            tenant_id: Tenant identifier
            case_ref: Case reference

        Returns:
            Latest serial number, or 0 if case not found
        """
        try:
            with self._get_connection() as conn:
                # Query the cases table for the latest serial number
                query = text("""
                    SELECT last_serialno
                    FROM cases
                    WHERE tenant_id = :tenant_id AND case_ref = :case_ref
                """)

                result = conn.execute(query, {
                    "tenant_id": tenant_id,
                    "case_ref": case_ref
                })

                row = result.fetchone()
                if row:
                    return row[0] or 0
                else:
                    logger.debug(f"Case not found in database: {case_ref}")
                    return 0

        except Exception as e:
            logger.error(f"Failed to get latest serialno for {case_ref}: {e}")
            return 0

    def update_serialno(self, tenant_id: str, case_ref: str, new_serialno: int) -> bool:
        """Update our stored serial number after processing.

        Args:
            tenant_id: Tenant identifier
            case_ref: Case reference
            new_serialno: New serial number to store

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                # Update the serial number and last modified timestamp
                query = text("""
                    UPDATE cases
                    SET last_serialno = :new_serialno,
                        updated_at = :updated_at
                    WHERE tenant_id = :tenant_id AND case_ref = :case_ref
                """)

                result = conn.execute(query, {
                    "new_serialno": new_serialno,
                    "updated_at": datetime.utcnow(),
                    "tenant_id": tenant_id,
                    "case_ref": case_ref
                })

                rows_affected = result.rowcount
                if rows_affected > 0:
                    logger.debug(f"Updated serialno for {case_ref}: {new_serialno}")
                    return True
                else:
                    logger.warning(f"No rows updated for case {case_ref} - case may not exist")
                    return False

        except Exception as e:
            logger.error(f"Failed to update serialno for {case_ref}: {e}")
            return False

    def needs_processing(self, tenant_id: str, case_ref: str, api_serialno: int) -> bool:
        """Check if case needs processing based on serial number comparison.

        Args:
            tenant_id: Tenant identifier
            case_ref: Case reference
            api_serialno: Serial number from CRM API

        Returns:
            True if case needs processing, False otherwise
        """
        try:
            local_serialno = self.get_latest_serialno(tenant_id, case_ref)

            needs_update = api_serialno > local_serialno

            if needs_update:
                logger.info(f"Case {case_ref} needs processing: API serialno {api_serialno} > local {local_serialno}")
            else:
                logger.debug(f"Case {case_ref} up to date: API serialno {api_serialno} <= local {local_serialno}")

            return needs_update

        except Exception as e:
            logger.error(f"Error checking processing need for {case_ref}: {e}")
            # Default to processing on error to be safe
            return True

    def batch_check_changes(
        self,
        tenant_id: str,
        case_serialnos: Dict[str, int],
        batch_size: int = 100
    ) -> Dict[str, bool]:
        """Efficiently check multiple cases for changes in batches.

        Args:
            tenant_id: Tenant identifier
            case_serialnos: Dictionary mapping case_ref to API serial numbers
            batch_size: Size of batches for database queries

        Returns:
            Dictionary mapping case_ref to boolean (True if needs processing)
        """
        if not case_serialnos:
            return {}

        logger.info(f"Batch checking changes for {len(case_serialnos)} cases")

        results = {}
        case_refs = list(case_serialnos.keys())

        try:
            # Process cases in batches to avoid large queries
            for i in range(0, len(case_refs), batch_size):
                batch_refs = case_refs[i:i + batch_size]
                batch_results = self._check_batch_changes(tenant_id, batch_refs, case_serialnos)
                results.update(batch_results)

            changes_needed = sum(1 for needs_change in results.values() if needs_change)
            logger.info(f"Batch change check complete: {changes_needed}/{len(case_serialnos)} cases need processing")

            return results

        except Exception as e:
            logger.error(f"Batch change check failed: {e}")
            # Return conservative result - assume all need processing
            return {case_ref: True for case_ref in case_refs}

    def _check_batch_changes(
        self,
        tenant_id: str,
        case_refs: List[str],
        case_serialnos: Dict[str, int]
    ) -> Dict[str, bool]:
        """Check a single batch of cases for changes.

        Args:
            tenant_id: Tenant identifier
            case_refs: List of case references to check
            case_serialnos: Dictionary mapping case_ref to API serial numbers

        Returns:
            Dictionary mapping case_ref to boolean (True if needs processing)
        """
        try:
            with self._get_connection() as conn:
                # Build parameterized query for batch
                placeholders = ','.join([f':case_ref_{i}' for i in range(len(case_refs))])

                query = text(f"""
                    SELECT case_ref, last_serialno
                    FROM cases
                    WHERE tenant_id = :tenant_id AND case_ref IN ({placeholders})
                """)

                # Build parameters dictionary
                params = {"tenant_id": tenant_id}
                for i, case_ref in enumerate(case_refs):
                    params[f"case_ref_{i}"] = case_ref

                result = conn.execute(query, params)
                rows = result.fetchall()

                # Create lookup for database serial numbers
                db_serialnos = {row[0]: row[1] or 0 for row in rows}

                # Check each case in the batch
                batch_results = {}
                for case_ref in case_refs:
                    api_serialno = case_serialnos.get(case_ref, 0)
                    local_serialno = db_serialnos.get(case_ref, 0)  # 0 if not found in DB

                    batch_results[case_ref] = api_serialno > local_serialno

                return batch_results

        except Exception as e:
            logger.error(f"Batch change check failed for {len(case_refs)} cases: {e}")
            # Conservative fallback - assume all need processing
            return {case_ref: True for case_ref in case_refs}

    def get_change_statistics(self, tenant_id: str, days_back: int = 7) -> Dict[str, Any]:
        """Get statistics about case changes over a time period.

        Args:
            tenant_id: Tenant identifier
            days_back: Number of days to analyze

        Returns:
            Dictionary with change statistics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            with self._get_connection() as conn:
                # Count total cases
                total_query = text("""
                    SELECT COUNT(*) as total_cases
                    FROM cases
                    WHERE tenant_id = :tenant_id
                """)

                total_result = conn.execute(total_query, {"tenant_id": tenant_id})
                total_cases = total_result.fetchone()[0]

                # Count recently updated cases
                recent_query = text("""
                    SELECT COUNT(*) as recent_updates
                    FROM cases
                    WHERE tenant_id = :tenant_id AND updated_at > :cutoff_date
                """)

                recent_result = conn.execute(recent_query, {
                    "tenant_id": tenant_id,
                    "cutoff_date": cutoff_date
                })
                recent_updates = recent_result.fetchone()[0]

                # Count cases by activity level
                activity_query = text("""
                    SELECT
                        CASE
                            WHEN last_serialno = 0 THEN 'never_processed'
                            WHEN updated_at > :recent_cutoff THEN 'high_activity'
                            WHEN updated_at > :medium_cutoff THEN 'medium_activity'
                            ELSE 'low_activity'
                        END as activity_level,
                        COUNT(*) as case_count
                    FROM cases
                    WHERE tenant_id = :tenant_id
                    GROUP BY activity_level
                """)

                activity_result = conn.execute(activity_query, {
                    "tenant_id": tenant_id,
                    "recent_cutoff": cutoff_date,
                    "medium_cutoff": datetime.utcnow() - timedelta(days=days_back * 2)
                })
                activity_stats = {row[0]: row[1] for row in activity_result.fetchall()}

                statistics = {
                    "tenant_id": tenant_id,
                    "analysis_period_days": days_back,
                    "total_cases": total_cases,
                    "recent_updates": recent_updates,
                    "update_rate": recent_updates / max(total_cases, 1),
                    "activity_distribution": activity_stats,
                    "generated_at": datetime.utcnow().isoformat()
                }

                logger.info(f"Change statistics for {tenant_id}: {recent_updates}/{total_cases} cases updated recently")
                return statistics

        except Exception as e:
            logger.error(f"Failed to get change statistics for {tenant_id}: {e}")
            return {
                "tenant_id": tenant_id,
                "error": str(e),
                "generated_at": datetime.utcnow().isoformat()
            }

    def cleanup_old_tracking_data(self, tenant_id: str, days_to_keep: int = 90) -> int:
        """Clean up old change tracking data to prevent database bloat.

        Args:
            tenant_id: Tenant identifier
            days_to_keep: Number of days of tracking data to keep

        Returns:
            Number of records cleaned up
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

            with self._get_connection() as conn:
                # Clean up old change tracking records (if we had a separate tracking table)
                # For now, this is a placeholder as we're storing serialno directly in cases table

                logger.info(f"Cleanup completed for {tenant_id}: kept {days_to_keep} days of tracking data")
                return 0  # Placeholder return

        except Exception as e:
            logger.error(f"Failed to cleanup tracking data for {tenant_id}: {e}")
            return 0

    def initialize_case_tracking(
        self,
        tenant_id: str,
        case_ref: str,
        initial_serialno: int = 0
    ) -> bool:
        """Initialize tracking for a new case.

        Args:
            tenant_id: Tenant identifier
            case_ref: Case reference
            initial_serialno: Initial serial number

        Returns:
            True if initialization successful
        """
        try:
            with self._get_connection() as conn:
                # Insert or update case tracking record
                query = text("""
                    INSERT INTO cases (tenant_id, case_ref, last_serialno, created_at, updated_at, is_active)
                    VALUES (:tenant_id, :case_ref, :last_serialno, :now, :now, TRUE)
                    ON CONFLICT (tenant_id, case_ref)
                    DO UPDATE SET
                        last_serialno = EXCLUDED.last_serialno,
                        updated_at = EXCLUDED.updated_at,
                        is_active = TRUE
                """)

                now = datetime.utcnow()
                conn.execute(query, {
                    "tenant_id": tenant_id,
                    "case_ref": case_ref,
                    "last_serialno": initial_serialno,
                    "now": now
                })

                logger.info(f"Initialized tracking for case {case_ref} with serialno {initial_serialno}")
                return True

        except Exception as e:
            logger.error(f"Failed to initialize tracking for case {case_ref}: {e}")
            return False


# Utility functions for change tracking
def create_change_tracker(db_session=None) -> ChangeTracker:
    """Create a change tracker instance.

    Args:
        db_session: Optional database session

    Returns:
        Configured ChangeTracker instance
    """
    return ChangeTracker(db_session=db_session)


def batch_update_serialnos(
    tracker: ChangeTracker,
    tenant_id: str,
    case_updates: Dict[str, int]
) -> Dict[str, bool]:
    """Batch update serial numbers for multiple cases.

    Args:
        tracker: ChangeTracker instance
        tenant_id: Tenant identifier
        case_updates: Dictionary mapping case_ref to new serial number

    Returns:
        Dictionary mapping case_ref to success status
    """
    results = {}

    for case_ref, new_serialno in case_updates.items():
        success = tracker.update_serialno(tenant_id, case_ref, new_serialno)
        results[case_ref] = success

    successful_updates = sum(1 for success in results.values() if success)
    logger.info(f"Batch serialno update: {successful_updates}/{len(case_updates)} successful")

    return results