"""Enhanced daily synchronization with comprehensive state reconciliation."""

import json
import logging
from typing import Dict, Any, List
from datetime import datetime

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from v2.etl.prefect_config import CASEGUARD_V2_TAGS, DEFAULT_RETRY_DELAY_SECONDS
from v2.crm.discovery import create_case_discovery_adapter
from v2.etl.reconciliation import create_state_reconciliator

logger = logging.getLogger(__name__)


@task(
    name="load_tenant_config",
    description="Load tenant configuration for sync operations",
    tags=CASEGUARD_V2_TAGS,
    timeout_seconds=60
)
def load_tenant_config(tenant_id: str) -> Dict[str, Any]:
    """Load tenant-specific configuration.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tenant configuration dictionary
    """
    task_logger = get_run_logger()
    task_logger.info(f"Loading configuration for tenant {tenant_id}")

    try:
        from pathlib import Path
        config_path = Path(f"v2/configs/tenants/{tenant_id}.json")

        if not config_path.exists():
            # Return default configuration
            task_logger.warning(f"Config file not found for {tenant_id}, using defaults")
            return {
                "tenant_id": tenant_id,
                "crm_config": {
                    "case_discovery": {
                        "adapter": "YAMLFallbackAdapter"
                    }
                },
                "processing_config": {
                    "concurrent_limit": 25,
                    "batch_size": 100
                },
                "sync_config": {
                    "validation_enabled": True,
                    "dry_run_before_sync": False
                }
            }

        with open(config_path, 'r') as f:
            config = json.load(f)

        task_logger.info(f"Loaded configuration for {tenant_id}: {config.get('display_name', 'Unknown')}")
        return config

    except Exception as e:
        task_logger.error(f"Failed to load tenant config for {tenant_id}: {e}")
        raise


