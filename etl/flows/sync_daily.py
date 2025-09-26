"""Daily synchronization flow with efficient change detection and processing."""

import json
import logging
from typing import Dict, Any, List, Set
from datetime import datetime, timedelta

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from v2.etl.prefect_config import CASEGUARD_V2_TAGS, DEFAULT_RETRY_DELAY_SECONDS

logger = logging.getLogger(__name__)


@task(
    name="get_crm_active_cases_list",
    description="Get current active cases from CRM system",
    tags=CASEGUARD_V2_TAGS,
    retries=3,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=1800  # 30 minutes
)
def get_crm_active_cases_list(tenant_id: str) -> List[Dict[str, Any]]:
    """Get current active cases from CRM system.

    Args:
        tenant_id: Law firm tenant identifier

    Returns:
        List of active cases from CRM with metadata
    """
    task_logger = get_run_logger()
    task_logger.info(f"Fetching active cases from CRM for tenant {tenant_id}")

    try:
        # NOTE: This requires CRM API extension - currently not available
        # For now, simulate CRM case discovery
        task_logger.warning("Using simulated CRM data - real API endpoints not yet available")

        # Simulate active cases based on tenant
        if tenant_id == "fdm_solicitors":
            # Based on FDM CSV: 1037 active cases
            active_cases = []
            for i in range(1, 1038):
                case_ref = f"FDM{i:04d}"
                active_cases.append({
                    "case_ref": case_ref,
                    "tenant_id": tenant_id,
                    "status": "active",
                    "last_modified": datetime.utcnow().isoformat(),
                    "serialno": i + 10000,  # Simulate serial numbers
                    "source": "crm_simulation"
                })

            task_logger.info(f"Fetched {len(active_cases)} active cases from CRM")
            return active_cases

        else:
            # Default simulation for other tenants
            active_cases = []
            for i in range(1, 251):  # 250 active cases
                case_ref = f"{tenant_id.upper()}{i:04d}"
                active_cases.append({
                    "case_ref": case_ref,
                    "tenant_id": tenant_id,
                    "status": "active",
                    "last_modified": datetime.utcnow().isoformat(),
                    "serialno": i + 5000,
                    "source": "crm_simulation"
                })

            task_logger.info(f"Fetched {len(active_cases)} active cases from CRM")
            return active_cases

    except Exception as e:
        task_logger.error(f"Failed to fetch CRM active cases for {tenant_id}: {e}")
        raise


@task(
    name="get_caseguard_active_cases_list",
    description="Query PostgreSQL for current active cases in CaseGuard",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=600  # 10 minutes
)
def get_caseguard_active_cases_list(tenant_id: str) -> List[Dict[str, Any]]:
    """Query PostgreSQL for our current active cases.

    Args:
        tenant_id: Law firm tenant identifier

    Returns:
        List of active cases in CaseGuard database
    """
    task_logger = get_run_logger()
    task_logger.info(f"Querying CaseGuard database for active cases - tenant {tenant_id}")

    try:
        # Import V2 database queries (to be implemented)
        # from v2.database.queries import get_active_cases

        # For now, simulate database query results
        task_logger.warning("Using simulated database data - real queries not yet implemented")

        # Simulate existing cases in our database (slightly fewer than CRM to show sync needed)
        caseguard_cases = []

        if tenant_id == "fdm_solicitors":
            # Simulate that we have most but not all cases, some may be outdated
            for i in range(1, 1025):  # Missing last 13 cases to show sync gap
                case_ref = f"FDM{i:04d}"
                caseguard_cases.append({
                    "case_ref": case_ref,
                    "tenant_id": tenant_id,
                    "status": "active",
                    "is_active": True,
                    "last_updated": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "last_serialno": i + 9990,  # Slightly behind CRM serial numbers
                    "source": "caseguard_database"
                })

        else:
            # Default simulation
            for i in range(1, 240):  # Missing 10 cases
                case_ref = f"{tenant_id.upper()}{i:04d}"
                caseguard_cases.append({
                    "case_ref": case_ref,
                    "tenant_id": tenant_id,
                    "status": "active",
                    "is_active": True,
                    "last_updated": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                    "last_serialno": i + 4990,
                    "source": "caseguard_database"
                })

        task_logger.info(f"Found {len(caseguard_cases)} active cases in CaseGuard database")
        return caseguard_cases

    except Exception as e:
        task_logger.error(f"Failed to query CaseGuard database for {tenant_id}: {e}")
        raise


