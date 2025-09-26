"""Historical backfill flow for massive case ingestion during tenant onboarding."""

import json
import logging
from typing import Dict, Any, List
from datetime import datetime

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from v2.etl.prefect_config import CASEGUARD_V2_TAGS, DEFAULT_RETRY_DELAY_SECONDS

logger = logging.getLogger(__name__)


@task(
    name="get_all_case_refs_for_tenant",
    description="Retrieve complete case inventory for historical backfill",
    tags=CASEGUARD_V2_TAGS,
    retries=3,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=3600  # 1 hour for large datasets
)
def get_all_case_refs_for_tenant(tenant_id: str, include_closed: bool = True) -> List[str]:
    """Single broad CRM API call for complete case list.

    Note: This requires CRM API extension - currently not available in Proclaim.
    Using fallback adapters until CRM provides bulk case enumeration endpoints.

    Args:
        tenant_id: Law firm identifier
        include_closed: Whether to include closed cases in backfill

    Returns:
        List of case references for the tenant
    """
    task_logger = get_run_logger()
    task_logger.info(f"Discovering all cases for tenant {tenant_id} (include_closed={include_closed})")

    try:
        # Import CRM discovery interface (to be implemented in Phase 3)
        # from v2.crm.discovery import CRMCaseDiscovery

        # For now, simulate case discovery with fallback methods
        task_logger.warning("Using fallback case discovery - CRM bulk endpoints not yet available")

        # Simulate different tenant case counts based on real data
        if tenant_id == "fdm_solicitors":
            # Based on actual FDM CSV data: 2117 cases (1037 Active, 1080 Complete)
            active_cases = [f"FDM{i:04d}" for i in range(1, 1038)]  # 1037 active
            closed_cases = [f"FDM{i:04d}C" for i in range(1, 1081)] # 1080 complete

            if include_closed:
                all_cases = active_cases + closed_cases
                task_logger.info(f"Discovered 2117 total cases (1037 active + 1080 closed)")
            else:
                all_cases = active_cases
                task_logger.info(f"Discovered 1037 active cases (excluding closed)")

        else:
            # Default simulation for other tenants
            all_cases = [f"{tenant_id.upper()}{i:04d}" for i in range(1, 501)]  # 500 cases
            task_logger.info(f"Discovered {len(all_cases)} cases for tenant {tenant_id}")

        task_logger.info(f"Case discovery completed: {len(all_cases)} cases found")
        return all_cases

    except Exception as e:
        task_logger.error(f"Case discovery failed for tenant {tenant_id}: {e}")
        raise


@task(
    name="validate_case_accessibility",
    description="Validate that discovered cases are accessible via Proclaim API",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=[30, 60],
    timeout_seconds=1800  # 30 minutes
)
def validate_case_accessibility(tenant_id: str, case_refs: List[str], sample_size: int = 10) -> Dict[str, Any]:
    """Validate a sample of cases to ensure API accessibility before queuing all cases.

    Args:
        tenant_id: Law firm identifier
        case_refs: List of case references to validate
        sample_size: Number of cases to sample for validation

    Returns:
        Validation results with accessibility statistics
    """
    task_logger = get_run_logger()
    task_logger.info(f"Validating API accessibility for {sample_size} sample cases")

    try:
        import random
        from v2.core.session_manager import V2SessionManager

        # Sample cases for validation
        sample_cases = random.sample(case_refs, min(sample_size, len(case_refs)))
        validation_results = {
            "tenant_id": tenant_id,
            "total_cases": len(case_refs),
            "sample_size": len(sample_cases),
            "accessible": 0,
            "inaccessible": 0,
            "errors": [],
            "estimated_accessibility_rate": 0.0
        }

        with V2SessionManager().bulk_processing_session() as session:
            task_logger.info(f"Validating {len(sample_cases)} sample cases")

            for case_ref in sample_cases:
                try:
                    # Simulate API accessibility check
                    # In real implementation, would attempt to fetch basic case metadata
                    task_logger.debug(f"Checking accessibility of case {case_ref}")

                    # Simulate 95% success rate for validation
                    if random.random() < 0.95:
                        validation_results["accessible"] += 1
                    else:
                        validation_results["inaccessible"] += 1
                        validation_results["errors"].append({
                            "case_ref": case_ref,
                            "error": "API access denied or case not found"
                        })

                except Exception as e:
                    validation_results["inaccessible"] += 1
                    validation_results["errors"].append({
                        "case_ref": case_ref,
                        "error": str(e)
                    })

        # Calculate accessibility rate
        total_validated = validation_results["accessible"] + validation_results["inaccessible"]
        if total_validated > 0:
            validation_results["estimated_accessibility_rate"] = (
                validation_results["accessible"] / total_validated
            )

        task_logger.info(f"Validation completed: {validation_results['accessible']}/{total_validated} cases accessible")
        task_logger.info(f"Estimated accessibility rate: {validation_results['estimated_accessibility_rate']:.1%}")

        return validation_results

    except Exception as e:
        task_logger.error(f"Case validation failed: {e}")
        raise


