# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup

```bash
# Add core dependencies using Poetry (let Poetry choose compatible versions)
poetry add fastapi uvicorn[standard] sqlalchemy alembic psycopg[binary]
poetry add pydantic pandas prefect openai pinecone-client llama-parse
poetry add redis requests aiohttp httpx pyyaml python-dotenv python-multipart
poetry add python-jose[cryptography] passlib[bcrypt] python-dateutil
poetry add prometheus-client structlog python-magic

# Add development dependencies
poetry add --group dev pytest pytest-asyncio black isort flake8 mypy pre-commit

# Install all dependencies
poetry install --with dev

# Copy environment configuration
cp .env.example .env
# Edit .env file with actual credentials

# Database setup (managed PostgreSQL database already configured)
poetry run python -c "
from database.alembic_setup import setup_alembic, upgrade_database
setup_alembic()
upgrade_database()
"
```

### Development Services

```bash
# Start core services for development
redis-server                          # Terminal 1 (local Redis instance)
poetry run prefect server start       # Terminal 2

# Test database connectivity
poetry run python -c "
from core.session_manager import SessionManager
sm = SessionManager()
with sm.get_session() as session:
    print('✅ Database connection successful')
"
```

### Running Tests

```bash
# Run the comprehensive test pipeline
poetry run python test_full_pipeline.py

# Test individual components
poetry run python -c "
from core.session_manager import V2SessionManager
sm = V2SessionManager()
with sm.bulk_processing_session() as session:
    print('✅ Session manager working')
"

# Test AI enrichment
poetry run python -c "
import asyncio
from etl.ai_engine import AIEnrichmentEngine

async def test_ai():
    engine = AIEnrichmentEngine()
    test_case = {
        'case_ref': 'TEST-001',
        'core_details': {'summary': 'Test case'}
    }
    result = await engine.enrich_case_data(test_case)
    print('✅ AI enrichment working')

asyncio.run(test_ai())
"

# Run pytest tests
poetry run pytest tests/ -v

# Run code formatting and linting
poetry run black .
poetry run isort .
poetry run flake8 .
poetry run mypy .
```

### Production Deployment

```bash
# Docker deployment
cd deployment
docker-compose up -d

# Check service health
docker-compose ps
curl http://localhost:8000/health

# View logs
docker-compose logs caseguard-api
docker-compose logs caseguard-prefect-worker
```

### Running Flows

```bash
# Process individual case
poetry run python -c "
import asyncio
from etl.flows.process_case import process_proclaim_case

async def test_flow():
    result = await process_proclaim_case('fdm_solicitors', 'TEST-001', is_full_rebuild=True)
    print(f'✅ Case processed: {result}')

asyncio.run(test_flow())
"

# Start Prefect worker
poetry run prefect worker start --pool caseguard-pool
```

## Architecture Overview

### Core Architecture Pattern

CaseGuard V2 follows a **multi-tenant data pipeline architecture** with these key principles:

- **Tenant Isolation**: Strict separation of law firm data using tenant_id metadata filters
- **Prefect Orchestration**: All processing flows managed through Prefect for reliability and monitoring
- **AI-First Enrichment**: Cases are enriched with AI insights before canonical field extraction
- **Vector Search**: Embedded case data in Pinecone for semantic search capabilities
- **Fallback Adapters**: CRM integration supports multiple data sources (CSV, YAML, API)

### Directory Structure

```
├── core/                    # Core services and session management
├── etl/                     # Prefect flows and processing pipelines
│   └── flows/              # Individual case processing flows
├── database/               # Models and change tracking
├── crm/                    # CRM integration and discovery adapters
├── ai/                     # AI enrichment engine
├── proclaim/               # Proclaim API status detection
├── docproc/                # Document processing configuration
├── monitoring/             # Health checks and dashboard
├── configs/                # Tenant configurations
│   └── tenants/           # Per-tenant JSON configurations
└── deployment/            # Docker and production deployment
```

### Multi-Tenant Design

The system supports multiple law firms (tenants) with complete data isolation:

- **Tenant Configs**: Each tenant has a JSON configuration in `configs/tenants/`
- **Database Isolation**: Tenant-specific schemas and metadata filters
- **Vector Isolation**: Pinecone metadata filters ensure cross-tenant privacy
- **Processing Limits**: Per-tenant concurrency and rate limiting
- **CRM Adapters**: Tenant-specific CRM integration strategies

### Key Flows

#### `process_proclaim_case` (etl/flows/process_case.py)

Primary case processing flow with three stages:

1. **Data Ingestion**: Fetch raw case data from Proclaim CRM
2. **AI Enrichment**: Generate insights without canonical field dependencies
3. **Vector Population**: Create embeddings and index in Pinecone