@task(
    name="get_crm_cases_with_adapter",
    description="Get CRM cases using configured adapter",
    tags=CASEGUARD_V2_TAGS,
    retries=3,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=1800
)
def get_crm_cases_with_adapter(tenant_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get CRM cases using tenant-configured adapter.

    Args:
        tenant_config: Tenant configuration

    Returns:
        List of CRM cases
    """
    task_logger = get_run_logger()
    tenant_id = tenant_config["tenant_id"]

    try:
        # Extract adapter configuration
        crm_config = tenant_config.get("crm_config", {})
        discovery_config = crm_config.get("case_discovery", {})
        adapter_type = discovery_config.get("adapter", "YAMLFallbackAdapter")

        # Create appropriate adapter
        if adapter_type == "CSVFallbackAdapter":
            csv_path = discovery_config.get("fallback_source", "FDM example Funded Cases.csv")
            adapter = create_case_discovery_adapter(
                tenant_id=tenant_id,
                adapter_type="csv",
                csv_path=csv_path
            )
        elif adapter_type == "ProclaimCRMAdapter":
            adapter = create_case_discovery_adapter(
                tenant_id=tenant_id,
                adapter_type="proclaim",
                api_base_url=crm_config.get("api_base_url"),
                credentials=crm_config.get("credentials", {})
            )
        else:
            # Default to YAML
            adapter = create_case_discovery_adapter(
                tenant_id=tenant_id,
                adapter_type="yaml"
            )

        # Get active cases
        crm_cases = adapter.get_active_cases()
        task_logger.info(f"Retrieved {len(crm_cases)} active cases from CRM using {adapter_type}")

        return crm_cases

    except Exception as e:
        task_logger.error(f"Failed to get CRM cases for {tenant_id}: {e}")
        raise


@task(
    name="get_database_cases_enhanced",
    description="Get database cases with enhanced filtering",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=600
)
def get_database_cases_enhanced(tenant_id: str) -> List[Dict[str, Any]]:
    """Get database cases with enhanced filtering and metadata.

    Args:
        tenant_id: Tenant identifier

    Returns:
        List of database cases with enhanced metadata
    """
    task_logger = get_run_logger()
    task_logger.info(f"Querying enhanced database cases for {tenant_id}")

    try:
        from v2.database.alembic_setup import get_postgres_url
        from sqlalchemy import create_engine, text

        engine = create_engine(get_postgres_url())

        with engine.connect() as conn:
            # Enhanced query with additional metadata
            query = text("""
                SELECT
                    case_ref,
                    tenant_id,
                    status,
                    is_active,
                    last_serialno,
                    updated_at,
                    created_at,
                    EXTRACT(EPOCH FROM (NOW() - updated_at)) / 3600 as hours_since_update,
                    CASE
                        WHEN last_serialno = 0 THEN 'never_processed'
                        WHEN updated_at > NOW() - INTERVAL '24 hours' THEN 'recent'
                        WHEN updated_at > NOW() - INTERVAL '7 days' THEN 'moderate'
                        ELSE 'stale'
                    END as freshness_status
                FROM cases
                WHERE tenant_id = :tenant_id AND is_active = TRUE
                ORDER BY updated_at DESC
            """)

            result = conn.execute(query, {"tenant_id": tenant_id})
            rows = result.fetchall()

            # Convert to list of dictionaries
            db_cases = []
            for row in rows:
                case = {
                    "case_ref": row[0],
                    "tenant_id": row[1],
                    "status": row[2],
                    "is_active": row[3],
                    "last_serialno": row[4] or 0,
                    "updated_at": row[5].isoformat() if row[5] else None,
                    "created_at": row[6].isoformat() if row[6] else None,
                    "hours_since_update": float(row[7]) if row[7] else 0,
                    "freshness_status": row[8],
                    "source": "caseguard_database"
                }
                db_cases.append(case)

        task_logger.info(f"Retrieved {len(db_cases)} active cases from database")

        # Log freshness statistics
        freshness_stats = {}
        for case in db_cases:
            status = case["freshness_status"]
            freshness_stats[status] = freshness_stats.get(status, 0) + 1

        task_logger.info(f"Case freshness distribution: {freshness_stats}")

        return db_cases

    except Exception as e:
        task_logger.error(f"Failed to query database cases for {tenant_id}: {e}")
        raise


@task(
    name="perform_enhanced_reconciliation",
    description="Perform comprehensive state reconciliation with validation",
    tags=CASEGUARD_V2_TAGS,
    timeout_seconds=900
)
def perform_enhanced_reconciliation(
    tenant_id: str,
    crm_cases: List[Dict[str, Any]],
    db_cases: List[Dict[str, Any]],
    validation_enabled: bool = True
) -> Dict[str, Any]:
    """Perform enhanced reconciliation with validation.

    Args:
        tenant_id: Tenant identifier
        crm_cases: Cases from CRM
        db_cases: Cases from database
        validation_enabled: Whether to validate reconciliation quality

    Returns:
        Enhanced reconciliation results
    """
    task_logger = get_run_logger()
    task_logger.info(f"Performing enhanced reconciliation for {tenant_id}")

    try:
        # Create reconciliator and perform reconciliation
        reconciliator = create_state_reconciliator(tenant_id)
        result = reconciliator.reconcile_case_lists(crm_cases, db_cases)

        # Convert to dictionary for flow return
        reconciliation_data = result.to_dict()

        # Add validation if enabled
        if validation_enabled:
            task_logger.info("Validating reconciliation quality")
            validation = reconciliator.validate_reconciliation_quality(result)
            reconciliation_data["validation"] = validation

            # Log validation results
            task_logger.info(f"Reconciliation quality: {validation.get('overall_quality', 'unknown')} "
                           f"(score: {validation.get('quality_score', 0):.1f})")

            if validation.get("warnings"):
                for warning in validation["warnings"]:
                    task_logger.warning(f"Reconciliation warning: {warning}")

        # Generate and log report
        report = reconciliator.generate_reconciliation_report(result)
        task_logger.info(f"Reconciliation report:\n{report}")

        return reconciliation_data

    except Exception as e:
        task_logger.error(f"Enhanced reconciliation failed for {tenant_id}: {e}")
        raise


@task(
    name="queue_sync_jobs_enhanced",
    description="Queue sync jobs with enhanced prioritization and batching",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=1200
)
def queue_sync_jobs_enhanced(
    tenant_id: str,
    reconciliation: Dict[str, Any],
    batch_size: int = 100
) -> Dict[str, Any]:
    """Queue sync jobs with enhanced prioritization.

    Args:
        tenant_id: Tenant identifier
        reconciliation: Reconciliation results
        batch_size: Batch size for job queuing

    Returns:
        Enhanced queuing results
    """
    task_logger = get_run_logger()
    task_logger.info("Queuing sync jobs with enhanced prioritization")

    try:
        import redis
        from v2.etl.prefect_config import get_redis_connection_url

        redis_client = redis.from_url(get_redis_connection_url(), decode_responses=True)

        queuing_results = {
            "tenant_id": tenant_id,
            "queued_at": datetime.utcnow().isoformat(),
            "batching": {
                "batch_size": batch_size,
                "batches_created": 0
            },
            "prioritization": {
                "high_priority": 0,
                "medium_priority": 0,
                "low_priority": 0
            },
            "jobs": {
                "new_cases_queued": 0,
                "updates_queued": 0,
                "total_queued": 0,
                "failures": 0
            }
        }

        # Queue new cases (high priority - full rebuild required)
        new_cases = reconciliation.get("new_cases", [])
        for i in range(0, len(new_cases), batch_size):
            batch = new_cases[i:i + batch_size]
            batch_id = f"new_cases_batch_{i//batch_size + 1}"

            for case_ref in batch:
                try:
                    job_data = {
                        "tenant_id": tenant_id,
                        "case_ref": case_ref,
                        "is_full_rebuild": True,
                        "job_type": "sync_new_case",
                        "priority": 1,  # High priority
                        "batch_id": batch_id,
                        "queued_at": datetime.utcnow().isoformat(),
                        "source": "enhanced_daily_sync"
                    }

                    redis_client.lpush("case_processing_queue:priority:1", json.dumps(job_data))
                    queuing_results["jobs"]["new_cases_queued"] += 1
                    queuing_results["prioritization"]["high_priority"] += 1

                except Exception as e:
                    task_logger.error(f"Failed to queue new case {case_ref}: {e}")
                    queuing_results["jobs"]["failures"] += 1

            queuing_results["batching"]["batches_created"] += 1

        # Queue updates (medium priority - incremental processing)
        update_cases = reconciliation.get("potential_updates", [])
        for i in range(0, len(update_cases), batch_size):
            batch = update_cases[i:i + batch_size]
            batch_id = f"updates_batch_{i//batch_size + 1}"

            for case_ref in batch:
                try:
                    job_data = {
                        "tenant_id": tenant_id,
                        "case_ref": case_ref,
                        "is_full_rebuild": False,
                        "job_type": "sync_update_case",
                        "priority": 2,  # Medium priority
                        "batch_id": batch_id,
                        "queued_at": datetime.utcnow().isoformat(),
                        "source": "enhanced_daily_sync"
                    }

                    redis_client.lpush("case_processing_queue:priority:2", json.dumps(job_data))
                    queuing_results["jobs"]["updates_queued"] += 1
                    queuing_results["prioritization"]["medium_priority"] += 1

                except Exception as e:
                    task_logger.error(f"Failed to queue update case {case_ref}: {e}")
                    queuing_results["jobs"]["failures"] += 1

            queuing_results["batching"]["batches_created"] += 1

        # Mark deactivated cases (if any)
        deactivated_cases = reconciliation.get("deactivated_cases", [])
        if deactivated_cases:
            # Use reconciliator to mark cases inactive
            from v2.etl.reconciliation import create_state_reconciliator
            reconciliator = create_state_reconciliator(tenant_id)
            marked_inactive = reconciliator.mark_cases_inactive(deactivated_cases)
            task_logger.info(f"Marked {marked_inactive} cases as inactive")

        # Calculate totals
        queuing_results["jobs"]["total_queued"] = (
            queuing_results["jobs"]["new_cases_queued"] +
            queuing_results["jobs"]["updates_queued"]
        )

        task_logger.info(f"Enhanced job queuing completed: {queuing_results['jobs']['total_queued']} jobs queued "
                        f"in {queuing_results['batching']['batches_created']} batches")

        return queuing_results

    except Exception as e:
        task_logger.error(f"Enhanced job queuing failed: {e}")
        raise


@flow(
    name="sync_tenant_daily_enhanced",
    description="Enhanced daily synchronization with comprehensive state reconciliation",
    tags=CASEGUARD_V2_TAGS,
    task_runner=ConcurrentTaskRunner(),
    timeout_seconds=7200,  # 2 hours
    retries=1,
    retry_delay_seconds=900  # 15 minutes
)
def sync_tenant_daily_enhanced(
    tenant_id: str,
    dry_run: bool = False,
    force_validation: bool = True
) -> Dict[str, Any]:
    """Enhanced daily synchronization with comprehensive state reconciliation.

    This enhanced flow provides:
    - Tenant-specific configuration loading
    - Adaptive CRM adapter selection
    - Comprehensive state reconciliation
    - Quality validation
    - Enhanced job prioritization and batching
    - Detailed reporting and metrics

    Args:
        tenant_id: Law firm tenant identifier
        dry_run: If True, perform reconciliation but don't queue jobs
        force_validation: Force validation even if disabled in config

    Returns:
        Enhanced sync results with detailed metrics
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Starting enhanced daily sync for tenant {tenant_id}")

    start_time = datetime.utcnow()
    sync_results = {
        "tenant_id": tenant_id,
        "sync_type": "enhanced_daily",
        "dry_run": dry_run,
        "started_at": start_time.isoformat(),
        "steps_completed": [],
        "configuration": {},
        "metrics": {},
        "final_status": "in_progress"
    }

    try:
        # Step 1: Load tenant configuration
        flow_logger.info("Step 1: Loading tenant configuration")
        tenant_config = load_tenant_config(tenant_id)
        sync_results["configuration"] = tenant_config
        sync_results["steps_completed"].append("config_loaded")

        # Extract sync configuration
        sync_config = tenant_config.get("sync_config", {})
        validation_enabled = force_validation or sync_config.get("validation_enabled", True)
        batch_size = tenant_config.get("processing_config", {}).get("batch_size", 100)

        # Step 2: Get CRM cases using configured adapter
        flow_logger.info("Step 2: Fetching CRM cases with adapter")
        crm_cases = get_crm_cases_with_adapter(tenant_config)
        sync_results["metrics"]["crm_cases_count"] = len(crm_cases)
        sync_results["steps_completed"].append("crm_fetch")

        # Step 3: Get enhanced database cases
        flow_logger.info("Step 3: Querying enhanced database cases")
        db_cases = get_database_cases_enhanced(tenant_id)
        sync_results["metrics"]["database_cases_count"] = len(db_cases)
        sync_results["steps_completed"].append("database_query")

        # Step 4: Perform enhanced reconciliation
        flow_logger.info("Step 4: Performing enhanced reconciliation")
        reconciliation = perform_enhanced_reconciliation(
            tenant_id, crm_cases, db_cases, validation_enabled
        )
        sync_results["reconciliation"] = reconciliation
        sync_results["steps_completed"].append("reconciliation")

        # Step 5: Queue jobs (unless dry run)
        if not dry_run:
            flow_logger.info("Step 5: Queuing enhanced sync jobs")
            queuing_results = queue_sync_jobs_enhanced(tenant_id, reconciliation, batch_size)
            sync_results["queuing_results"] = queuing_results
            sync_results["steps_completed"].append("job_queuing")
        else:
            flow_logger.info("Step 5: Skipping job queuing (dry run mode)")
            sync_results["queuing_results"] = {
                "message": "Skipped due to dry_run=True",
                "would_queue": reconciliation.get("summary", {}).get("total_changes", 0)
            }

        # Calculate final metrics and results
        end_time = datetime.utcnow()
        sync_duration = (end_time - start_time).total_seconds()

        # Enhanced efficiency metrics
        crm_count = sync_results["metrics"]["crm_cases_count"]
        total_changes = reconciliation.get("summary", {}).get("total_changes", 0)

        sync_results.update({
            "completed_at": end_time.isoformat(),
            "sync_duration_seconds": sync_duration,
            "final_status": "completed",
            "enhanced_metrics": {
                "processing_efficiency": {
                    "total_cases_analyzed": crm_count + sync_results["metrics"]["database_cases_count"],
                    "changes_identified": total_changes,
                    "efficiency_ratio": (crm_count - total_changes) / max(crm_count, 1),
                    "processing_reduction_percent": ((crm_count - total_changes) / max(crm_count, 1)) * 100
                },
                "quality_metrics": reconciliation.get("validation", {}),
                "batching_efficiency": sync_results.get("queuing_results", {}).get("batching", {}),
                "sync_performance": {
                    "duration_seconds": sync_duration,
                    "cases_per_second": crm_count / max(sync_duration, 1),
                    "changes_per_second": total_changes / max(sync_duration, 1)
                }
            }
        })

        flow_logger.info(f"Enhanced daily sync completed successfully in {sync_duration:.1f}s")
        flow_logger.info(f"Efficiency: {sync_results['enhanced_metrics']['processing_efficiency']['processing_reduction_percent']:.1f}% reduction in processing")

        return sync_results

    except Exception as e:
        end_time = datetime.utcnow()
        sync_duration = (end_time - start_time).total_seconds()

        error_result = {
            **sync_results,
            "completed_at": end_time.isoformat(),
            "sync_duration_seconds": sync_duration,
            "final_status": "failed",
            "error": str(e)
        }

        flow_logger.error(f"Enhanced daily sync failed after {sync_duration:.1f}s: {e}")
        flow_logger.error(f"Steps completed before failure: {sync_results['steps_completed']}")

        return error_result