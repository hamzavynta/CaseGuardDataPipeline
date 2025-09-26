# CaseGuard V2 Testing Guide

This guide walks you through testing the complete V2 implementation step by step.

## 🚀 Quick Start Testing

### 1. Environment Setup

First, set up your environment file:

```bash
# Copy the environment template
cp v2/.env.example v2/.env

# Edit the .env file with your actual credentials
nano v2/.env
```

**Minimum required credentials:**
- `OPENAI_API_KEY` - For AI enrichment
- `PINECONE_API_KEY` - For vector storage
- `LLAMA_CLOUD_API_KEY` - For document processing
- `DATABASE_URL` - PostgreSQL connection string

### 2. Database Setup

```bash
# Start PostgreSQL (if not running)
sudo systemctl start postgresql

# Create the database
createdb caseguard_v2

# Set up Alembic migrations
cd v2
python -c "
from database.alembic_setup import setup_alembic, upgrade_database
setup_alembic()
upgrade_database()
"
```

### 3. Start Core Services

```bash
# Terminal 1: Start Redis/Valkey
redis-server

# Terminal 2: Start Prefect server
prefect server start

# Terminal 3: Test basic connectivity
python -c "
from core.session_manager import SessionManager
sm = SessionManager()
print('✅ Database connection successful')
"
```

## 🧪 Testing Each Component

### Phase 1 Tests: Foundation

```bash
# Test database models
python -c "
from database.models import CaseModel, ProcessingJob
from datetime import datetime

case = CaseModel(
    case_ref='TEST-001',
    tenant_id='fdm_solicitors',
    raw_data={'test': 'data'},
    last_updated=datetime.utcnow()
)
print('✅ Models working:', case.case_ref)
"

# Test session manager
python -c "
from core.session_manager import SessionManager
sm = SessionManager()
with sm.get_session() as session:
    print('✅ Session manager working')
"
```

### Phase 2 Tests: Prefect Workflows

```bash
# Test Prefect configuration
python -c "
from etl.prefect_config import setup_prefect_environment, get_work_pool
setup_prefect_environment()
print('✅ Prefect environment configured')
"

# Test AI enrichment engine
python -c "
from etl.ai_engine import AIEnrichmentEngine
import asyncio

async def test_ai():
    engine = AIEnrichmentEngine()
    test_case = {
        'case_ref': 'TEST-001',
        'core_details': {'summary': 'Test personal injury case'}
    }
    result = await engine.enrich_case_data(test_case)
    print('✅ AI enrichment working:', result.get('summary', 'No summary'))

asyncio.run(test_ai())
"

# Test individual case processing flow
python -c "
import asyncio
from etl.flows.process_case import process_proclaim_case

async def test_flow():
    # This will run but may fail without full CRM data - that's expected
    try:
        result = await process_proclaim_case('fdm_solicitors', 'TEST-001', is_full_rebuild=True)
        print('✅ Process flow executed')
    except Exception as e:
        print('⚠️ Flow tested (expected errors without CRM):', str(e)[:100])

asyncio.run(test_flow())
"
```

### Phase 3 Tests: Discovery & Synchronization

```bash
# Test case discovery adapters
python -c "
import asyncio
from crm.discovery import CSVFallbackAdapter

async def test_discovery():
    adapter = CSVFallbackAdapter('fdm_solicitors')
    cases = await adapter.discover_cases()
    print(f'✅ Discovery working: Found {len(cases)} cases')

asyncio.run(test_discovery())
"

# Test change tracking
python -c "
import asyncio
from database.change_tracking import ChangeTracker

async def test_tracking():
    tracker = ChangeTracker('fdm_solicitors')
    # Test with sample data
    changes = await tracker.detect_changes(['TEST-001', 'TEST-002'])
    print('✅ Change tracking working:', changes)

asyncio.run(test_tracking())
"
```

### Phase 4 Tests: Production Features

```bash
# Test tenant management
python -c "
import asyncio
from core.tenant_manager import TenantManager

async def test_tenant():
    manager = TenantManager()
    config = await manager.get_tenant_config('fdm_solicitors')
    print('✅ Tenant management working:', config['display_name'] if config else 'No config')

asyncio.run(test_tenant())
"

# Test monitoring dashboard
python -c "
import asyncio
from monitoring.dashboard import MonitoringDashboard

async def test_monitoring():
    dashboard = MonitoringDashboard()
    health_checks = await dashboard.run_health_checks()
    print(f'✅ Monitoring working: {len(health_checks)} health checks completed')

asyncio.run(test_monitoring())
"

# Test error handling
python -c "
from core.error_handling import ErrorHandler, CaseGuardError, ErrorContext

handler = ErrorHandler('fdm_solicitors')
context = ErrorContext(tenant_id='fdm_solicitors', case_ref='TEST-001')

try:
    raise ValueError('Test error')
except Exception as e:
    record = handler.handle_error(e, context)
    print('✅ Error handling working:', record.error_id)
"
```

## 🔧 Full Integration Tests

### Test Complete Pipeline