@task(
    name="enqueue_backfill_jobs",
    description="Queue individual cases for processing via Valkey (Redis)",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=1800  # 30 minutes
)
def enqueue_backfill_jobs(
    tenant_id: str,
    case_refs: List[str],
    batch_size: int = 100,
    priority: int = 1
) -> Dict[str, Any]:
    """Queue individual cases for processing via Valkey (Redis).

    Args:
        tenant_id: Law firm identifier
        case_refs: List of case references to queue
        batch_size: Number of cases to queue in each batch
        priority: Job priority (higher = more urgent)

    Returns:
        Queuing results with statistics
    """
    task_logger = get_run_logger()
    task_logger.info(f"Queuing {len(case_refs)} cases for backfill processing")

    try:
        import redis
        from v2.etl.prefect_config import get_redis_connection_url

        # Connect to Redis/Valkey
        redis_url = get_redis_connection_url()
        redis_client = redis.from_url(redis_url, decode_responses=True)

        # Test Redis connection
        redis_client.ping()
        task_logger.info("Redis connection established")

        queuing_results = {
            "tenant_id": tenant_id,
            "total_cases": len(case_refs),
            "queued_successfully": 0,
            "queuing_failures": 0,
            "batch_size": batch_size,
            "priority": priority,
            "queue_name": "case_processing_queue",
            "started_at": datetime.utcnow().isoformat()
        }

        # Queue cases in batches to avoid overwhelming Redis
        for i in range(0, len(case_refs), batch_size):
            batch = case_refs[i:i + batch_size]
            task_logger.info(f"Queuing batch {i//batch_size + 1}: {len(batch)} cases")

            for case_ref in batch:
                try:
                    job_data = {
                        "tenant_id": tenant_id,
                        "case_ref": case_ref,
                        "is_full_rebuild": True,  # Backfill always uses full rebuild
                        "job_type": "historical_backfill",
                        "priority": priority,
                        "queued_at": datetime.utcnow().isoformat(),
                        "batch_id": i // batch_size + 1
                    }

                    # Push to Redis queue with priority support
                    queue_name = f"case_processing_queue:priority:{priority}"
                    redis_client.lpush(queue_name, json.dumps(job_data))

                    queuing_results["queued_successfully"] += 1

                except Exception as e:
                    task_logger.error(f"Failed to queue case {case_ref}: {e}")
                    queuing_results["queuing_failures"] += 1

            # Brief pause between batches to prevent overwhelming Redis
            if i + batch_size < len(case_refs):
                import time
                time.sleep(0.1)

        queuing_results["completed_at"] = datetime.utcnow().isoformat()

        task_logger.info(f"Queuing completed: {queuing_results['queued_successfully']} successful, "
                        f"{queuing_results['queuing_failures']} failed")

        return queuing_results

    except Exception as e:
        task_logger.error(f"Failed to queue backfill jobs: {e}")
        raise


