# CaseGuard DataPipelines V2

Multi-tenant data pipeline architecture for legal case management and AI-driven insights.

## Features

- **Multi-tenant architecture** with strict data isolation
- **AI-powered case enrichment** using OpenAI GPT models
- **Vector search capabilities** with Pinecone integration
- **Prefect workflow orchestration** for reliable processing
- **Document processing** with LlamaParse integration
- **Comprehensive monitoring** and health checks

## Quick Start

1. **Install dependencies**:
   ```bash
   poetry install --with dev
   ```

2. **Set up environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Initialize database**:
   ```bash
   poetry run python -c "
   from database.alembic_setup import setup_alembic, upgrade_database
   setup_alembic()
   upgrade_database()
   "
   ```

4. **Run tests**:
   ```bash
   poetry run python test_full_pipeline.py
   ```

## Documentation

- [Development Commands](./CLAUDE.md)
- [Testing Guide](./TESTING_GUIDE.md)

## Architecture

Built on a microservices architecture with:
- FastAPI web framework
- PostgreSQL database with SQLAlchemy ORM
- Redis for caching and job queuing
- Prefect for workflow orchestration
- Docker for containerization

## License

Proprietary - VyntaLab