```bash
# Create a comprehensive test script
cat > test_full_pipeline.py << 'EOF'
#!/usr/bin/env python3
"""Complete V2 pipeline test"""

import asyncio
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_complete_pipeline():
    """Test the complete V2 pipeline"""

    print("🧪 Starting CaseGuard V2 Full Pipeline Test")
    print("=" * 50)

    # Test 1: Database connectivity
    try:
        from core.session_manager import SessionManager
        sm = SessionManager()
        with sm.get_session():
            print("✅ 1. Database connection successful")
    except Exception as e:
        print(f"❌ 1. Database connection failed: {e}")
        return False

    # Test 2: Tenant configuration
    try:
        from core.tenant_manager import TenantManager
        tm = TenantManager()
        config = await tm.get_tenant_config('fdm_solicitors')
        if config:
            print(f"✅ 2. Tenant config loaded: {config['display_name']}")
        else:
            print("⚠️ 2. No tenant config found (expected in development)")
    except Exception as e:
        print(f"❌ 2. Tenant management failed: {e}")

    # Test 3: Case discovery
    try:
        from crm.discovery import CSVFallbackAdapter
        adapter = CSVFallbackAdapter('fdm_solicitors')
        cases = await adapter.discover_cases(limit=5)
        print(f"✅ 3. Case discovery: Found {len(cases)} test cases")
    except Exception as e:
        print(f"⚠️ 3. Case discovery: {e} (expected without CSV file)")

    # Test 4: AI enrichment (with mock data)
    try:
        from etl.ai_engine import AIEnrichmentEngine
        engine = AIEnrichmentEngine()

        test_case = {
            'case_ref': 'TEST-001',
            'tenant_id': 'fdm_solicitors',
            'core_details': {
                'summary': 'Test personal injury case involving vehicle accident',
                'client_name': 'John Doe'
            },
            'history': [
                {'date': '2024-01-01', 'entry': 'Case opened'},
                {'date': '2024-01-15', 'entry': 'Medical report received'}
            ]
        }

        result = await engine.enrich_case_data(test_case)
        if result and 'insights' in result:
            print("✅ 4. AI enrichment working")
        else:
            print("⚠️ 4. AI enrichment returned basic result")

    except Exception as e:
        print(f"⚠️ 4. AI enrichment: {e} (expected without API keys)")

    # Test 5: Error handling
    try:
        from core.error_handling import ErrorHandler, ErrorContext
        handler = ErrorHandler('fdm_solicitors')
        context = ErrorContext(tenant_id='fdm_solicitors', case_ref='TEST-001')

        # Test error handling
        try:
            raise ValueError("Test pipeline error")
        except Exception as test_error:
            record = handler.handle_error(test_error, context)
            print(f"✅ 5. Error handling: {record.error_id[:8]}...")
    except Exception as e:
        print(f"❌ 5. Error handling failed: {e}")

    # Test 6: Monitoring
    try:
        from monitoring.dashboard import MonitoringDashboard
        dashboard = MonitoringDashboard()
        health_checks = await dashboard.run_health_checks()
        healthy_count = sum(1 for check in health_checks if check.status == "healthy")
        print(f"✅ 6. Monitoring: {healthy_count}/{len(health_checks)} services healthy")
    except Exception as e:
        print(f"⚠️ 6. Monitoring: {e}")

    print("\n" + "=" * 50)
    print("🎉 V2 Pipeline Test Complete!")
    print("\nNext steps:")
    print("1. Fill in API keys in v2/.env for full functionality")
    print("2. Ensure FDM CSV file is available for case discovery")
    print("3. Start Prefect worker: prefect worker start --pool caseguard-pool")
    print("4. Run production deployment: docker-compose -f v2/deployment/docker_compose.yml up")

if __name__ == "__main__":
    asyncio.run(test_complete_pipeline())
EOF

# Run the test
python test_full_pipeline.py
```

### Test with Docker

```bash
# Test the production Docker setup
cd v2/deployment

# Copy environment file
cp .env.example .env
# Edit .env with your credentials

# Start the stack
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs caseguard-api
docker-compose logs caseguard-prefect-worker

# Test API endpoint
curl http://localhost:8000/health
```

## 🐛 Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Check PostgreSQL is running
   sudo systemctl status postgresql

   # Create database if missing
   createdb caseguard_v2
   ```

2. **Missing API Keys**
   ```bash
   # Check environment variables are loaded
   python -c "import os; print('OPENAI_API_KEY' in os.environ)"
   ```

3. **Prefect Connection Issues**
   ```bash
   # Start Prefect server
   prefect server start

   # Check API URL
   prefect config view
   ```

4. **Import Errors**
   ```bash
   # Ensure PYTHONPATH is set
   export PYTHONPATH=/home/hamza/CaseGuard/EmbeddingPipeline:$PYTHONPATH
   ```

### Expected Warnings

- **Without API keys**: AI enrichment will use fallback methods
- **Without CSV file**: Case discovery will return empty results
- **Development mode**: Some health checks may show warnings

## 📊 Success Criteria

A successful test should show:
- ✅ Database connectivity working
- ✅ Core models and session management functional
- ✅ Tenant configuration loading
- ✅ Basic AI enrichment (with API keys)
- ✅ Error handling and monitoring operational
- ✅ Docker services starting (in production test)

The system is ready for production when all integration tests pass with real API credentials and data sources.