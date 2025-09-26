"""Valkey (Redis) job worker for processing queued case jobs."""

import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import redis
from v2.etl.prefect_config import get_redis_connection_url
from v2.etl.flows.process_case import process_proclaim_case

logger = logging.getLogger(__name__)


class WorkerStatus(str, Enum):
    """Worker status enumeration."""
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WorkerMetrics:
    """Worker performance metrics."""
    jobs_processed: int = 0
    jobs_successful: int = 0
    jobs_failed: int = 0
    total_processing_time: float = 0.0
    average_processing_time: float = 0.0
    worker_uptime: float = 0.0
    last_job_processed: Optional[str] = None


class CaseProcessingWorker:
    """Redis queue worker for processing case jobs with health monitoring and error recovery."""

    def __init__(self, worker_id: str = None, max_jobs_per_hour: int = 60):
        """Initialize the case processing worker.

        Args:
            worker_id: Unique worker identifier
            max_jobs_per_hour: Rate limiting for job processing
        """
        self.worker_id = worker_id or f"worker_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.max_jobs_per_hour = max_jobs_per_hour
        self.status = WorkerStatus.STARTING
        self.metrics = WorkerMetrics()
        self.start_time = datetime.utcnow()

        # Redis connection
        self.redis_url = get_redis_connection_url()
        self.redis_client = None

        # Job processing configuration
        self.queue_names = [
            "case_processing_queue:priority:1",  # High priority (new urgent cases)
            "case_processing_queue:priority:2",  # Medium priority (daily sync new cases)
            "case_processing_queue:priority:3",  # Low priority (daily sync updates)
            "case_processing_queue"             # Default queue
        ]

        self.polling_timeout = 10  # seconds
        self.max_retries = 3
        self.retry_delay = 60  # seconds

        # Graceful shutdown handling
        self._shutdown_requested = False
        self._setup_signal_handlers()

        logger.info(f"Worker {self.worker_id} initialized")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def shutdown_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_requested = True
            self.status = WorkerStatus.STOPPING

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

    def _connect_redis(self) -> bool:
        """Establish Redis connection with retry logic.

        Returns:
            True if connection successful, False otherwise
        """
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                self.redis_client.ping()
                logger.info(f"Redis connection established (attempt {attempt + 1})")
                return True

            except Exception as e:
                logger.error(f"Redis connection attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        logger.error("Failed to establish Redis connection after all attempts")
        return False

    def _get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get next job from priority queues.

        Returns:
            Job data dictionary or None if no jobs available
        """
        try:
            # Check queues in priority order
            for queue_name in self.queue_names:
                job_data = self.redis_client.brpop(queue_name, timeout=self.polling_timeout)
                if job_data:
                    _, job_json = job_data
                    job = json.loads(job_json)
                    job["source_queue"] = queue_name
                    logger.info(f"Retrieved job from {queue_name}: {job.get('case_ref', 'unknown')}")
                    return job

            return None

        except json.JSONDecodeError as e:
            logger.error(f"Invalid job data format: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving job: {e}")
            return None

    def _process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single case job.

        Args:
            job: Job data dictionary

        Returns:
            Processing result dictionary
        """
        case_ref = job.get("case_ref", "unknown")
        tenant_id = job.get("tenant_id", "unknown")
        is_full_rebuild = job.get("is_full_rebuild", False)

        logger.info(f"Processing job: {case_ref} (tenant: {tenant_id}, full_rebuild: {is_full_rebuild})")

        job_start_time = time.time()
        processing_result = {
            "case_ref": case_ref,
            "tenant_id": tenant_id,
            "worker_id": self.worker_id,
            "started_at": datetime.utcnow().isoformat(),
            "source_queue": job.get("source_queue"),
            "job_type": job.get("job_type", "unknown")
        }

        try:
            # Call the Prefect flow for case processing
            flow_result = process_proclaim_case(
                tenant_id=tenant_id,
                case_ref=case_ref,
                is_full_rebuild=is_full_rebuild
            )

            processing_time = time.time() - job_start_time
            processing_result.update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "flow_result": flow_result
            })

            # Update metrics
            self.metrics.jobs_processed += 1
            self.metrics.jobs_successful += 1
            self.metrics.total_processing_time += processing_time
            self.metrics.average_processing_time = (
                self.metrics.total_processing_time / self.metrics.jobs_processed
            )
            self.metrics.last_job_processed = case_ref

            logger.info(f"Job completed successfully: {case_ref} ({processing_time:.1f}s)")

        except Exception as e:
            processing_time = time.time() - job_start_time
            processing_result.update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "error": str(e),
                "error_type": type(e).__name__
            })

            # Update metrics
            self.metrics.jobs_processed += 1
            self.metrics.jobs_failed += 1

            logger.error(f"Job failed: {case_ref} - {e}")

        return processing_result

    def _handle_job_result(self, job: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Handle job processing result (success/failure/retry).

        Args:
            job: Original job data
            result: Processing result
        """
        case_ref = job.get("case_ref", "unknown")

        if result["status"] == "completed":
            # Job succeeded - log success
            logger.info(f"Job success logged: {case_ref}")

        elif result["status"] == "failed":
            # Check if job should be retried
            retry_count = job.get("retry_count", 0)
            max_retries = job.get("max_retries", self.max_retries)

            if retry_count < max_retries:
                # Queue for retry
                retry_job = {
                    **job,
                    "retry_count": retry_count + 1,
                    "last_error": result.get("error"),
                    "retry_queued_at": datetime.utcnow().isoformat(),
                    "next_retry_after": (datetime.utcnow() + timedelta(seconds=self.retry_delay)).isoformat()
                }

                # Add to retry queue with delay (lower priority)
                self.redis_client.lpush("case_processing_queue:priority:3", json.dumps(retry_job))
                logger.info(f"Job queued for retry ({retry_count + 1}/{max_retries}): {case_ref}")

            else:
                # Max retries exceeded - move to failed jobs queue
                failed_job = {
                    **job,
                    "final_failure_at": datetime.utcnow().isoformat(),
                    "final_error": result.get("error"),
                    "worker_id": self.worker_id
                }

                self.redis_client.lpush("failed_jobs", json.dumps(failed_job))
                logger.error(f"Job permanently failed after {retry_count} retries: {case_ref}")

    def _report_health_status(self) -> None:
        """Report worker health status to Redis."""
        try:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
            self.metrics.worker_uptime = uptime

            health_data = {
                "worker_id": self.worker_id,
                "status": self.status.value,
                "uptime_seconds": uptime,
                "metrics": {
                    "jobs_processed": self.metrics.jobs_processed,
                    "jobs_successful": self.metrics.jobs_successful,
                    "jobs_failed": self.metrics.jobs_failed,
                    "success_rate": (
                        self.metrics.jobs_successful / max(self.metrics.jobs_processed, 1)
                    ),
                    "average_processing_time": self.metrics.average_processing_time,
                    "last_job_processed": self.metrics.last_job_processed
                },
                "last_health_check": datetime.utcnow().isoformat(),
                "queues_monitored": self.queue_names
            }

            # Store health data with expiration
            health_key = f"worker_health:{self.worker_id}"
            self.redis_client.setex(health_key, 300, json.dumps(health_data))  # 5 minute expiry

        except Exception as e:
            logger.error(f"Failed to report health status: {e}")

    def _check_rate_limiting(self) -> bool:
        """Check if rate limiting should be applied.

        Returns:
            True if processing should continue, False if rate limited
        """
        if self.max_jobs_per_hour <= 0:
            return True  # No rate limiting

        # Check jobs processed in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        if self.start_time > one_hour_ago:
            # Worker hasn't been running for a full hour yet
            elapsed_hours = (datetime.utcnow() - self.start_time).total_seconds() / 3600
            max_jobs = int(self.max_jobs_per_hour * elapsed_hours)
        else:
            max_jobs = self.max_jobs_per_hour

        if self.metrics.jobs_processed >= max_jobs:
            logger.info(f"Rate limit reached: {self.metrics.jobs_processed}/{max_jobs} jobs/hour")
            return False

        return True

    def run(self, health_check_interval: int = 60) -> None:
        """Run the worker main loop.

        Args:
            health_check_interval: Interval between health status reports (seconds)
        """
        logger.info(f"Starting worker {self.worker_id}")

        # Connect to Redis
        if not self._connect_redis():
            logger.error("Cannot start worker without Redis connection")
            self.status = WorkerStatus.ERROR
            return

        self.status = WorkerStatus.RUNNING
        last_health_check = time.time()

        logger.info(f"Worker {self.worker_id} is now running")

        try:
            while not self._shutdown_requested:
                current_time = time.time()

                # Periodic health status reporting
                if current_time - last_health_check >= health_check_interval:
                    self._report_health_status()
                    last_health_check = current_time

                # Check rate limiting
                if not self._check_rate_limiting():
                    logger.info("Rate limited - pausing for 60 seconds")
                    time.sleep(60)
                    continue

                # Get next job
                job = self._get_next_job()
                if not job:
                    continue  # No job available, continue polling

                # Process job
                result = self._process_job(job)

                # Handle result (retry/failure logic)
                self._handle_job_result(job, result)

        except KeyboardInterrupt:
            logger.info("Worker interrupted by user")
        except Exception as e:
            logger.error(f"Worker error: {e}")
            self.status = WorkerStatus.ERROR
        finally:
            self._shutdown()

    def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info(f"Shutting down worker {self.worker_id}")
        self.status = WorkerStatus.STOPPED

        # Final health status report
        try:
            self._report_health_status()
        except:
            pass

        # Close Redis connection
        if self.redis_client:
            self.redis_client.close()

        # Log final metrics
        logger.info(f"Worker {self.worker_id} shutdown complete")
        logger.info(f"Final metrics: {self.metrics.jobs_processed} jobs processed, "
                   f"{self.metrics.jobs_successful} successful, {self.metrics.jobs_failed} failed")

    def get_status(self) -> Dict[str, Any]:
        """Get current worker status and metrics.

        Returns:
            Worker status dictionary
        """
        uptime = (datetime.utcnow() - self.start_time).total_seconds()

        return {
            "worker_id": self.worker_id,
            "status": self.status.value,
            "uptime_seconds": uptime,
            "metrics": {
                "jobs_processed": self.metrics.jobs_processed,
                "jobs_successful": self.metrics.jobs_successful,
                "jobs_failed": self.metrics.jobs_failed,
                "success_rate": self.metrics.jobs_successful / max(self.metrics.jobs_processed, 1),
                "average_processing_time": self.metrics.average_processing_time,
                "last_job_processed": self.metrics.last_job_processed
            },
            "configuration": {
                "max_jobs_per_hour": self.max_jobs_per_hour,
                "queues_monitored": self.queue_names,
                "polling_timeout": self.polling_timeout,
                "max_retries": self.max_retries
            },
            "timestamp": datetime.utcnow().isoformat()
        }


def main():
    """Main entry point for the worker."""
    import argparse

    parser = argparse.ArgumentParser(description="CaseGuard V2 Case Processing Worker")
    parser.add_argument(
        "--worker-id",
        help="Unique worker identifier",
        default=None
    )
    parser.add_argument(
        "--max-jobs-per-hour",
        type=int,
        help="Maximum jobs to process per hour (0 for no limit)",
        default=60
    )
    parser.add_argument(
        "--health-check-interval",
        type=int,
        help="Health check reporting interval in seconds",
        default=60
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
        default="INFO"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and run worker
    worker = CaseProcessingWorker(
        worker_id=args.worker_id,
        max_jobs_per_hour=args.max_jobs_per_hour
    )

    try:
        worker.run(health_check_interval=args.health_check_interval)
    except Exception as e:
        logger.error(f"Worker failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()