#### Session Management (core/session_manager.py)

Enhanced Proclaim session handling with:

- Bulk processing session context managers
- Graceful shutdown signal handling
- Session age validation and cleanup
- Multi-session tracking for concurrent operations

#### Tenant Management (core/tenant_manager.py)

Multi-tenant configuration system providing:

- Dynamic tenant configuration loading
- Per-tenant processing limits and quotas
- Vector configuration with isolation metadata
- CRM credential resolution from environment variables

### CRM Integration Strategy

Due to Proclaim API limitations, the system uses adaptive fallback mechanisms:

#### CSVFallbackAdapter (Primary for FDM)

- **Data Source**: "FDM example Funded Cases.csv" with 2117 cases
- **Capabilities**: Case discovery, status filtering, batch processing
- **Limitation**: Static data requiring manual updates

#### YAMLFallbackAdapter (Legacy)

- **Data Source**: config/cases.yaml
- **Use Case**: Manual case list management and testing

#### ProclaimCRMAdapter (Future)

- **Status**: Awaiting enhanced API endpoints from Proclaim
- **Requirements**: Bulk case enumeration, change detection, high-watermark sync
- **Critical Missing**: `/api/tenant/{tenant_id}/cases` endpoint

### AI Enrichment Pipeline

The AI system generates structured insights without canonical field dependencies:

```python
# AI insights structure
{
    "ai_insights": {
        "case_summary": "AI-generated summary",
        "key_issues": ["Contract dispute", "Payment delay"],
        "settlement_likelihood": 0.65,
        "risk_factors": ["Statute of limitations"],
        "recommended_actions": ["Review documentation"]
    },
    "confidence_score": 0.82
}
```

### Vector Architecture

Uses OpenAI embeddings with Pinecone for semantic search:

- **Model**: text-embedding-3-large (3072 dimensions)
- **Indexes**: Shared indexes with tenant metadata isolation
- **Types**: Summary vectors and detail vectors per case
- **Isolation**: Tenant ID metadata filters prevent cross-tenant data access

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/caseguard_v2

# AI Services
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
LLAMA_CLOUD_API_KEY=llx-...

# CRM Credentials
PROCLAIM_USERNAME=...
PROCLAIM_PASSWORD=...

# Prefect
PREFECT_API_URL=http://localhost:4200/api

# Optional Monitoring
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

### Development Considerations

#### Testing Strategy

Use the comprehensive test script in TESTING_GUIDE.md which validates:

- Database connectivity and models
- Tenant configuration loading
- AI enrichment functionality
- Vector embedding and indexing
- Error handling and monitoring
- Complete pipeline integration

#### Error Handling

The system implements robust error handling through:

- **ErrorHandler** class for structured error capture
- **ErrorContext** for tenant and case-specific error tracking
- Prefect task retries with exponential backoff
- Graceful degradation when external services are unavailable

#### Performance Optimization

- **Concurrent Processing**: Configurable per-tenant concurrency limits
- **Session Reuse**: Bulk processing sessions minimize API overhead
- **Vector Batching**: Efficient Pinecone upserts for multiple cases
- **Change Detection**: High-watermark sync when CRM APIs support it

#### Monitoring Integration

Built-in health checks and monitoring through:

- **MonitoringDashboard**: Comprehensive system health validation
- **Grafana Integration**: Production monitoring dashboards
- **Prometheus Metrics**: Performance and error rate tracking
- **Health Endpoints**: `/health` API for container orchestration

### Production Deployment Notes

#### Docker Architecture

- **caseguard-api**: Main API service with health checks
- **caseguard-prefect-worker**: Distributed processing workers
- **postgres**: Database with persistent volumes
- **valkey**: Redis-compatible caching and job queuing
- **prefect-server**: Workflow orchestration server
- **grafana/prometheus**: Monitoring stack
- **nginx**: Reverse proxy with SSL termination

#### Scaling Considerations

- Workers scale horizontally via `WORKER_REPLICAS`
- Database connection pooling configured per tenant
- Vector indexes shared across tenants for efficiency
- Rate limiting prevents CRM API overload

#### Security Features

- Tenant data isolation through database schemas
- Vector metadata filtering prevents cross-tenant access
- Environment variable credential resolution
- GDPR compliance configuration per tenant
- Audit logging for sensitive operations

### Common Development Patterns

When adding new functionality:

1. **Check tenant configuration** for feature flags and limits
2. **Use session managers** for CRM API interactions
3. **Implement proper error handling** with ErrorContext
4. **Add vector isolation** metadata for multi-tenant safety
5. **Update health checks** for new service dependencies
6. **Follow Prefect patterns** for new processing flows