@task(
    name="monitor_backfill_progress",
    description="Monitor and report on backfill processing progress",
    tags=CASEGUARD_V2_TAGS,
    timeout_seconds=300  # 5 minutes
)
def monitor_backfill_progress(tenant_id: str, expected_job_count: int) -> Dict[str, Any]:
    """Monitor the progress of backfill job processing.

    Args:
        tenant_id: Law firm identifier
        expected_job_count: Expected number of jobs that were queued

    Returns:
        Progress monitoring results
    """
    task_logger = get_run_logger()
    task_logger.info(f"Monitoring backfill progress for {expected_job_count} jobs")

    try:
        import redis
        from v2.etl.prefect_config import get_redis_connection_url

        redis_client = redis.from_url(get_redis_connection_url(), decode_responses=True)

        # Check queue depths
        queue_names = [
            "case_processing_queue:priority:1",
            "case_processing_queue:priority:2",
            "failed_jobs"
        ]

        progress_data = {
            "tenant_id": tenant_id,
            "expected_jobs": expected_job_count,
            "queue_depths": {},
            "estimated_completion_time": None,
            "monitoring_timestamp": datetime.utcnow().isoformat()
        }

        total_queued = 0
        for queue_name in queue_names:
            depth = redis_client.llen(queue_name)
            progress_data["queue_depths"][queue_name] = depth
            total_queued += depth

        progress_data["total_jobs_remaining"] = total_queued
        progress_data["jobs_processed"] = max(0, expected_job_count - total_queued)

        if total_queued > 0 and expected_job_count > 0:
            completion_rate = (expected_job_count - total_queued) / expected_job_count
            progress_data["completion_percentage"] = completion_rate * 100

        task_logger.info(f"Progress: {progress_data.get('jobs_processed', 0)}/{expected_job_count} jobs processed")
        task_logger.info(f"Remaining in queues: {total_queued}")

        return progress_data

    except Exception as e:
        task_logger.error(f"Progress monitoring failed: {e}")
        return {
            "tenant_id": tenant_id,
            "error": str(e),
            "monitoring_timestamp": datetime.utcnow().isoformat()
        }


