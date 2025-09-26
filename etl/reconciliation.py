"""State reconciliation engine for comparing CRM vs database case states."""

import logging
from typing import Dict, Set, List, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from v2.database.change_tracking import ChangeTracker

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationResult:
    """Results of case state reconciliation between CRM and database."""
    tenant_id: str
    timestamp: str
    crm_active_count: int
    database_active_count: int
    new_cases: List[str]
    deactivated_cases: List[str]
    potential_updates: List[str]
    unchanged_cases: List[str]
    errors: List[str]

    @property
    def summary(self) -> Dict[str, int]:
        """Get summary statistics."""
        return {
            "new": len(self.new_cases),
            "deactivated": len(self.deactivated_cases),
            "updates_needed": len(self.potential_updates),
            "unchanged": len(self.unchanged_cases),
            "total_changes": len(self.new_cases) + len(self.deactivated_cases) + len(self.potential_updates)
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp,
            "crm_active_count": self.crm_active_count,
            "database_active_count": self.database_active_count,
            "new_cases": self.new_cases,
            "deactivated_cases": self.deactivated_cases,
            "potential_updates": self.potential_updates,
            "unchanged_cases": self.unchanged_cases,
            "errors": self.errors,
            "summary": self.summary
        }


class StateReconciliator:
    """Engine for reconciling case states between CRM and database."""

    def __init__(self, tenant_id: str, db_session=None):
        """Initialize state reconciliator.

        Args:
            tenant_id: Tenant identifier
            db_session: Optional database session
        """
        self.tenant_id = tenant_id
        self.change_tracker = ChangeTracker(db_session=db_session)

        logger.info(f"StateReconciliator initialized for tenant {tenant_id}")

    def reconcile_case_lists(
        self,
        crm_cases: List[Dict[str, Any]],
        db_cases: List[Dict[str, Any]]
    ) -> ReconciliationResult:
        """Compare CRM active cases vs database active cases.

        Args:
            crm_cases: Cases from CRM system
            db_cases: Cases from database

        Returns:
            Detailed reconciliation results
        """
        logger.info(f"Starting case reconciliation for tenant {self.tenant_id}")
        timestamp = datetime.utcnow().isoformat()

        errors = []

        try:
            # Extract active case references from both sources
            crm_refs = self._extract_active_case_refs(crm_cases)
            db_refs = self._extract_active_case_refs(db_cases)

            logger.info(f"CRM active cases: {len(crm_refs)}, Database active cases: {len(db_refs)}")

            # Identify different categories of changes
            new_cases = list(crm_refs - db_refs)
            deactivated_cases = list(db_refs - crm_refs)
            potential_updates = list(crm_refs & db_refs)

            logger.info(f"Initial analysis: {len(new_cases)} new, {len(deactivated_cases)} deactivated, "
                       f"{len(potential_updates)} potential updates")

            # Check potential updates using high-watermark change detection
            cases_needing_update, unchanged_cases = self._filter_updates_by_serialno(
                crm_cases, potential_updates
            )

            logger.info(f"After serialno check: {len(cases_needing_update)} need updates, "
                       f"{len(unchanged_cases)} unchanged")

            result = ReconciliationResult(
                tenant_id=self.tenant_id,
                timestamp=timestamp,
                crm_active_count=len(crm_refs),
                database_active_count=len(db_refs),
                new_cases=new_cases,
                deactivated_cases=deactivated_cases,
                potential_updates=cases_needing_update,
                unchanged_cases=unchanged_cases,
                errors=errors
            )

            logger.info(f"Reconciliation completed: {result.summary}")
            return result

        except Exception as e:
            error_msg = f"Reconciliation failed: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

            # Return partial result with error
            return ReconciliationResult(
                tenant_id=self.tenant_id,
                timestamp=timestamp,
                crm_active_count=0,
                database_active_count=0,
                new_cases=[],
                deactivated_cases=[],
                potential_updates=[],
                unchanged_cases=[],
                errors=errors
            )

    def _extract_active_case_refs(self, cases: List[Dict[str, Any]]) -> Set[str]:
        """Extract active case references from case list.

        Args:
            cases: List of case dictionaries

        Returns:
            Set of active case references
        """
        active_refs = set()

        for case in cases:
            # Check various possible fields for active status
            is_active = (
                case.get("is_active", True) and
                case.get("status", "").lower() != "closed" and
                case.get("status", "").lower() != "complete"
            )

            if is_active:
                case_ref = case.get("case_ref")
                if case_ref:
                    active_refs.add(str(case_ref))

        return active_refs

    def _filter_updates_by_serialno(
        self,
        crm_cases: List[Dict[str, Any]],
        potential_updates: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Filter potential updates using serial number comparison.

        Args:
            crm_cases: Cases from CRM system
            potential_updates: List of case references that might need updates

        Returns:
            Tuple of (cases_needing_update, unchanged_cases)
        """
        if not potential_updates:
            return [], []

        try:
            # Create lookup dictionary for CRM case serial numbers
            crm_serialnos = {}
            for case in crm_cases:
                case_ref = case.get("case_ref")
                serialno = case.get("serialno", 0)
                if case_ref:
                    crm_serialnos[str(case_ref)] = serialno

            # Batch check changes using ChangeTracker
            relevant_serialnos = {
                case_ref: crm_serialnos.get(case_ref, 0)
                for case_ref in potential_updates
            }

            change_results = self.change_tracker.batch_check_changes(
                self.tenant_id, relevant_serialnos
            )

            # Split into cases needing update vs unchanged
            cases_needing_update = [
                case_ref for case_ref, needs_update in change_results.items()
                if needs_update
            ]

            unchanged_cases = [
                case_ref for case_ref, needs_update in change_results.items()
                if not needs_update
            ]

            logger.debug(f"Serial number filtering: {len(cases_needing_update)} need updates, "
                        f"{len(unchanged_cases)} unchanged")

            return cases_needing_update, unchanged_cases

        except Exception as e:
            logger.error(f"Error filtering updates by serialno: {e}")
            # Conservative fallback - assume all need updates
            return potential_updates, []

    def mark_cases_inactive(self, case_refs: List[str]) -> int:
        """Mark deactivated cases as inactive in database.

        Args:
            case_refs: List of case references to deactivate

        Returns:
            Number of cases successfully marked inactive
        """
        if not case_refs:
            return 0

        logger.info(f"Marking {len(case_refs)} cases as inactive")

        try:
            from v2.database.alembic_setup import get_postgres_url
            from sqlalchemy import create_engine, text

            engine = create_engine(get_postgres_url())

            with engine.connect() as conn:
                # Update cases to mark as inactive
                query = text("""
                    UPDATE cases
                    SET is_active = FALSE,
                        status = 'inactive',
                        updated_at = :updated_at
                    WHERE tenant_id = :tenant_id AND case_ref = ANY(:case_refs)
                """)

                result = conn.execute(query, {
                    "updated_at": datetime.utcnow(),
                    "tenant_id": self.tenant_id,
                    "case_refs": case_refs
                })

                rows_affected = result.rowcount
                logger.info(f"Marked {rows_affected} cases as inactive")
                return rows_affected

        except Exception as e:
            logger.error(f"Failed to mark cases inactive: {e}")
            return 0

    def generate_reconciliation_report(self, result: ReconciliationResult) -> str:
        """Generate human-readable reconciliation report.

        Args:
            result: Reconciliation results

        Returns:
            Formatted report string
        """
        report = f"""
Case State Reconciliation Report
Tenant: {result.tenant_id}
Generated: {result.timestamp}

SUMMARY
=======
CRM Active Cases: {result.crm_active_count:,}
Database Active Cases: {result.database_active_count:,}
Total Changes Identified: {result.summary['total_changes']:,}

CHANGE BREAKDOWN
================
New Cases (need full processing): {result.summary['new']:,}
Deactivated Cases (mark inactive): {result.summary['deactivated']:,}
Updated Cases (incremental sync): {result.summary['updates_needed']:,}
Unchanged Cases (no action): {result.summary['unchanged']:,}

EFFICIENCY METRICS
==================
Change Rate: {(result.summary['total_changes'] / max(result.crm_active_count, 1) * 100):.1f}%
Processing Reduction: {(result.summary['unchanged'] / max(result.crm_active_count, 1) * 100):.1f}%
"""

        # Add error information if present
        if result.errors:
            report += f"\nERRORS\n======\n"
            for i, error in enumerate(result.errors, 1):
                report += f"{i}. {error}\n"

        # Add sample case references for verification
        if result.new_cases:
            sample_new = result.new_cases[:5]
            report += f"\nSample New Cases: {', '.join(sample_new)}"
            if len(result.new_cases) > 5:
                report += f" (+{len(result.new_cases) - 5} more)"

        if result.potential_updates:
            sample_updates = result.potential_updates[:5]
            report += f"\nSample Updates: {', '.join(sample_updates)}"
            if len(result.potential_updates) > 5:
                report += f" (+{len(result.potential_updates) - 5} more)"

        return report.strip()

    def validate_reconciliation_quality(self, result: ReconciliationResult) -> Dict[str, Any]:
        """Validate the quality and reasonableness of reconciliation results.

        Args:
            result: Reconciliation results to validate

        Returns:
            Validation report with quality metrics
        """
        validation = {
            "tenant_id": result.tenant_id,
            "validation_timestamp": datetime.utcnow().isoformat(),
            "quality_score": 1.0,  # Start with perfect score
            "warnings": [],
            "quality_checks": {}
        }

        try:
            # Check 1: Reasonable change rate (expect < 20% changes per day)
            total_cases = max(result.crm_active_count, result.database_active_count)
            if total_cases > 0:
                change_rate = result.summary['total_changes'] / total_cases

                validation["quality_checks"]["change_rate"] = {
                    "value": change_rate,
                    "threshold": 0.20,
                    "status": "normal" if change_rate <= 0.20 else "high"
                }

                if change_rate > 0.20:
                    validation["warnings"].append(f"High change rate: {change_rate:.1%} (expected < 20%)")
                    validation["quality_score"] -= 0.2

            # Check 2: Data consistency (CRM and DB case counts should be similar)
            if result.crm_active_count > 0 and result.database_active_count > 0:
                count_ratio = abs(result.crm_active_count - result.database_active_count) / result.crm_active_count

                validation["quality_checks"]["count_consistency"] = {
                    "crm_count": result.crm_active_count,
                    "db_count": result.database_active_count,
                    "difference_ratio": count_ratio,
                    "status": "normal" if count_ratio <= 0.10 else "inconsistent"
                }

                if count_ratio > 0.10:
                    validation["warnings"].append(f"Case count mismatch: {count_ratio:.1%} difference")
                    validation["quality_score"] -= 0.3

            # Check 3: Error rate
            if result.errors:
                validation["quality_checks"]["error_count"] = {
                    "errors": len(result.errors),
                    "status": "errors_present"
                }
                validation["quality_score"] -= 0.4

            # Check 4: Completeness (no empty results without explanation)
            if (result.crm_active_count == 0 and result.database_active_count == 0 and
                not result.errors):
                validation["warnings"].append("Empty reconciliation result - verify data sources")
                validation["quality_score"] -= 0.3

            # Final quality assessment
            if validation["quality_score"] >= 0.8:
                validation["overall_quality"] = "excellent"
            elif validation["quality_score"] >= 0.6:
                validation["overall_quality"] = "good"
            elif validation["quality_score"] >= 0.4:
                validation["overall_quality"] = "fair"
            else:
                validation["overall_quality"] = "poor"

            logger.info(f"Reconciliation quality: {validation['overall_quality']} "
                       f"(score: {validation['quality_score']:.1f})")

            return validation

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            validation["errors"] = [f"Validation error: {str(e)}"]
            validation["overall_quality"] = "unknown"
            return validation


# Utility functions for reconciliation
def create_state_reconciliator(tenant_id: str, db_session=None) -> StateReconciliator:
    """Create a state reconciliator instance.

    Args:
        tenant_id: Tenant identifier
        db_session: Optional database session

    Returns:
        Configured StateReconciliator instance
    """
    return StateReconciliator(tenant_id=tenant_id, db_session=db_session)


def reconcile_tenant_cases(
    tenant_id: str,
    crm_cases: List[Dict[str, Any]],
    db_cases: List[Dict[str, Any]],
    mark_inactive: bool = False
) -> ReconciliationResult:
    """High-level function to reconcile cases for a tenant.

    Args:
        tenant_id: Tenant identifier
        crm_cases: Cases from CRM system
        db_cases: Cases from database
        mark_inactive: Whether to mark deactivated cases as inactive

    Returns:
        Reconciliation results
    """
    reconciliator = create_state_reconciliator(tenant_id)

    # Perform reconciliation
    result = reconciliator.reconcile_case_lists(crm_cases, db_cases)

    # Optionally mark deactivated cases as inactive
    if mark_inactive and result.deactivated_cases:
        marked_inactive = reconciliator.mark_cases_inactive(result.deactivated_cases)
        logger.info(f"Marked {marked_inactive} cases as inactive")

    return result