@task(
    name="reconcile_case_states",
    description="Compare CRM and CaseGuard case states to identify changes",
    tags=CASEGUARD_V2_TAGS,
    timeout_seconds=300  # 5 minutes
)
def reconcile_case_states(
    crm_cases: List[Dict[str, Any]],
    caseguard_cases: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare states and identify new/deactivated/updated cases.

    Args:
        crm_cases: Active cases from CRM system
        caseguard_cases: Active cases from CaseGuard database

    Returns:
        Reconciliation results with categorized changes
    """
    task_logger = get_run_logger()
    task_logger.info("Reconciling case states between CRM and CaseGuard")

    try:
        # Create sets for comparison
        crm_refs = {case["case_ref"] for case in crm_cases if case.get("status") == "active"}
        caseguard_refs = {case["case_ref"] for case in caseguard_cases if case.get("is_active", True)}

        # Identify different categories of changes
        new_cases = list(crm_refs - caseguard_refs)
        deactivated_cases = list(caseguard_refs - crm_refs)
        potential_updates = list(crm_refs & caseguard_refs)

        # For potential updates, check serial numbers to identify actual changes
        cases_needing_update = []
        unchanged_cases = []

        # Create lookup dictionaries for efficient access
        crm_lookup = {case["case_ref"]: case for case in crm_cases}
        caseguard_lookup = {case["case_ref"]: case for case in caseguard_cases}

        for case_ref in potential_updates:
            crm_case = crm_lookup.get(case_ref, {})
            cg_case = caseguard_lookup.get(case_ref, {})

            crm_serialno = crm_case.get("serialno", 0)
            cg_serialno = cg_case.get("last_serialno", 0)

            if crm_serialno > cg_serialno:
                cases_needing_update.append(case_ref)
            else:
                unchanged_cases.append(case_ref)

        reconciliation_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "crm_active_count": len(crm_refs),
            "caseguard_active_count": len(caseguard_refs),
            "new_cases": new_cases,
            "deactivated_cases": deactivated_cases,
            "cases_needing_update": cases_needing_update,
            "unchanged_cases": unchanged_cases,
            "summary": {
                "new": len(new_cases),
                "deactivated": len(deactivated_cases),
                "updates_needed": len(cases_needing_update),
                "unchanged": len(unchanged_cases)
            }
        }

        task_logger.info(f"Reconciliation complete: {reconciliation_result['summary']}")
        task_logger.info(f"New cases: {len(new_cases)}, Updates needed: {len(cases_needing_update)}")

        return reconciliation_result

    except Exception as e:
        task_logger.error(f"Case state reconciliation failed: {e}")
        raise


@task(
    name="enqueue_sync_jobs",
    description="Queue identified changes for processing",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=900  # 15 minutes
)
def enqueue_sync_jobs(tenant_id: str, reconciliation: Dict[str, Any]) -> Dict[str, Any]:
    """Queue new cases and updates for processing via Redis.

    Args:
        tenant_id: Law firm tenant identifier
        reconciliation: Results from case state reconciliation

    Returns:
        Job queuing results
    """
    task_logger = get_run_logger()
    task_logger.info("Queuing sync jobs based on reconciliation results")

    try:
        import redis
        from v2.etl.prefect_config import get_redis_connection_url

        redis_client = redis.from_url(get_redis_connection_url(), decode_responses=True)

        queuing_results = {
            "tenant_id": tenant_id,
            "queued_at": datetime.utcnow().isoformat(),
            "new_cases_queued": 0,
            "updates_queued": 0,
            "queuing_failures": 0,
            "total_jobs_queued": 0
        }

        # Queue new cases (full rebuild required)
        new_cases = reconciliation.get("new_cases", [])
        for case_ref in new_cases:
            try:
                job_data = {
                    "tenant_id": tenant_id,
                    "case_ref": case_ref,
                    "is_full_rebuild": True,  # New cases need full processing
                    "job_type": "sync_new_case",
                    "priority": 2,  # Medium priority
                    "queued_at": datetime.utcnow().isoformat(),
                    "source": "daily_sync"
                }

                redis_client.lpush("case_processing_queue:priority:2", json.dumps(job_data))
                queuing_results["new_cases_queued"] += 1

            except Exception as e:
                task_logger.error(f"Failed to queue new case {case_ref}: {e}")
                queuing_results["queuing_failures"] += 1

        # Queue cases needing updates (incremental processing)
        update_cases = reconciliation.get("cases_needing_update", [])
        for case_ref in update_cases:
            try:
                job_data = {
                    "tenant_id": tenant_id,
                    "case_ref": case_ref,
                    "is_full_rebuild": False,  # Incremental update
                    "job_type": "sync_update_case",
                    "priority": 3,  # Lower priority than new cases
                    "queued_at": datetime.utcnow().isoformat(),
                    "source": "daily_sync"
                }

                redis_client.lpush("case_processing_queue:priority:3", json.dumps(job_data))
                queuing_results["updates_queued"] += 1

            except Exception as e:
                task_logger.error(f"Failed to queue update for case {case_ref}: {e}")
                queuing_results["queuing_failures"] += 1

        # Mark deactivated cases in database (placeholder - actual implementation needed)
        deactivated_cases = reconciliation.get("deactivated_cases", [])
        if deactivated_cases:
            task_logger.info(f"Need to mark {len(deactivated_cases)} cases as inactive")
            # This would update the database to mark cases as inactive
            # Implementation depends on final database schema

        queuing_results["total_jobs_queued"] = (
            queuing_results["new_cases_queued"] + queuing_results["updates_queued"]
        )

        task_logger.info(f"Sync jobs queued successfully: {queuing_results['total_jobs_queued']} total jobs")
        task_logger.info(f"New: {queuing_results['new_cases_queued']}, Updates: {queuing_results['updates_queued']}")

        return queuing_results

    except Exception as e:
        task_logger.error(f"Failed to queue sync jobs: {e}")
        raise


@flow(
    name="sync_tenant_daily",
    description="Fast, lightweight daily updates for changed cases only",
    tags=CASEGUARD_V2_TAGS,
    task_runner=ConcurrentTaskRunner(),
    timeout_seconds=3600,  # 1 hour
    retries=1,
    retry_delay_seconds=600  # 10 minute delay before flow retry
)
def sync_tenant_daily(tenant_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """Fast, lightweight daily updates for changed cases only.

    This flow performs efficient synchronization by:
    1. Comparing CRM active cases with CaseGuard database
    2. Identifying new, updated, and deactivated cases
    3. Queuing only changed cases for processing
    4. Using high-watermark serial number comparison for efficiency

    Args:
        tenant_id: Law firm tenant identifier
        dry_run: If True, perform reconciliation but don't queue jobs

    Returns:
        Daily sync results with detailed statistics
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Starting daily sync for tenant {tenant_id} (dry_run={dry_run})")

    start_time = datetime.utcnow()
    sync_results = {
        "tenant_id": tenant_id,
        "sync_type": "daily",
        "dry_run": dry_run,
        "started_at": start_time.isoformat(),
        "steps_completed": [],
        "final_status": "in_progress"
    }

    try:
        # Step 1: Get current CRM active cases
        flow_logger.info("Step 1: Fetching active cases from CRM")
        crm_cases = get_crm_active_cases_list(tenant_id)
        sync_results["crm_cases_count"] = len(crm_cases)
        sync_results["steps_completed"].append("crm_fetch")

        # Step 2: Get current CaseGuard active cases
        flow_logger.info("Step 2: Querying CaseGuard database")
        caseguard_cases = get_caseguard_active_cases_list(tenant_id)
        sync_results["caseguard_cases_count"] = len(caseguard_cases)
        sync_results["steps_completed"].append("database_query")

        # Step 3: Reconcile case states
        flow_logger.info("Step 3: Reconciling case states")
        reconciliation = reconcile_case_states(crm_cases, caseguard_cases)
        sync_results["reconciliation"] = reconciliation
        sync_results["steps_completed"].append("reconciliation")

        # Step 4: Queue jobs (unless dry run)
        if not dry_run:
            flow_logger.info("Step 4: Queuing processing jobs")
            queuing_results = enqueue_sync_jobs(tenant_id, reconciliation)
            sync_results["queuing_results"] = queuing_results
            sync_results["steps_completed"].append("job_queuing")
        else:
            flow_logger.info("Step 4: Skipping job queuing (dry run mode)")
            sync_results["queuing_results"] = {
                "message": "Skipped due to dry_run=True",
                "would_queue": reconciliation["summary"]["new"] + reconciliation["summary"]["updates_needed"]
            }

        # Final results
        end_time = datetime.utcnow()
        sync_duration = (end_time - start_time).total_seconds()

        sync_results.update({
            "completed_at": end_time.isoformat(),
            "sync_duration_seconds": sync_duration,
            "final_status": "completed",
            "efficiency_metrics": {
                "total_cases_checked": len(crm_cases) + len(caseguard_cases),
                "processing_jobs_created": (
                    queuing_results.get("total_jobs_queued", 0) if not dry_run
                    else sync_results["queuing_results"]["would_queue"]
                ),
                "efficiency_ratio": (
                    (queuing_results.get("total_jobs_queued", 0) / max(len(crm_cases), 1))
                    if not dry_run else 0
                )
            }
        })

        flow_logger.info(f"Daily sync completed successfully in {sync_duration:.1f}s")
        flow_logger.info(f"Changes identified: {reconciliation['summary']}")

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

        flow_logger.error(f"Daily sync failed after {sync_duration:.1f}s: {e}")
        flow_logger.error(f"Steps completed before failure: {sync_results['steps_completed']}")

        return error_result


# Utility flow for manual sync trigger
@flow(
    name="trigger_manual_sync",
    description="Manually trigger sync for specific tenant with options",
    tags=CASEGUARD_V2_TAGS
)
def trigger_manual_sync(
    tenant_id: str,
    include_dry_run: bool = True,
    force_full_reconciliation: bool = False
) -> Dict[str, Any]:
    """Manually trigger synchronization with additional options.

    Args:
        tenant_id: Law firm tenant identifier
        include_dry_run: Run dry run first to preview changes
        force_full_reconciliation: Force full reconciliation even if recent sync exists

    Returns:
        Manual sync results
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Manual sync triggered for tenant {tenant_id}")

    manual_results = {
        "tenant_id": tenant_id,
        "trigger_type": "manual",
        "triggered_at": datetime.utcnow().isoformat(),
        "results": []
    }

    try:
        # Optional dry run first
        if include_dry_run:
            flow_logger.info("Running dry run first...")
            dry_run_result = sync_tenant_daily(tenant_id, dry_run=True)
            manual_results["results"].append({
                "phase": "dry_run",
                "result": dry_run_result
            })

            # Check if any work is needed
            changes_needed = (
                dry_run_result.get("reconciliation", {})
                .get("summary", {})
                .get("new", 0) + dry_run_result.get("reconciliation", {})
                .get("summary", {})
                .get("updates_needed", 0)
            )

            if changes_needed == 0 and not force_full_reconciliation:
                flow_logger.info("No changes detected in dry run - skipping actual sync")
                manual_results["skipped_actual_sync"] = True
                return manual_results

        # Run actual sync
        flow_logger.info("Running actual synchronization...")
        actual_sync_result = sync_tenant_daily(tenant_id, dry_run=False)
        manual_results["results"].append({
            "phase": "actual_sync",
            "result": actual_sync_result
        })

        flow_logger.info("Manual sync completed successfully")
        return manual_results

    except Exception as e:
        flow_logger.error(f"Manual sync failed: {e}")
        manual_results["error"] = str(e)
        return manual_results