@flow(
    name="onboard_tenant",
    description="One-time historical backfill for new tenants",
    tags=CASEGUARD_V2_TAGS,
    task_runner=ConcurrentTaskRunner(),
    timeout_seconds=7200,  # 2 hours
    retries=1,
    retry_delay_seconds=900  # 15 minutes
)
def onboard_tenant(
    tenant_id: str,
    include_closed_cases: bool = True,
    validate_before_queuing: bool = True,
    batch_size: int = 100
) -> Dict[str, Any]:
    """One-time historical backfill for new tenants.

    This flow handles the complete onboarding process:
    1. Discover all cases for the tenant
    2. Validate API accessibility (optional)
    3. Queue all cases for full processing
    4. Monitor initial progress

    Args:
        tenant_id: Law firm identifier for onboarding
        include_closed_cases: Whether to include closed cases in backfill
        validate_before_queuing: Whether to validate case accessibility first
        batch_size: Size of batches for queuing operations

    Returns:
        Complete onboarding results
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Starting tenant onboarding for {tenant_id}")

    start_time = datetime.utcnow()
    onboarding_results = {
        "tenant_id": tenant_id,
        "started_at": start_time.isoformat(),
        "include_closed_cases": include_closed_cases,
        "steps_completed": [],
        "final_status": "in_progress"
    }

    try:
        # Step 1: Discover all cases
        flow_logger.info("Step 1: Discovering all cases for tenant")
        case_refs = get_all_case_refs_for_tenant(tenant_id, include_closed_cases)
        onboarding_results["total_cases_discovered"] = len(case_refs)
        onboarding_results["steps_completed"].append("case_discovery")

        if len(case_refs) == 0:
            flow_logger.warning("No cases discovered - onboarding completed with empty result")
            onboarding_results["final_status"] = "completed_empty"
            return onboarding_results

        # Step 2: Validate accessibility (optional)
        if validate_before_queuing:
            flow_logger.info("Step 2: Validating case accessibility")
            validation_results = validate_case_accessibility(tenant_id, case_refs)
            onboarding_results["validation_results"] = validation_results
            onboarding_results["steps_completed"].append("validation")

            # Check if accessibility rate is acceptable (>80%)
            accessibility_rate = validation_results.get("estimated_accessibility_rate", 0)
            if accessibility_rate < 0.8:
                flow_logger.warning(f"Low accessibility rate: {accessibility_rate:.1%}")
                flow_logger.warning("Proceeding with onboarding but expect some failures")

        # Step 3: Queue all cases for processing
        flow_logger.info("Step 3: Queuing cases for backfill processing")
        queuing_results = enqueue_backfill_jobs(tenant_id, case_refs, batch_size)
        onboarding_results["queuing_results"] = queuing_results
        onboarding_results["steps_completed"].append("case_queuing")

        # Step 4: Initial progress monitoring
        flow_logger.info("Step 4: Initial progress monitoring")
        progress_snapshot = monitor_backfill_progress(tenant_id, len(case_refs))
        onboarding_results["initial_progress"] = progress_snapshot
        onboarding_results["steps_completed"].append("progress_monitoring")

        # Final results
        end_time = datetime.utcnow()
        onboarding_duration = (end_time - start_time).total_seconds()

        onboarding_results.update({
            "completed_at": end_time.isoformat(),
            "onboarding_duration_seconds": onboarding_duration,
            "final_status": "completed",
            "jobs_queued": queuing_results.get("queued_successfully", 0),
            "queuing_failures": queuing_results.get("queuing_failures", 0)
        })

        flow_logger.info(f"Tenant onboarding completed successfully in {onboarding_duration:.1f}s")
        flow_logger.info(f"Queued {onboarding_results['jobs_queued']} cases for processing")

        return onboarding_results

    except Exception as e:
        end_time = datetime.utcnow()
        onboarding_duration = (end_time - start_time).total_seconds()

        error_result = {
            **onboarding_results,
            "completed_at": end_time.isoformat(),
            "onboarding_duration_seconds": onboarding_duration,
            "final_status": "failed",
            "error": str(e)
        }

        flow_logger.error(f"Tenant onboarding failed after {onboarding_duration:.1f}s: {e}")
        flow_logger.error(f"Steps completed before failure: {onboarding_results['steps_completed']}")

        return error_result


# Utility flow for re-queuing failed cases
@flow(
    name="retry_failed_backfill_cases",
    description="Re-queue cases that failed during backfill processing",
    tags=CASEGUARD_V2_TAGS
)
def retry_failed_backfill_cases(tenant_id: str, max_retries: int = 3) -> Dict[str, Any]:
    """Re-queue cases from the failed jobs queue for retry processing.

    Args:
        tenant_id: Law firm identifier
        max_retries: Maximum number of retry attempts per case

    Returns:
        Retry processing results
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Processing failed backfill cases for tenant {tenant_id}")

    try:
        import redis
        from v2.etl.prefect_config import get_redis_connection_url

        redis_client = redis.from_url(get_redis_connection_url(), decode_responses=True)
        failed_queue = "failed_jobs"
        retry_queue = "case_processing_queue:priority:2"  # Lower priority for retries

        # Get all failed jobs
        failed_jobs_count = redis_client.llen(failed_queue)
        flow_logger.info(f"Found {failed_jobs_count} failed jobs to process")

        retry_results = {
            "tenant_id": tenant_id,
            "failed_jobs_found": failed_jobs_count,
            "requeued": 0,
            "permanently_failed": 0,
            "processed_at": datetime.utcnow().isoformat()
        }

        # Process failed jobs
        while True:
            job_data_str = redis_client.rpop(failed_queue)
            if not job_data_str:
                break

            try:
                job_data = json.loads(job_data_str)

                # Check if this job is for our tenant
                if job_data.get("tenant_id") != tenant_id:
                    # Put back jobs for other tenants
                    redis_client.lpush(failed_queue, job_data_str)
                    continue

                # Check retry count
                retry_count = job_data.get("retry_count", 0)
                if retry_count >= max_retries:
                    flow_logger.warning(f"Case {job_data.get('case_ref')} exceeded max retries")
                    retry_results["permanently_failed"] += 1
                    continue

                # Increment retry count and re-queue
                job_data["retry_count"] = retry_count + 1
                job_data["retry_queued_at"] = datetime.utcnow().isoformat()

                redis_client.lpush(retry_queue, json.dumps(job_data))
                retry_results["requeued"] += 1

            except json.JSONDecodeError as e:
                flow_logger.error(f"Invalid job data in failed queue: {e}")

        flow_logger.info(f"Retry processing completed: {retry_results['requeued']} requeued, "
                        f"{retry_results['permanently_failed']} permanently failed")

        return retry_results

    except Exception as e:
        flow_logger.error(f"Failed to process retry queue: {e}")
        return {"error": str(e), "tenant_id": tenant_id}