"""Production monitoring dashboard with Prefect integration and system health checks."""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import json
import asyncio
from enum import Enum

# V2 imports
from ..database.session_manager import SessionManager
from ..database.models import ProcessingJob, JobStatus
from ..core.tenant_manager import TenantManager

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """System health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DOWN = "down"


class MetricType(str, Enum):
    """Types of system metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class SystemMetric:
    """System metric data structure."""
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime
    labels: Dict[str, str] = None
    tenant_id: Optional[str] = None


@dataclass
class HealthCheck:
    """Health check result structure."""
    component: str
    status: HealthStatus
    message: str
    timestamp: datetime
    response_time_ms: float = 0.0
    details: Dict[str, Any] = None


class MonitoringDashboard:
    """Production monitoring dashboard with multi-tenant awareness."""

    def __init__(self, tenant_manager: TenantManager = None):
        """Initialize monitoring dashboard.

        Args:
            tenant_manager: Tenant configuration manager
        """
        self.tenant_manager = tenant_manager or TenantManager()
        self.session_manager = SessionManager()
        self.metrics_cache = {}
        self.health_cache = {}
        self.cache_ttl_seconds = 30

        logger.info("MonitoringDashboard initialized")

    async def get_system_overview(self) -> Dict[str, Any]:
        """Get comprehensive system overview across all tenants.

        Returns:
            System overview dashboard data
        """
        logger.debug("Generating system overview")

        try:
            # Get active tenants
            active_tenants = await self.tenant_manager.get_active_tenants()

            # Aggregate metrics across tenants
            overview = {
                "timestamp": datetime.utcnow().isoformat(),
                "system_status": await self._get_overall_system_status(),
                "tenant_summary": {
                    "total_tenants": len(active_tenants),
                    "active_tenants": len([t for t in active_tenants if t.get('is_active', False)]),
                    "tenant_statuses": {}
                },
                "processing_summary": await self._get_processing_summary(),
                "resource_utilization": await self._get_resource_metrics(),
                "recent_alerts": await self._get_recent_alerts(),
                "performance_metrics": await self._get_performance_overview()
            }

            # Get per-tenant status
            for tenant in active_tenants:
                tenant_id = tenant.get('tenant_id')
                if tenant_id:
                    overview["tenant_summary"]["tenant_statuses"][tenant_id] = \
                        await self._get_tenant_status(tenant_id)

            logger.info(f"System overview generated for {len(active_tenants)} tenants")
            return overview

        except Exception as e:
            logger.error(f"Failed to generate system overview: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "system_status": HealthStatus.CRITICAL,
                "error": str(e),
                "tenant_summary": {"total_tenants": 0, "active_tenants": 0},
                "processing_summary": {},
                "resource_utilization": {},
                "recent_alerts": [],
                "performance_metrics": {}
            }

    async def run_health_checks(self) -> List[HealthCheck]:
        """Run comprehensive health checks across all system components.

        Returns:
            List of health check results
        """
        logger.info("Starting comprehensive health checks")

        health_checks = []

        # Core system checks
        checks = [
            self._check_database_health(),
            self._check_prefect_health(),
            self._check_redis_health(),
            self._check_vector_stores_health(),
            self._check_ai_services_health(),
            self._check_storage_health()
        ]

        # Run checks concurrently
        try:
            results = await asyncio.gather(*checks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    health_checks.append(HealthCheck(
                        component="unknown",
                        status=HealthStatus.CRITICAL,
                        message=f"Health check failed: {str(result)}",
                        timestamp=datetime.utcnow()
                    ))
                else:
                    health_checks.append(result)

        except Exception as e:
            logger.error(f"Health checks failed: {e}")
            health_checks.append(HealthCheck(
                component="health_system",
                status=HealthStatus.CRITICAL,
                message=f"Health check system failure: {str(e)}",
                timestamp=datetime.utcnow()
            ))

        # Add tenant-specific checks
        try:
            active_tenants = await self.tenant_manager.get_active_tenants()
            for tenant in active_tenants:
                tenant_id = tenant.get('tenant_id')
                if tenant_id:
                    tenant_check = await self._check_tenant_health(tenant_id)
                    health_checks.append(tenant_check)
        except Exception as e:
            logger.error(f"Tenant health checks failed: {e}")

        overall_status = self._determine_overall_health(health_checks)
        logger.info(f"Health checks complete: {overall_status} ({len(health_checks)} checks)")

        return health_checks

    async def get_tenant_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant-specific dashboard data.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Tenant dashboard data
        """
        logger.debug(f"Generating tenant dashboard for {tenant_id}")

        try:
            tenant_config = await self.tenant_manager.get_tenant_config(tenant_id)
            if not tenant_config:
                return {"error": f"Tenant {tenant_id} not found"}

            dashboard = {
                "tenant_id": tenant_id,
                "display_name": tenant_config.get('display_name', tenant_id),
                "timestamp": datetime.utcnow().isoformat(),
                "status": await self._get_tenant_status(tenant_id),
                "processing_stats": await self._get_tenant_processing_stats(tenant_id),
                "recent_jobs": await self._get_recent_tenant_jobs(tenant_id),
                "case_metrics": await self._get_tenant_case_metrics(tenant_id),
                "resource_usage": await self._get_tenant_resource_usage(tenant_id),
                "configuration": {
                    "is_active": tenant_config.get('is_active', False),
                    "processing_limits": tenant_config.get('processing_config', {}),
                    "crm_type": tenant_config.get('crm_config', {}).get('type', 'unknown'),
                    "vector_indexes": tenant_config.get('vector_config', {}),
                    "ai_config": tenant_config.get('ai_config', {})
                }
            }

            logger.debug(f"Tenant dashboard generated for {tenant_id}")
            return dashboard

        except Exception as e:
            logger.error(f"Failed to generate tenant dashboard for {tenant_id}: {e}")
            return {
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "status": HealthStatus.CRITICAL
            }

    async def get_processing_metrics(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get processing performance metrics.

        Args:
            hours_back: How many hours back to analyze

        Returns:
            Processing metrics data
        """
        logger.debug(f"Collecting processing metrics for last {hours_back} hours")

        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)

            with self.session_manager.get_session() as session:
                # Query processing jobs
                from sqlalchemy import func, and_

                # Get job statistics
                job_stats = session.query(
                    ProcessingJob.status,
                    ProcessingJob.tenant_id,
                    func.count(ProcessingJob.id).label('count'),
                    func.avg(ProcessingJob.duration_seconds).label('avg_duration'),
                    func.max(ProcessingJob.duration_seconds).label('max_duration')
                ).filter(
                    ProcessingJob.created_at >= cutoff_time
                ).group_by(
                    ProcessingJob.status,
                    ProcessingJob.tenant_id
                ).all()

                # Calculate throughput
                hourly_throughput = session.query(
                    func.date_trunc('hour', ProcessingJob.created_at).label('hour'),
                    ProcessingJob.tenant_id,
                    func.count(ProcessingJob.id).label('jobs_count')
                ).filter(
                    ProcessingJob.created_at >= cutoff_time
                ).group_by(
                    func.date_trunc('hour', ProcessingJob.created_at),
                    ProcessingJob.tenant_id
                ).all()

                # Error analysis
                error_analysis = session.query(
                    ProcessingJob.error_message,
                    func.count(ProcessingJob.id).label('count')
                ).filter(
                    and_(
                        ProcessingJob.created_at >= cutoff_time,
                        ProcessingJob.status == JobStatus.FAILED
                    )
                ).group_by(
                    ProcessingJob.error_message
                ).limit(10).all()

            metrics = {
                "analysis_period_hours": hours_back,
                "timestamp": datetime.utcnow().isoformat(),
                "job_statistics": self._format_job_statistics(job_stats),
                "throughput_analysis": self._format_throughput_data(hourly_throughput),
                "error_analysis": [
                    {"error": error, "count": count}
                    for error, count in error_analysis
                ],
                "performance_summary": self._calculate_performance_summary(job_stats)
            }

            logger.info(f"Processing metrics collected for {hours_back} hours")
            return metrics

        except Exception as e:
            logger.error(f"Failed to collect processing metrics: {e}")
            return {
                "analysis_period_hours": hours_back,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }

    async def export_metrics(self, output_path: str, format: str = "json") -> str:
        """Export monitoring metrics to file.

        Args:
            output_path: Output file path
            format: Export format (json, csv)

        Returns:
            Path to exported file
        """
        logger.info(f"Exporting metrics to {output_path} in {format} format")

        try:
            # Collect comprehensive metrics
            metrics_data = {
                "export_timestamp": datetime.utcnow().isoformat(),
                "system_overview": await self.get_system_overview(),
                "health_checks": [
                    {
                        "component": check.component,
                        "status": check.status,
                        "message": check.message,
                        "timestamp": check.timestamp.isoformat(),
                        "response_time_ms": check.response_time_ms
                    }
                    for check in await self.run_health_checks()
                ],
                "processing_metrics": await self.get_processing_metrics(hours_back=168),  # 1 week
                "tenant_dashboards": {}
            }

            # Add tenant-specific data
            active_tenants = await self.tenant_manager.get_active_tenants()
            for tenant in active_tenants:
                tenant_id = tenant.get('tenant_id')
                if tenant_id:
                    metrics_data["tenant_dashboards"][tenant_id] = \
                        await self.get_tenant_dashboard(tenant_id)

            # Export based on format
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if format.lower() == "json":
                with open(output_file, 'w') as f:
                    json.dump(metrics_data, f, indent=2, default=str)
            elif format.lower() == "csv":
                # Convert to CSV format (simplified)
                import pandas as pd

                # Flatten health checks for CSV
                health_df = pd.DataFrame([
                    {
                        "component": check["component"],
                        "status": check["status"],
                        "message": check["message"],
                        "timestamp": check["timestamp"],
                        "response_time_ms": check["response_time_ms"]
                    }
                    for check in metrics_data["health_checks"]
                ])

                health_df.to_csv(output_file, index=False)
            else:
                raise ValueError(f"Unsupported export format: {format}")

            logger.info(f"Metrics exported successfully to {output_file}")
            return str(output_file)

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            raise

    # Internal health check methods
    async def _check_database_health(self) -> HealthCheck:
        """Check PostgreSQL database health."""
        start_time = datetime.utcnow()

        try:
            with self.session_manager.get_session() as session:
                # Simple connectivity and performance test
                result = session.execute("SELECT 1, NOW()").fetchone()

                response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return HealthCheck(
                    component="postgresql_database",
                    status=HealthStatus.HEALTHY if response_time < 100 else HealthStatus.WARNING,
                    message=f"Database responsive in {response_time:.1f}ms",
                    timestamp=datetime.utcnow(),
                    response_time_ms=response_time
                )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component="postgresql_database",
                status=HealthStatus.CRITICAL,
                message=f"Database connection failed: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    async def _check_prefect_health(self) -> HealthCheck:
        """Check Prefect server health."""
        start_time = datetime.utcnow()

        try:
            # Try to import and check Prefect client
            from prefect import get_client

            async with get_client() as client:
                # Simple API call to check connectivity
                flows = await client.read_flows(limit=1)

                response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return HealthCheck(
                    component="prefect_server",
                    status=HealthStatus.HEALTHY,
                    message=f"Prefect server responsive in {response_time:.1f}ms",
                    timestamp=datetime.utcnow(),
                    response_time_ms=response_time
                )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component="prefect_server",
                status=HealthStatus.CRITICAL,
                message=f"Prefect server unavailable: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    async def _check_redis_health(self) -> HealthCheck:
        """Check Redis/Valkey health."""
        start_time = datetime.utcnow()

        try:
            import redis
            import os

            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            client = redis.from_url(redis_url)

            # Simple ping test
            client.ping()

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return HealthCheck(
                component="redis_valkey",
                status=HealthStatus.HEALTHY,
                message=f"Redis responsive in {response_time:.1f}ms",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component="redis_valkey",
                status=HealthStatus.CRITICAL,
                message=f"Redis connection failed: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    async def _check_vector_stores_health(self) -> HealthCheck:
        """Check vector store (Pinecone) health."""
        start_time = datetime.utcnow()

        try:
            import pinecone
            import os

            # Initialize Pinecone client
            api_key = os.getenv('PINECONE_API_KEY')
            if not api_key:
                return HealthCheck(
                    component="vector_stores",
                    status=HealthStatus.WARNING,
                    message="Pinecone API key not configured",
                    timestamp=datetime.utcnow()
                )

            # Check index health
            pc = pinecone.Pinecone(api_key=api_key)
            indexes = pc.list_indexes()

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return HealthCheck(
                component="vector_stores",
                status=HealthStatus.HEALTHY,
                message=f"Pinecone responsive with {len(indexes)} indexes in {response_time:.1f}ms",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component="vector_stores",
                status=HealthStatus.CRITICAL,
                message=f"Vector store health check failed: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    async def _check_ai_services_health(self) -> HealthCheck:
        """Check AI services (OpenAI) health."""
        start_time = datetime.utcnow()

        try:
            import openai
            import os

            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                return HealthCheck(
                    component="ai_services",
                    status=HealthStatus.WARNING,
                    message="OpenAI API key not configured",
                    timestamp=datetime.utcnow()
                )

            # Simple model list test
            client = openai.OpenAI(api_key=api_key)
            models = client.models.list()

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return HealthCheck(
                component="ai_services",
                status=HealthStatus.HEALTHY,
                message=f"OpenAI API responsive in {response_time:.1f}ms",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component="ai_services",
                status=HealthStatus.CRITICAL,
                message=f"AI services health check failed: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    async def _check_storage_health(self) -> HealthCheck:
        """Check storage system health."""
        start_time = datetime.utcnow()

        try:
            # Check disk space and write permissions
            import shutil
            import tempfile

            # Check available disk space
            total, used, free = shutil.disk_usage("/")
            free_gb = free // (1024**3)

            # Test write permissions
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                tmp.write(b"health check")
                tmp.flush()

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            status = HealthStatus.HEALTHY
            message = f"Storage healthy: {free_gb}GB free"

            if free_gb < 5:  # Less than 5GB free
                status = HealthStatus.CRITICAL
                message = f"Storage critical: only {free_gb}GB free"
            elif free_gb < 20:  # Less than 20GB free
                status = HealthStatus.WARNING
                message = f"Storage low: {free_gb}GB free"

            return HealthCheck(
                component="storage_system",
                status=status,
                message=message,
                timestamp=datetime.utcnow(),
                response_time_ms=response_time,
                details={"free_gb": free_gb, "total_gb": total // (1024**3)}
            )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component="storage_system",
                status=HealthStatus.CRITICAL,
                message=f"Storage health check failed: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    async def _check_tenant_health(self, tenant_id: str) -> HealthCheck:
        """Check tenant-specific health."""
        start_time = datetime.utcnow()

        try:
            tenant_config = await self.tenant_manager.get_tenant_config(tenant_id)
            if not tenant_config:
                return HealthCheck(
                    component=f"tenant_{tenant_id}",
                    status=HealthStatus.CRITICAL,
                    message="Tenant configuration not found",
                    timestamp=datetime.utcnow()
                )

            # Check tenant processing health
            processing_stats = await self._get_tenant_processing_stats(tenant_id)
            recent_failures = processing_stats.get('failed_jobs_24h', 0)
            total_jobs = processing_stats.get('total_jobs_24h', 0)

            failure_rate = (recent_failures / max(total_jobs, 1)) * 100

            status = HealthStatus.HEALTHY
            message = f"Tenant healthy: {failure_rate:.1f}% failure rate"

            if failure_rate > 20:
                status = HealthStatus.CRITICAL
                message = f"Tenant critical: {failure_rate:.1f}% failure rate"
            elif failure_rate > 10:
                status = HealthStatus.WARNING
                message = f"Tenant degraded: {failure_rate:.1f}% failure rate"

            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return HealthCheck(
                component=f"tenant_{tenant_id}",
                status=status,
                message=message,
                timestamp=datetime.utcnow(),
                response_time_ms=response_time,
                details=processing_stats
            )

        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return HealthCheck(
                component=f"tenant_{tenant_id}",
                status=HealthStatus.CRITICAL,
                message=f"Tenant health check failed: {str(e)}",
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )

    # Helper methods for data formatting and analysis
    def _determine_overall_health(self, health_checks: List[HealthCheck]) -> HealthStatus:
        """Determine overall system health from individual checks."""
        if not health_checks:
            return HealthStatus.CRITICAL

        critical_count = sum(1 for check in health_checks if check.status == HealthStatus.CRITICAL)
        warning_count = sum(1 for check in health_checks if check.status == HealthStatus.WARNING)

        if critical_count > 0:
            return HealthStatus.CRITICAL
        elif warning_count > len(health_checks) * 0.3:  # More than 30% warnings
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    async def _get_overall_system_status(self) -> HealthStatus:
        """Get cached overall system status."""
        cache_key = "overall_system_status"
        cached = self.health_cache.get(cache_key)

        if cached and (datetime.utcnow() - cached['timestamp']).seconds < self.cache_ttl_seconds:
            return cached['status']

        # Run health checks if not cached
        health_checks = await self.run_health_checks()
        status = self._determine_overall_health(health_checks)

        self.health_cache[cache_key] = {
            'status': status,
            'timestamp': datetime.utcnow()
        }

        return status

    async def _get_processing_summary(self) -> Dict[str, Any]:
        """Get processing summary across all tenants."""
        try:
            with self.session_manager.get_session() as session:
                from sqlalchemy import func

                # Last 24 hours summary
                cutoff_time = datetime.utcnow() - timedelta(hours=24)

                summary = session.query(
                    ProcessingJob.status,
                    func.count(ProcessingJob.id).label('count')
                ).filter(
                    ProcessingJob.created_at >= cutoff_time
                ).group_by(ProcessingJob.status).all()

                return {
                    job_status: count for job_status, count in summary
                }

        except Exception as e:
            logger.error(f"Failed to get processing summary: {e}")
            return {}

    async def _get_resource_metrics(self) -> Dict[str, Any]:
        """Get system resource utilization metrics."""
        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_free_gb": disk.free / (1024**3),
                "disk_percent": (disk.used / disk.total) * 100
            }

        except ImportError:
            logger.warning("psutil not available for resource monitoring")
            return {"error": "Resource monitoring not available"}
        except Exception as e:
            logger.error(f"Failed to get resource metrics: {e}")
            return {"error": str(e)}

    async def _get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent system alerts."""
        # Placeholder - in production this would query an alerting system
        return []

    async def _get_performance_overview(self) -> Dict[str, Any]:
        """Get performance overview metrics."""
        try:
            metrics = await self.get_processing_metrics(hours_back=24)
            return metrics.get('performance_summary', {})
        except Exception as e:
            logger.error(f"Failed to get performance overview: {e}")
            return {}

    async def _get_tenant_status(self, tenant_id: str) -> HealthStatus:
        """Get tenant-specific status."""
        try:
            tenant_check = await self._check_tenant_health(tenant_id)
            return tenant_check.status
        except Exception as e:
            logger.error(f"Failed to get tenant status for {tenant_id}: {e}")
            return HealthStatus.CRITICAL

    async def _get_tenant_processing_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant processing statistics."""
        try:
            with self.session_manager.get_session() as session:
                from sqlalchemy import func

                cutoff_24h = datetime.utcnow() - timedelta(hours=24)
                cutoff_7d = datetime.utcnow() - timedelta(days=7)

                # 24-hour stats
                stats_24h = session.query(
                    ProcessingJob.status,
                    func.count(ProcessingJob.id).label('count'),
                    func.avg(ProcessingJob.duration_seconds).label('avg_duration')
                ).filter(
                    ProcessingJob.tenant_id == tenant_id,
                    ProcessingJob.created_at >= cutoff_24h
                ).group_by(ProcessingJob.status).all()

                # 7-day stats
                total_7d = session.query(
                    func.count(ProcessingJob.id)
                ).filter(
                    ProcessingJob.tenant_id == tenant_id,
                    ProcessingJob.created_at >= cutoff_7d
                ).scalar() or 0

                stats = {
                    "total_jobs_24h": sum(count for _, count, _ in stats_24h),
                    "total_jobs_7d": total_7d,
                    "failed_jobs_24h": next((count for status, count, _ in stats_24h if status == JobStatus.FAILED), 0),
                    "successful_jobs_24h": next((count for status, count, _ in stats_24h if status == JobStatus.COMPLETED), 0),
                    "avg_duration_seconds": next((float(avg_duration) for status, _, avg_duration in stats_24h if status == JobStatus.COMPLETED and avg_duration), 0)
                }

                return stats

        except Exception as e:
            logger.error(f"Failed to get tenant processing stats for {tenant_id}: {e}")
            return {}

    async def _get_recent_tenant_jobs(self, tenant_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent jobs for tenant."""
        try:
            with self.session_manager.get_session() as session:
                jobs = session.query(ProcessingJob).filter(
                    ProcessingJob.tenant_id == tenant_id
                ).order_by(
                    ProcessingJob.created_at.desc()
                ).limit(limit).all()

                return [
                    {
                        "job_id": job.id,
                        "status": job.status,
                        "job_type": job.job_type,
                        "case_ref": job.case_ref,
                        "created_at": job.created_at.isoformat() if job.created_at else None,
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                        "duration_seconds": job.duration_seconds,
                        "error_message": job.error_message if job.status == JobStatus.FAILED else None
                    }
                    for job in jobs
                ]

        except Exception as e:
            logger.error(f"Failed to get recent tenant jobs for {tenant_id}: {e}")
            return []

    async def _get_tenant_case_metrics(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant case-related metrics."""
        # Placeholder - would query case data
        return {
            "total_cases": 0,
            "active_cases": 0,
            "cases_processed_24h": 0,
            "avg_processing_time_minutes": 0
        }

    async def _get_tenant_resource_usage(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant resource usage metrics."""
        # Placeholder - would track tenant-specific resource consumption
        return {
            "storage_used_gb": 0,
            "api_calls_24h": 0,
            "vector_operations_24h": 0,
            "ai_tokens_consumed_24h": 0
        }

    def _format_job_statistics(self, job_stats) -> Dict[str, Any]:
        """Format job statistics for display."""
        formatted = {}
        for status, tenant_id, count, avg_duration, max_duration in job_stats:
            key = f"{status}_{tenant_id}" if tenant_id else status
            formatted[key] = {
                "count": count,
                "avg_duration_seconds": float(avg_duration) if avg_duration else 0,
                "max_duration_seconds": float(max_duration) if max_duration else 0
            }
        return formatted

    def _format_throughput_data(self, throughput_data) -> List[Dict[str, Any]]:
        """Format throughput data for display."""
        return [
            {
                "hour": hour.isoformat() if hour else None,
                "tenant_id": tenant_id,
                "jobs_count": count
            }
            for hour, tenant_id, count in throughput_data
        ]

    def _calculate_performance_summary(self, job_stats) -> Dict[str, Any]:
        """Calculate performance summary from job statistics."""
        total_jobs = sum(count for _, _, count, _, _ in job_stats)
        successful_jobs = sum(count for status, _, count, _, _ in job_stats if status == JobStatus.COMPLETED)

        if total_jobs == 0:
            return {
                "total_jobs": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": 0.0
            }

        avg_durations = [avg_duration for _, _, _, avg_duration, _ in job_stats if avg_duration]
        overall_avg_duration = sum(avg_durations) / len(avg_durations) if avg_durations else 0

        return {
            "total_jobs": total_jobs,
            "success_rate": (successful_jobs / total_jobs) * 100,
            "avg_duration_seconds": float(overall_avg_duration)
        }


# Utility functions
def create_monitoring_dashboard(tenant_manager: TenantManager = None) -> MonitoringDashboard:
    """Create a monitoring dashboard instance.

    Args:
        tenant_manager: Optional tenant manager instance

    Returns:
        Configured MonitoringDashboard instance
    """
    return MonitoringDashboard(tenant_manager=tenant_manager)


async def run_health_check_cli() -> None:
    """CLI interface for running health checks."""
    dashboard = create_monitoring_dashboard()

    print("Running CaseGuard V2 Health Checks...")
    print("=" * 50)

    health_checks = await dashboard.run_health_checks()

    for check in health_checks:
        status_icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.WARNING: "⚠️",
            HealthStatus.CRITICAL: "❌",
            HealthStatus.DOWN: "🔴"
        }.get(check.status, "❓")

        print(f"{status_icon} {check.component}: {check.message}")
        if check.response_time_ms > 0:
            print(f"   Response time: {check.response_time_ms:.1f}ms")

    overall_status = dashboard._determine_overall_health(health_checks)
    print("\n" + "=" * 50)
    print(f"Overall System Status: {overall_status}")


if __name__ == "__main__":
    asyncio.run(run_health_check_cli())