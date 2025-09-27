"""FastAPI application for CaseGuard V2 data pipelines."""

import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Setup logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="CaseGuard V2 Data Pipelines API",
    description="API for CaseGuard V2 data processing and workflow orchestration",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint providing basic API information."""
    return {
        "service": "CaseGuard V2 Data Pipelines API",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": os.getenv("CASEGUARD_ENV", "development")
    }


async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        import os
        import psycopg

        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return {"status": "warning", "message": "Database URL not configured"}

        # Simple connection test
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()

        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "critical", "message": f"Database connection failed: {str(e)}"}


async def check_redis_health() -> Dict[str, Any]:
    """Check Redis/Valkey connectivity."""
    try:
        import redis
        import os

        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        client = redis.from_url(redis_url)
        client.ping()

        return {"status": "healthy", "message": "Redis connection successful"}
    except Exception as e:
        return {"status": "warning", "message": f"Redis connection failed: {str(e)}"}


async def check_prefect_health() -> Dict[str, Any]:
    """Check Prefect server connectivity."""
    try:
        from prefect import get_client

        async with get_client() as client:
            # Simple API call to check connectivity
            flows = await client.read_flows(limit=1)

        return {"status": "healthy", "message": "Prefect server connection successful"}
    except Exception as e:
        return {"status": "warning", "message": f"Prefect server connection failed: {str(e)}"}


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint for container health checks."""
    try:
        # Run basic health checks
        checks = []

        # Check database
        db_check = await check_database_health()
        checks.append({"component": "database", **db_check})

        # Check Redis (non-critical)
        redis_check = await check_redis_health()
        checks.append({"component": "redis", **redis_check})

        # Check Prefect (non-critical for API)
        prefect_check = await check_prefect_health()
        checks.append({"component": "prefect", **prefect_check})

        # Determine overall health
        critical_issues = [c for c in checks if c["status"] == "critical"]
        warnings = [c for c in checks if c["status"] == "warning"]

        if critical_issues:
            overall_status = "critical"
            status_code = 503
        elif warnings:
            overall_status = "warning"
            status_code = 200
        else:
            overall_status = "healthy"
            status_code = 200

        response_data = {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks,
            "summary": {
                "total_checks": len(checks),
                "healthy": len([c for c in checks if c["status"] == "healthy"]),
                "warnings": len(warnings),
                "critical": len(critical_issues)
            }
        }

        return JSONResponse(status_code=status_code, content=response_data)

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": f"Health check system failure: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/health/simple")
async def simple_health_check():
    """Simple health check for basic container readiness."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "caseguard-api"
    }


@app.get("/metrics")
async def get_metrics():
    """Get basic system metrics for monitoring."""
    try:
        return {
            "metrics": [
                {
                    "name": "api_uptime",
                    "value": 1,
                    "type": "gauge",
                    "timestamp": datetime.utcnow().isoformat(),
                    "labels": {"service": "caseguard-api"}
                }
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics collection failed: {str(e)}")


@app.get("/status")
async def get_system_status():
    """Get basic system status information."""
    try:
        return {
            "system_status": {
                "service": "caseguard-api",
                "version": "2.0.0",
                "environment": os.getenv("CASEGUARD_ENV", "development"),
                "uptime": "running"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting CaseGuard V2 API...")
    logger.info(f"Environment: {os.getenv('CASEGUARD_ENV', 'development')}")
    logger.info(f"Log Level: {os.getenv('LOG_LEVEL', 'INFO')}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down CaseGuard V2 API...")


if __name__ == "__main__":
    # Run with uvicorn for development
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )