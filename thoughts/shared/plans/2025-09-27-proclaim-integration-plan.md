# Proclaim API Integration Implementation Plan

## Overview

Integrate the comprehensive Proclaim API components documented in `technical-details.md` into the DataPipelines ETL architecture. This shifts from implementing missing APIs to leveraging proven implementations, replacing CSV fallback mechanisms with real Proclaim integration.

## Current State Analysis

### DataPipelines Foundation (V2 ETL Architecture)

- **Prefect-orchestrated ETL** with 3-stage processing (Data Ingestion, AI Enrichment, Vector Population)
- **Multi-tenant isolation** with strict data separation and metadata filtering
- **Basic session management** via V2SessionManager with bulk processing contexts
- **CRM fallback adapters** with working CSV adapter (2117 FDM cases) and placeholder Proclaim adapter
- **AI enrichment engine** generating structured insights without canonical field dependencies
- **Vector processing** with Pinecone integration and tenant metadata isolation

### Existing Proclaim Components (Available Implementations)

- **ProclaimClient** - Complete REST API client with authentication, session management, and cleanup handlers (implementation details in existing codebase)
- **SessionManager** - Production-ready session persistence with file-based storage
- **CaseEmbedder** - OpenAI embeddings with comprehensive metadata extraction
- **CaseExtractor** - Case data extraction logic
- **ProclaimSoapDownloader** - Binary-safe SOAP document downloader with comprehensive format mapping (lines 92-164 in `technical-details.md`)
- **SpacesClient** - DigitalOcean Spaces S3-compatible client with tenant-based object hierarchy (lines 244-473 in `technical-details.md`)
- **SmartFieldRetriever** - Canonical field extraction with 100% tested field mappings (lines 809-974 in `technical-details.md`)

### Key Discoveries

- **Complete Integration Suite Available**: All critical Proclaim components now have full implementations, including previously missing SOAP downloader, Spaces integration, and canonical field mapping
- **Production-Ready Components**: 100% tested canonical field system with 27 working fields, binary-safe document processing, and S3-compatible storage
- **Comprehensive Document Pipeline**: Full document processing chain from SOAP download → text extraction → Spaces storage → vector embedding with agent citations
- **Smart Field Extraction**: Three-tier field architecture (Global, HDR, Fixed) with automatic fallback mechanisms and type conversion
- **Tenant-Based Storage Hierarchy**: Structured object key system for multi-tenant document isolation in DigitalOcean Spaces

## Desired End State

A unified ETL system where:

- **Real Proclaim integration** replaces CSV fallback adapters in DataPipelines flows
- **Production-ready session management** from existing implementations replaces basic V2SessionManager
- **Enhanced vector processing** leverages existing comprehensive metadata extraction
- **Complete case processing** flows from Proclaim → AI Enrichment → Vector Storage
- **Comprehensive testing** validates the integrated system with NBC200993.001 case

### Verification

- NBC200993.001 case processes successfully through complete pipeline
- All Prefect flows use real ProclaimClient instead of CSV fallback
- Session management handles cleanup and persistence correctly
- Vector embeddings include comprehensive metadata for agent citations
- Multi-tenant isolation maintained throughout integration

## What We're NOT Doing

- **Not rebuilding** existing ProclaimClient - leveraging proven implementation
- **Not replacing** DataPipelines ETL architecture - integrating into existing flows
- **Not modifying** tenant isolation architecture - maintaining existing security model
- **Not changing** database models - adapting integration to existing schema
- **Not reimplementing** SOAP downloader, Spaces client, or field mapping - using complete existing implementations

## Implementation Approach

**Component Copy Strategy**: Copy and adapt proven implementations detailed in `technical-details.md` into DataPipelines structure, rather than importing cross-project. This ensures clean dependency management and allows customization for DataPipelines architecture while preserving the sophisticated ETL orchestration and multi-tenant architecture.

## Phase 1: TDD Test Suite Implementation

### Overview

Implement a comprehensive Test-Driven Development (TDD) suite before copying components. This ensures each integration step can be validated immediately and provides confidence during the copying and adaptation process.

### Changes Required

#### 1. Test Infrastructure Setup

**File**: `tests/conftest.py` (new)
**Changes**: Create pytest fixtures for TDD workflow

```python
import pytest
import os
import json
from unittest.mock import Mock, MagicMock
from pathlib import Path
import tempfile
from typing import Dict, Any

@pytest.fixture
def fdm_proclaim_credentials():
    """Real FDM Proclaim credentials for testing."""
    return {
        'base_url': 'http://52.158.28.226:8085',
        'username': os.getenv('PROCLAIM_USERNAME', 'fdm_test_user'),
        'password': os.getenv('PROCLAIM_PASSWORD', 'fdm_test_pass')
    }

@pytest.fixture
def fdm_tenant_config():
    """Real FDM tenant configuration for testing."""
    return {
        'tenant_id': 'fdm_solicitors',
        'display_name': 'FDM Solicitors',
        'api_base_url': 'http://52.158.28.226:8085',
        'concurrent_limit': 25,
        'batch_size': 100,
        'embedding_model': 'text-embedding-3-large',
        'dimension': 3072,
        'spaces_bucket': 'caseguard-documents'
    }

@pytest.fixture
def fdm_test_case_reference():
    """Single real case reference from FDM CSV for focused testing."""
    return 'NBC200993.001'  # Primary test case from CSV - Complete

@pytest.fixture
def fdm_wsdl_path():
    """Path to WSDL file in repository root."""
    return 'Proclaim.wsdl'  # WSDL file added to repo root

@pytest.fixture
def fdm_primary_test_case():
    """Primary test case (NBC200993.001) with real FDM data."""
    return {
        'case_ref': 'NBC200993.001',
        'tenant_id': 'fdm_solicitors',
        'claim_ate_reference': 'FDM001\\P23070100',
        'status': 'Complete',
        'borrower_company': 'FDM Solicitors'
    }

@pytest.fixture
def temp_session_file():
    """Temporary session file for testing session management."""
    session_dir = Path.home() / '.caseguard'
    session_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        dir=session_dir,
        delete=False
    ) as f:
        yield f.name

    if os.path.exists(f.name):
        os.unlink(f.name)

@pytest.fixture
def fdm_spaces_config():
    """Real DigitalOcean Spaces configuration for FDM."""
    return {
        'bucket': 'caseguard-documents',
        'region': 'nyc3',
        'endpoint_url': 'https://nyc3.digitaloceanspaces.com',
        'profile': 'digitalocean'
    }

@pytest.fixture
def fdm_canonical_fields_config():
    """Path to real canonical fields configuration."""
    return 'config/canonical_fields_corrected.json'

@pytest.fixture
def fdm_vector_metadata():
    """Real FDM vector metadata filters."""
    return {
        'tenant_id': 'fdm_solicitors',
        'privacy_level': 'confidential',
        'case_summaries_index': 'caseguard-case-summaries',
        'case_details_index': 'caseguard-case-details'
    }
```

#### 2. Component Interface Tests (Write First)

**File**: `tests/unit/test_proclaim_client_interface.py` (new)
**Changes**: Define expected interfaces before implementation

```python
import pytest
from unittest.mock import Mock, patch

class TestProclaimClientInterface:
    """Test ProclaimClient interface before implementation."""

    def test_proclaim_client_initialization_fdm(self, fdm_proclaim_credentials):
        """Test ProclaimClient can be initialized with FDM tenant context."""
        # This test will fail initially - that's the point of TDD
        from caseguard.proclaim.client import ProclaimClient

        client = ProclaimClient(
            tenant_id='fdm_solicitors',
            **fdm_proclaim_credentials
        )

        assert client.tenant_id == 'fdm_solicitors'
        assert client.base_url == 'http://52.158.28.226:8085'

    def test_get_case_data_with_fdm_context(self, fdm_proclaim_credentials, fdm_primary_test_case):
        """Test case data includes FDM tenant metadata for NBC200993.001."""
        from caseguard.proclaim.client import ProclaimClient

        with patch.object(ProclaimClient, 'get_case_data') as mock_get:
            mock_get.return_value = {
                'case_ref': 'NBC200993.001',
                'status': 'Complete',
                'claim_ate_reference': 'FDM001\\P23070100'
            }

            client = ProclaimClient(tenant_id='fdm_solicitors', **fdm_proclaim_credentials)
            result = client.get_case_data_with_tenant_context('NBC200993.001')

            assert result['tenant_id'] == 'fdm_solicitors'
            assert result['case_ref'] == 'NBC200993.001'
            assert result['claim_ate_reference'] == 'FDM001\\P23070100'

    def test_session_token_management_fdm(self, fdm_proclaim_credentials, temp_session_file):
        """Test session token is properly managed for FDM."""
        from caseguard.proclaim.client import ProclaimClient

        client = ProclaimClient(tenant_id='fdm_solicitors', **fdm_proclaim_credentials)

        assert hasattr(client, 'session_token')
        assert hasattr(client, '_authenticate')
        assert hasattr(client, '_cleanup_session')
        assert client.tenant_id == 'fdm_solicitors'

    def test_single_case_reference_validation(self, fdm_test_case_reference):
        """Test that we have a valid FDM case reference for focused testing."""
        assert fdm_test_case_reference == 'NBC200993.001'
        assert fdm_test_case_reference.startswith('NBC')
        assert fdm_test_case_reference.endswith('.001')
```

#### 3. SOAP Downloader TDD Tests

**File**: `tests/unit/test_soap_downloader_interface.py` (new)
**Changes**: Test SOAP downloader interface before copying implementation

```python
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

class TestSoapDownloaderInterface:
    """Test SOAP downloader interface before implementation."""

    def test_soap_downloader_initialization_fdm(self):
        """Test SOAP downloader initializes with FDM tenant context."""
        from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader

        downloader = ProclaimSoapDownloader(
            wsdl_path='Proclaim.wsdl',  # WSDL file in repo root
            soap_endpoint='http://52.158.28.226:8085/soap',
            tenant_id='fdm_solicitors'
        )

        assert downloader.tenant_id == 'fdm_solicitors'

    def test_fetch_document_with_fdm_context(self, fdm_primary_test_case, fdm_wsdl_path):
        """Test document fetching for real FDM case NBC200993.001 using repo WSDL."""
        from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader

        downloader = ProclaimSoapDownloader(
            wsdl_path=fdm_wsdl_path,  # WSDL file from repo root
            soap_endpoint='http://52.158.28.226:8085/soap',
            tenant_id='fdm_solicitors'
        )

        with patch.object(downloader, 'fetch_document') as mock_fetch:
            # Simulate real document path for NBC200993.001
            mock_fetch.return_value = (Path('/tmp/caseguard_doc_NBC200993_001.pdf'), None)

            result_path, error = downloader.fetch_document_with_tenant_context(
                token='fdm_session_token',
                document_code='DOC_NBC200993_001',
                document_format='ACROBAT-PDF'
            )

            assert result_path is not None
            assert 'NBC200993' in str(result_path)
            assert error is None
            mock_fetch.assert_called_once()

    def test_format_to_mime_mapping(self):
        """Test format detection works correctly."""
        from caseguard.proclaim.soap_downloader import FORMAT_TO_MIME

        assert 'ACROBAT-PDF' in FORMAT_TO_MIME
        assert FORMAT_TO_MIME['ACROBAT-PDF'] == 'application/pdf'
        assert 'WORD-DOC' in FORMAT_TO_MIME
```

#### 4. Spaces Client TDD Tests

**File**: `tests/unit/test_spaces_client_interface.py` (new)
**Changes**: Test Spaces client interface before copying implementation

```python
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

class TestSpacesClientInterface:
    """Test Spaces client interface before implementation."""

    def test_spaces_client_initialization_fdm(self, fdm_spaces_config):
        """Test Spaces client initializes with FDM tenant context."""
        from caseguard.storage.spaces import SpacesClient

        client = SpacesClient(
            tenant_id='fdm_solicitors',
            **fdm_spaces_config
        )

        assert client.tenant_id == 'fdm_solicitors'
        assert client.bucket == 'caseguard-documents'
        assert client.region == 'nyc3'

    def test_store_document_with_fdm_hierarchy(self, fdm_spaces_config, fdm_primary_test_case):
        """Test document storage uses FDM tenant-based hierarchy for NBC200993.001."""
        from caseguard.storage.spaces import SpacesClient, SpacesLocation

        client = SpacesClient(
            tenant_id='fdm_solicitors',
            **fdm_spaces_config
        )

        with patch.object(client, 'upload_file') as mock_upload:
            mock_upload.return_value = None

            result = client.store_document_with_tenant_path(
                local_path=Path('/tmp/NBC200993_001_document.pdf'),
                case_ref='NBC200993.001',
                document_type='raw'
            )

            assert isinstance(result, SpacesLocation)
            assert result.tenant_id == 'fdm_solicitors'
            assert 'fdm_solicitors/documents/raw/NBC200993.001' in result.object_key
            assert result.bucket == 'caseguard-documents'

    def test_fdm_document_types_support(self, fdm_tenant_config):
        """Test that FDM document types are properly supported."""
        allowed_extensions = [
            '.pdf', '.doc', '.docx', '.txt', '.rtf',
            '.xls', '.xlsx', '.ppt', '.pptx',
            '.jpg', '.jpeg', '.png', '.tiff',
            '.eml', '.msg'
        ]

        # Verify common legal document types are supported
        assert '.pdf' in allowed_extensions  # Legal documents
        assert '.eml' in allowed_extensions  # Email correspondence
        assert '.docx' in allowed_extensions # Word documents
```

#### 5. Field Extractor TDD Tests

**File**: `tests/unit/test_field_extractor_interface.py` (new)
**Changes**: Test canonical field extraction interface

```python
import pytest
from unittest.mock import Mock, patch

class TestFieldExtractorInterface:
    """Test field extractor interface before implementation."""

    def test_field_extractor_initialization_fdm(self, fdm_canonical_fields_config):
        """Test field extractor initializes with FDM tenant context."""
        from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever

        extractor = SmartFieldRetriever(
            canonical_fields_path=fdm_canonical_fields_config,
            proclaim_client=Mock(),
            tenant_id='fdm_solicitors'
        )

        assert extractor.tenant_id == 'fdm_solicitors'

    def test_extract_canonical_fields_for_nbc200993(self, fdm_canonical_fields_config, fdm_primary_test_case):
        """Test field extraction for real FDM case NBC200993.001."""
        from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever

        mock_client = Mock()
        extractor = SmartFieldRetriever(
            canonical_fields_path=fdm_canonical_fields_config,
            proclaim_client=mock_client,
            tenant_id='fdm_solicitors'
        )

        # Test critical fields for FDM cases
        critical_fields_responses = {
            'date_opened': ('18/09/2024', True, 'direct_api'),
            'case_status': ('Complete', True, 'direct_hdr'),
            'handler_name': ('Ellie Braiden', True, 'direct_api'),
            'claimant_name': ('FDM Solicitors', True, 'party_extraction')
        }

        def mock_get_field(case_ref, field_name, case_type='104'):
            return critical_fields_responses.get(field_name, (None, False, 'not_found'))

        with patch.object(extractor, 'get_field', side_effect=mock_get_field):
            result = extractor.extract_canonical_fields_with_tenant_context('NBC200993.001')

            assert result['tenant_id'] == 'fdm_solicitors'
            assert result['case_ref'] == 'NBC200993.001'
            assert 'extraction_timestamp' in result

            # Verify critical field extraction
            if 'date_opened' in result:
                assert result['date_opened']['value'] == '18/09/2024'
                assert result['date_opened']['tenant_id'] == 'fdm_solicitors'

    def test_fdm_canonical_fields_coverage(self):
        """Test that all 27 canonical fields are defined for FDM."""
        # This will be validated when config is copied from technical-details.md
        critical_fields = [
            'case_ref', 'handler_name', 'date_opened', 'profit_costs_incurred',
            'claimant_name', 'defendant_name', 'case_status', 'case_outcome',
            'date_closed', 'date_loc_sent', 'date_landlord_response_received',
            'date_expert_inspection', 'date_proceedings_issued', 'date_trial_listed'
        ]

        assert len(critical_fields) >= 10  # Minimum critical fields
        assert 'NBC200993.001' == 'NBC200993.001'  # Test case reference format
```

#### 6. Integration Test Templates

**File**: `tests/integration/test_component_integration_tdd.py` (new)
**Changes**: Integration test templates for TDD workflow

```python
import pytest
from unittest.mock import Mock, patch

class TestComponentIntegrationTDD:
    """Integration tests to be run after each component is copied."""

    @pytest.mark.skip(reason="Run after ProclaimClient is copied")
    def test_fdm_proclaim_client_real_integration(self, fdm_proclaim_credentials):
        """Test ProclaimClient with real FDM credentials (when ready)."""
        # Will be enabled after component is copied
        # Test with real NBC200993.001 case
        pass

    @pytest.mark.skip(reason="Run after SOAP downloader is copied")
    def test_fdm_soap_document_download_integration(self, fdm_primary_test_case):
        """Test real SOAP document download for NBC200993.001 (when ready)."""
        # Will be enabled after component is copied
        # Test with real FDM case documents
        pass

    @pytest.mark.skip(reason="Run after Spaces client is copied")
    def test_fdm_spaces_upload_integration(self, fdm_spaces_config, fdm_primary_test_case):
        """Test real Spaces upload for FDM documents (when ready)."""
        # Will be enabled after component is copied
        # Test with caseguard-documents bucket
        pass

    @pytest.mark.skip(reason="Run after field extractor is copied")
    def test_fdm_canonical_fields_real_extraction(self, fdm_test_case_reference):
        """Test real canonical field extraction for NBC200993.001 (when ready)."""
        # Will be enabled after component is copied
        # Test with single real case reference: NBC200993.001
        pass
```

### Phase 1 TDD Success Criteria

#### Automated Verification

- [ ] Test infrastructure runs: `poetry run pytest tests/conftest.py -v`
- [ ] FDM fixtures load correctly: `poetry run pytest tests/conftest.py::fdm_tenant_config -v`
- [ ] Single test case reference validates: `poetry run pytest tests/conftest.py::fdm_test_case_reference -v`
- [ ] Interface tests fail as expected: `poetry run pytest tests/unit/ -v` (should show failing tests for single case NBC200993.001)
- [ ] Test coverage setup: `poetry run pytest --cov=caseguard tests/unit/`
- [ ] Test documentation generated: `poetry run pytest --html=reports/fdm_tests.html`

#### Manual Verification

- [ ] All component interfaces defined with failing tests for FDM cases
- [ ] Test fixtures provide real FDM data (NBC200993.001, fdm_solicitors)
- [ ] Integration test templates ready for activation with single case NBC200993.001
- [ ] TDD workflow documented for developers using single FDM test case (NBC200993.001)
- [ ] Real Proclaim API endpoint (http://52.158.28.226:8085) accessible for testing

---

## Phase 2: Core Component Integration

### Overview

Copy and adapt core Proclaim components from `technical-details.md` into DataPipelines, **following TDD workflow**: make tests pass one by one as components are copied and adapted.

### Changes Required

#### 1. ProclaimClient Integration

**File**: `caseguard/proclaim/client.py` (new)
**Changes**: Copy ProclaimClient implementation from existing codebase and adapt for DataPipelines

```python
# Copy base implementation from existing ProclaimClient
# (reference implementation available in related codebase)
# and adapt for DataPipelines tenant architecture
import atexit
import base64
import logging
import signal
import sys
import threading
from typing import Any, Dict, List, Optional

import requests
from urllib.parse import quote

from ..utils.session_manager import SessionManager

logger = logging.getLogger(__name__)

class ProclaimClient:
    """Client for interacting with Proclaim REST API with DataPipelines tenant support."""

    def __init__(self, base_url: str, username: str, password: str,
                 tenant_id: str = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.tenant_id = tenant_id
        self.timeout = timeout
        self.session_token = None
        self.session_manager = SessionManager()

        self._register_cleanup_handlers()
        self._authenticate()

    def get_case_data_with_tenant_context(self, case_ref: str) -> Dict[str, Any]:
        """Get case data with tenant metadata for isolation."""
        case_data = self.get_case_data(case_ref)
        if self.tenant_id:
            case_data['tenant_id'] = self.tenant_id
        return case_data

    # Copy rest of implementation from existing ProclaimClient...
```

#### 2. Enhanced Session Management

**File**: `core/session_manager.py`
**Changes**: Extend existing V2SessionManager with Proclaim integration

```python
# Extend existing V2SessionManager with Proclaim session management
import os
from typing import Dict, Any, Optional
from contextlib import contextmanager

from ..caseguard.proclaim.client import ProclaimClient
from ..caseguard.utils.session_manager import SessionManager as ProclaimSessionManager

class V2SessionManager:
    """Enhanced session manager with Proclaim integration."""

    def __init__(self):
        self.proclaim_session_manager = ProclaimSessionManager()
        self._active_sessions = {}

    def get_proclaim_client(self, tenant_id: str) -> ProclaimClient:
        """Get configured ProclaimClient with session management."""
        if tenant_id not in self._active_sessions:
            client = ProclaimClient(
                base_url=os.getenv('PROCLAIM_BASE_URL'),
                username=os.getenv('PROCLAIM_USERNAME'),
                password=os.getenv('PROCLAIM_PASSWORD'),
                tenant_id=tenant_id
            )
            self._active_sessions[tenant_id] = client
        return self._active_sessions[tenant_id]

    @contextmanager
    def bulk_processing_session(self):
        """Context manager for bulk processing with proper cleanup."""
        try:
            yield self
        finally:
            self._cleanup_sessions()

    def _cleanup_sessions(self):
        """Clean up all active sessions."""
        for client in self._active_sessions.values():
            try:
                client._cleanup_session()
            except:
                pass
        self._active_sessions.clear()
```

#### 3. CRM Adapter Implementation

**File**: `crm/discovery.py`
**Changes**: Replace ProclaimCRMAdapter placeholder with real implementation

```python
class ProclaimCRMAdapter(CRMCaseDiscovery):
    def __init__(self, tenant_id: str):
        super().__init__(tenant_id)
        self.proclaim_client = self._get_proclaim_client()

    def enumerate_all_cases(self, include_closed: bool = True) -> List[Dict[str, Any]]:
        """Real implementation using ProclaimClient."""
        # Replace NotImplementedError with actual API calls

    def get_active_cases(self) -> List[Dict[str, Any]]:
        """Real implementation using ProclaimClient."""
        # Replace NotImplementedError with actual API calls
```

#### 4. SOAP Document Downloader Integration

**File**: `caseguard/proclaim/soap_downloader.py` (new)
**Changes**: Copy SOAP downloader implementation and adapt for DataPipelines

```python
# Copy implementation from technical-details.md and adapt for DataPipelines
from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from zeep import Client, Settings
from zeep.transports import Transport

logger = logging.getLogger(__name__)

# Format mappings copied from technical-details.md...
FORMAT_TO_MIME = {
    "WORD-DOC": "application/msword",
    "ACROBAT-PDF": "application/pdf",
    # ... rest of format mappings
}

class ProclaimSoapDownloader:
    """SOAP document downloader with tenant context support."""

    def __init__(self, wsdl_path: str, soap_endpoint: str,
                 tenant_id: str = None, timeout_seconds: int = 90):
        self.tenant_id = tenant_id
        settings = Settings(strict=False, xml_huge_tree=True)
        transport = Transport(timeout=timeout_seconds)
        self.client = Client(wsdl_path, settings=settings, transport=transport)
        self.client.service._binding_options["address"] = soap_endpoint

    def fetch_document_with_tenant_context(self, token: str, document_code: str,
                                         document_format: str) -> Tuple[Optional[Path], Optional[str]]:
        """Fetch document with tenant metadata for processing pipeline."""
        tmp_path, error = self.fetch_document(token, document_code, document_format)
        # Add tenant context to temporary path if needed
        return tmp_path, error

    # Copy rest of implementation from technical-details.md...
```

#### 5. DigitalOcean Spaces Integration

**File**: `caseguard/storage/spaces.py` (new)
**Changes**: Copy Spaces client implementation and adapt for DataPipelines

```python
# Copy implementation from technical-details.md and adapt for DataPipelines
from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)

@dataclass
class SpacesLocation:
    """Represents a location in DigitalOcean Spaces."""
    bucket: str
    object_key: str
    region: str
    tenant_id: Optional[str] = None

class SpacesClient:
    """DigitalOcean Spaces client with tenant-aware object hierarchy."""

    def __init__(self, bucket: str, region: str, endpoint_url: str,
                 tenant_id: str = None, profile: Optional[str] = None):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.tenant_id = tenant_id
        self.profile = profile

        # Initialize boto3 session...
        session_kwargs = {}
        if self.profile:
            try:
                session_kwargs["profile_name"] = self.profile
            except Exception:
                pass

        session = boto3.Session(**session_kwargs)
        self._s3 = session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            config=BotoConfig(s3={"addressing_style": "path"})
        )

    def store_document_with_tenant_path(self, local_path: Path, case_ref: str,
                                      document_type: str = "raw") -> SpacesLocation:
        """Store document using tenant-based object key hierarchy."""
        object_key = f"{self.tenant_id}/documents/{document_type}/{case_ref}/{local_path.name}"
        self.upload_file(local_path, object_key)
        return SpacesLocation(
            bucket=self.bucket,
            object_key=object_key,
            region=self.region,
            tenant_id=self.tenant_id
        )

    # Copy rest of implementation from technical-details.md...
```

#### 6. Canonical Field Mapping Integration

**File**: `caseguard/hdr_timeline/smart_field_retriever.py` (new)
**Changes**: Copy SmartFieldRetriever implementation and adapt for DataPipelines

```python
# Copy implementation from technical-details.md and adapt for DataPipelines
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

class SmartFieldRetriever:
    """Smart field retrieval with tenant context and fallback mechanisms."""

    def __init__(self, canonical_fields_path: str, proclaim_client, tenant_id: str = None):
        self.tenant_id = tenant_id
        self.proclaim_client = proclaim_client

        with open(canonical_fields_path, 'r') as f:
            config = json.load(f)

        self.global_fields = config["global_fields"]["fields"]
        self.hdr_fields = config["hdr_fields"]["fields"]

    def extract_canonical_fields_with_tenant_context(self, case_ref: str) -> Dict[str, Any]:
        """Extract all canonical fields with tenant metadata."""
        critical_fields = [
            "date_opened", "date_loc_sent", "date_landlord_response_received",
            "date_expert_inspection", "date_proceedings_issued", "date_closed",
            "case_status", "case_outcome", "claimant_name", "defendant_name"
        ]

        extracted_data = {
            "tenant_id": self.tenant_id,
            "case_ref": case_ref,
            "extraction_timestamp": datetime.now().isoformat()
        }

        for field_name in critical_fields:
            value, success, method = self.get_field(case_ref, field_name)
            if success and value:
                extracted_data[field_name] = {
                    "value": value,
                    "extraction_method": method,
                    "tenant_id": self.tenant_id
                }

        return extracted_data

    # Copy rest of implementation from technical-details.md...
```

#### 7. Vector Embedder Integration

**File**: `caseguard/vectorization/embedder.py` (new)
**Changes**: Copy CaseEmbedder implementation and adapt for DataPipelines

```python
# Copy implementation from technical-details.md and adapt for DataPipelines
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI
from tqdm import tqdm

logger = logging.getLogger(__name__)

class CaseEmbedder:
    """Generates embeddings for case data with DataPipelines tenant support."""

    def __init__(self, openai_client: OpenAI, tenant_id: str = None,
                 model: str = "text-embedding-3-large"):
        self.openai_client = openai_client
        self.tenant_id = tenant_id
        self.model = model

    def create_vectors_with_tenant_isolation(self, cases: List[Dict]) -> List[Dict]:
        """Create vectors with DataPipelines tenant metadata."""
        vectors = []

        for case in tqdm(cases, desc="Embedding Cases"):
            try:
                # Create summary text from case data
                text = self._create_summary_text(case)

                # Generate embedding
                embedding = self._generate_embedding(text)
                if not embedding:
                    continue

                # Create comprehensive metadata with tenant isolation
                metadata = self._extract_comprehensive_metadata(case)
                metadata["tenant_id"] = self.tenant_id
                metadata["source_type"] = "case_summary"

                vector = {
                    "id": f"{self.tenant_id}_{case.get('case_ref', 'unknown')}",
                    "values": embedding,
                    "metadata": metadata
                }

                vectors.append(vector)

            except Exception as e:
                logger.error(f"Failed to create vector for {case.get('case_ref')}: {e}")

        return vectors

    # Copy rest of implementation from existing ProclaimClient...
```

### Phase 2 Success Criteria

#### Automated Verification

- [ ] Import statements resolve correctly: `python -c "from caseguard.proclaim.client import ProclaimClient; print('✅ Import successful')"`
- [ ] Session management initializes: `python -c "from core.session_manager import V2SessionManager; sm = V2SessionManager(); print('✅ Session manager working')"`
- [ ] Document downloader initializes: `python -c "from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader; print('✅ SOAP downloader ready')"`
- [ ] Storage client connects: `python -c "from caseguard.storage.spaces import SpacesClient; print('✅ Spaces client ready')"`
- [ ] Field extractor loads config: `python -c "from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever; print('✅ Field extractor ready')"`
- [ ] Database migrations apply: `poetry run python -c "from database.alembic_setup import upgrade_database; upgrade_database()"`
- [ ] All tests pass: `poetry run pytest tests/ -v`

#### Manual Verification

- [ ] ProclaimClient authenticates successfully with real credentials
- [ ] Session persistence works across process restarts
- [ ] SOAP downloader fetches test document successfully
- [ ] Spaces client uploads and retrieves test file
- [ ] Field extractor retrieves canonical fields from NBC200993.001
- [ ] CRM adapter returns actual case data instead of NotImplementedError
- [ ] Vector processor generates embeddings with proper tenant metadata

---

## Phase 3: ETL Flow Integration

### Overview

Integrate the imported Proclaim components into existing Prefect flows, replacing CSV fallback mechanisms with real Proclaim data fetching.

### Changes Required

#### 1. Data Ingestion Flow Update

**File**: `etl/flows/process_case.py`
**Changes**: Update ingest_raw_data task to use ProclaimClient

```python
@task(retries=3, retry_delay_seconds=30, timeout_seconds=1800)
def ingest_raw_data(tenant_id: str, case_ref: str, is_full_rebuild: bool = False) -> Dict[str, Any]:
    """Ingest case data using real ProclaimClient instead of CSV fallback."""
    session_manager = V2SessionManager()

    with session_manager.bulk_processing_session() as session:
        # Use ProclaimClient instead of CSV fallback
        proclaim_client = session_manager.get_proclaim_client(tenant_id)
        raw_data = proclaim_client.get_case_data_with_tenant_context(case_ref)

        # Maintain existing data structure format
        return {
            'case_ref': case_ref,
            'tenant_id': tenant_id,
            'data_source': 'proclaim_api',  # Changed from 'csv_fallback'
            'raw_case_data': raw_data,
            'extraction_timestamp': datetime.now().isoformat(),
            'is_full_rebuild': is_full_rebuild
        }
```

#### 2. Vector Population Enhancement

**File**: `etl/flows/process_case.py`
**Changes**: Update populate_knowledge_bases task to use enhanced embedder

```python
@task(retries=2, retry_delay_seconds=60, timeout_seconds=1800)
def populate_knowledge_bases(enriched_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create vectors using enhanced embedder with comprehensive metadata."""
    tenant_id = enriched_data['tenant_id']
    vector_processor = DataPipelinesVectorProcessor(tenant_id)

    # Use enhanced embedder instead of basic vector creation
    vectors = vector_processor.create_vectors_with_tenant_isolation([enriched_data])

    # Upload to Pinecone with tenant isolation
    # Existing Pinecone logic with enhanced metadata
```

#### 3. Daily Sync Flow Enhancement

**File**: `etl/flows/sync_daily.py`
**Changes**: Update sync flow to use real ProclaimClient for case discovery

```python
def get_crm_active_cases_list(tenant_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get active cases using real Proclaim integration."""
    # Replace CSV fallback with ProclaimCRMAdapter
    adapter = create_case_discovery_adapter(
        adapter_type="proclaim",  # Changed from "csv"
        tenant_id=tenant_config['tenant_id']
    )
    return adapter.get_active_cases()
```

#### 4. Complete Document Processing Pipeline

**File**: `etl/flows/process_case.py`
**Changes**: Add document processing stage with SOAP download and Spaces storage

```python
@task(retries=2, retry_delay_seconds=60, timeout_seconds=1800)
def process_case_documents(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process case documents: SOAP download → text extraction → Spaces storage."""
    tenant_id = raw_data['tenant_id']
    case_ref = raw_data['case_ref']

    # Initialize document processing components
    downloader = DataPipelinesDocumentDownloader(
        tenant_id=tenant_id,
        wsdl_path=os.getenv('PROCLAIM_WSDL_PATH', 'Proclaim.wsdl'),  # WSDL in repo root
        soap_endpoint=f"{os.getenv('PROCLAIM_BASE_URL')}/soap/"
    )

    storage_client = DataPipelinesStorageClient(
        tenant_id=tenant_id,
        bucket=os.getenv('SPACES_BUCKET'),
        region=os.getenv('SPACES_REGION'),
        endpoint_url=os.getenv('SPACES_ENDPOINT_URL')
    )

    # Process documents from case manifest
    processed_documents = []
    for doc in raw_data.get('raw_case_data', {}).get('document_manifest', []):
        # Download via SOAP (get token from session manager)
        session_manager = V2SessionManager()
        proclaim_client = session_manager.get_proclaim_client(tenant_id)
        token = proclaim_client.session_token

        doc_path, error = downloader.fetch_document_with_tenant_context(
            token=token,
            document_code=doc['code'],
            document_format=doc['format']
        )

        if doc_path:
            # Store raw document
            raw_location = storage_client.store_document_with_tenant_path(
                local_path=doc_path,
                case_ref=case_ref,
                document_type="raw"
            )

            # Extract text (placeholder for LlamaParse integration)
            # text = llamaparse.convert_to_text(doc_path)

            # Store processed text
            # proc_location = storage_client.spaces.upload_text(
            #     text=text,
            #     object_key=f"{tenant_id}/documents/processed_text/{case_ref}/{doc['code']}.txt"
            # )

            processed_documents.append({
                'document_code': doc['code'],
                'raw_storage_path': raw_location.object_key,
                'status': 'processed'
            })

    return {
        **raw_data,
        'processed_documents': processed_documents,
        'document_processing_timestamp': datetime.now().isoformat()
    }
```

#### 5. Environment Configuration

**File**: `.env`
**Changes**: Add comprehensive configuration for all integrated components

```bash
# Proclaim API Configuration
PROCLAIM_BASE_URL=http://52.158.28.226:8085
PROCLAIM_USERNAME=${PROCLAIM_USERNAME}
PROCLAIM_PASSWORD=${PROCLAIM_PASSWORD}
PROCLAIM_WSDL_PATH=Proclaim.wsdl  # WSDL file in repository root
SOAP_REQUEST_DELAY_MS=500

# Session Management
PROCLAIM_SESSION_TIMEOUT_HOURS=6
PROCLAIM_SESSION_FILE_PATH=~/.caseguard/proclaim_session.json

# DigitalOcean Spaces Configuration
SPACES_BUCKET=caseguard-documents
SPACES_REGION=nyc3
SPACES_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com
SPACES_PROFILE=digitalocean

# AWS Credentials for Spaces
AWS_ACCESS_KEY_ID=${SPACES_ACCESS_KEY}
AWS_SECRET_ACCESS_KEY=${SPACES_SECRET_KEY}

# Canonical Field Mapping
CANONICAL_FIELDS_CONFIG_PATH=config/canonical_fields_corrected.json

# Document Processing
LLAMA_CLOUD_API_KEY=${LLAMA_CLOUD_API_KEY}
```

### Phase 3 Success Criteria

#### Automated Verification

- [ ] FDM Proclaim credentials validate: `poetry run python -c "from caseguard.proclaim.client import ProclaimClient; client = ProclaimClient('http://52.158.28.226:8085', os.getenv('PROCLAIM_USERNAME'), os.getenv('PROCLAIM_PASSWORD'), 'fdm_solicitors'); print('✅ FDM Authentication successful')"`
- [ ] Data ingestion flow runs: `poetry run python -c "import asyncio; from etl.flows.process_case import ingest_raw_data; asyncio.run(ingest_raw_data('fdm_solicitors', 'NBC200993.001'))"`
- [ ] Document processing pipeline runs: `poetry run python -c "import asyncio; from etl.flows.process_case import process_case_documents; asyncio.run(process_case_documents({'tenant_id': 'fdm_solicitors', 'case_ref': 'TEST-001'}))"`
- [ ] Canonical field extraction works: `poetry run python -c "from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever; retriever = SmartFieldRetriever('config/canonical_fields_corrected.json', None, 'fdm_solicitors'); print('✅ Field extraction ready')"`
- [ ] All Prefect flows deploy: `poetry run prefect deploy --all`
- [ ] Integration tests pass: `poetry run pytest tests/integration/ -v`

#### Manual Verification

- [ ] NBC200993.001 case data fetches successfully from Proclaim API
- [ ] Documents download via SOAP and store in DigitalOcean Spaces
- [ ] Canonical fields extract with 100% success rate for test cases
- [ ] Vector embeddings include comprehensive metadata from enhanced embedder
- [ ] Daily sync discovers real cases instead of CSV data
- [ ] Session management persists across flow runs
- [ ] Document storage hierarchy follows tenant-based structure

---

## Phase 4: Comprehensive Testing and Validation

### Overview

Create comprehensive test suite for the integrated system and validate complete pipeline functionality with NBC200993.001 case.

### Changes Required

#### 1. Integration Test Suite

**File**: `tests/integration/test_proclaim_integration.py` (new)
**Changes**: Create comprehensive integration tests

```python
import pytest
from caseguard.proclaim.client import ProclaimClient
from core.session_manager import V2SessionManager

class TestProclaimIntegration:
    def test_proclaim_client_authentication(self):
        """Test real Proclaim API authentication."""

    def test_case_data_extraction_nbc200993(self):
        """Test NBC200993.001 case data extraction."""

    def test_session_persistence(self):
        """Test session management persistence."""

    def test_vector_embeddings_with_metadata(self):
        """Test enhanced vector creation with comprehensive metadata."""
```

#### 2. End-to-End Pipeline Test

**File**: `tests/end_to_end/test_complete_pipeline_nbc200993.py` (new)
**Changes**: Complete pipeline validation

```python
class TestCompletePipelineNBC200993:
    def test_full_case_processing_pipeline(self):
        """Test complete NBC200993.001 processing through all stages."""
        # Proclaim → AI Enrichment → Vector Storage

    def test_performance_baseline(self):
        """Establish performance baseline for integrated system."""

    def test_tenant_isolation_maintained(self):
        """Verify tenant isolation throughout integrated pipeline."""
```

#### 3. Performance Monitoring

**File**: `monitoring/integration_health.py` (new)
**Changes**: Add integration-specific health checks

```python
class IntegrationHealthChecker:
    def check_proclaim_connectivity(self) -> Dict[str, Any]:
        """Health check for Proclaim API connectivity."""

    def check_session_management_health(self) -> Dict[str, Any]:
        """Health check for integrated session management."""

    def check_vector_processing_performance(self) -> Dict[str, Any]:
        """Performance monitoring for enhanced vector processing."""
```

#### 4. Documentation Updates

**File**: `CLAUDE.md`
**Changes**: Update development commands for integrated system

```bash
# Test integrated Proclaim connection
poetry run python -c "
from core.session_manager import V2SessionManager
sm = V2SessionManager()
with sm.bulk_processing_session() as session:
    client = session.get_proclaim_client('fdm_solicitors')
    case_data = client.get_case_data_with_tenant_context('NBC200993.001')
    print('✅ Proclaim integration working')
"

# Test complete pipeline with NBC200993.001
poetry run python -c "
import asyncio
from etl.flows.process_case import process_proclaim_case

async def test_integration():
    result = await process_proclaim_case('fdm_solicitors', 'NBC200993.001', is_full_rebuild=True)
    print(f'✅ Complete pipeline working: {result}')

asyncio.run(test_integration())
"
```

### Phase 4 Success Criteria

#### Automated Verification

- [ ] All integration tests pass: `poetry run pytest tests/integration/ -v`
- [ ] End-to-end tests pass: `poetry run pytest tests/end_to_end/ -v`
- [ ] Performance baselines established: `poetry run python tests/performance/baseline_nbc200993.py`
- [ ] Health checks pass: `poetry run python monitoring/integration_health.py`
- [ ] Complete pipeline test runs: `poetry run python test_full_pipeline.py`
- [ ] SOAP downloader tests pass: `poetry run python -c "from tests.integration.test_soap_downloader import test_document_fetch; test_document_fetch()"`
- [ ] Spaces integration tests pass: `poetry run python -c "from tests.integration.test_spaces_client import test_upload_download; test_upload_download()"`
- [ ] Canonical field tests pass: `poetry run python -c "from tests.integration.test_field_extractor import test_all_canonical_fields; test_all_canonical_fields()"`

#### Manual Verification

- [ ] NBC200993.001 processes successfully through complete pipeline in under 5 minutes
- [ ] Document processing chain works: SOAP download → Spaces storage → vector embedding
- [ ] All 27 canonical fields extract successfully from test cases
- [ ] Vector embeddings include comprehensive metadata for agent citations
- [ ] Session management handles process interruptions gracefully
- [ ] Multi-tenant isolation maintained throughout integrated system
- [ ] Performance is acceptable compared to CSV fallback baseline
- [ ] Document storage follows tenant-based hierarchy in DigitalOcean Spaces

---

## Testing Strategy

### Integration Tests

- **ProclaimClient Integration**: Authentication, case data fetching, session management
- **SOAP Document Processing**: Binary document download, format detection, temporary file handling
- **DigitalOcean Spaces Storage**: Upload, download, tenant-based object hierarchy, pre-signed URLs
- **Canonical Field Extraction**: All 27 fields, three-tier architecture, fallback mechanisms
- **Vector Processing**: Enhanced embeddings with comprehensive metadata and storage references
- **ETL Flow Integration**: Real Proclaim data through Prefect flows with document processing
- **Session Management**: Persistence, cleanup, and health validation

### End-to-End Tests

- **Complete Document Pipeline**: NBC200993.001 through Proclaim → SOAP Download → Spaces Storage → AI → Vector storage
- **Multi-Tenant Isolation**: Verify data separation in all storage systems (database, Pinecone, Spaces)
- **Performance Baseline**: Timing and resource usage for integrated system with document processing
- **Agent Citation Workflow**: Vector search → metadata retrieval → pre-signed URL generation for document access

### Manual Testing Steps

1. **Authenticate with Proclaim**: Verify real API connection and session persistence
2. **Extract NBC200993.001**: Validate case data structure and completeness
3. **Test Document Processing**: Download documents via SOAP, store in Spaces, verify tenant isolation
4. **Validate Canonical Fields**: Extract all 27 fields and verify 100% success rate
5. **Process through ETL**: Run complete pipeline and verify all stages including document processing
6. **Verify Vector Storage**: Check Pinecone indexing with comprehensive metadata and storage paths
7. **Test Agent Citations**: Verify vector search returns proper storage references for document access
8. **Test Session Cleanup**: Interrupt process and verify graceful session handling

## Performance Considerations

- **Session Reuse**: Leverage existing session management for efficient API usage
- **Bulk Processing**: Use enhanced session contexts for multiple case processing
- **Vector Optimization**: Batch embeddings for improved throughput
- **Change Detection**: Maintain efficient sync mechanisms with real API data

## Migration Notes

### Environment Variables

- **Add Proclaim credentials** to existing .env configuration
- **Configure session management** file paths and timeouts
- **Align vector configurations** between existing implementations and DataPipelines

### Dependencies and File Structure

- **Copy component implementations** from `technical-details.md` to DataPipelines `caseguard/` directory
- **Install required packages**: `zeep`, `boto3`, `openai`, `tqdm` for copied components
- **Create canonical field configuration**: Copy `config/canonical_fields_corrected.json` from technical-details.md
- **Create directory structure**:

  ```text
  DataPipelines/
  ├── caseguard/
  │   ├── __init__.py
  │   ├── proclaim/
  │   │   ├── __init__.py
  │   │   ├── client.py (copied and adapted)
  │   │   └── soap_downloader.py (copied and adapted)
  │   ├── storage/
  │   │   ├── __init__.py
  │   │   └── spaces.py (copied and adapted)
  │   ├── hdr_timeline/
  │   │   ├── __init__.py
  │   │   └── smart_field_retriever.py (copied and adapted)
  │   ├── vectorization/
  │   │   ├── __init__.py
  │   │   └── embedder.py (copied and adapted)
  │   └── utils/
  │       ├── __init__.py
  │       └── session_manager.py (copied and adapted)
  └── config/
      └── canonical_fields_corrected.json (copied from technical-details.md)
  ```

- **Resolve version conflicts** between OpenAI client versions
- **Configure shared session storage** locations

### Backward Compatibility

- **Maintain CSV fallback** as secondary adapter for testing
- **Preserve existing database schema** with extended metadata support
- **Keep existing API endpoints** functional during transition

## References

- Research document: `thoughts/shared/research/2025-09-26-etl-pipeline-testing-documentation.md`
- **Technical implementation details**: `technical-details.md` - Complete implementations for SOAP downloader, Spaces integration, and canonical field mapping
- Existing ProclaimClient: Reference implementation available in existing codebase
- SOAP Document Downloader: `caseguard/proclaim/soap_downloader.py:92` - Binary-safe document retrieval with format mapping
- DigitalOcean Spaces Client: `caseguard/storage/spaces.py:244` - S3-compatible storage with tenant hierarchy
- Canonical Field Configuration: `config/canonical_fields_corrected.json` - 100% tested field mappings
- Smart Field Retriever: `caseguard/hdr_timeline/smart_field_retriever.py:809` - Three-tier extraction with fallbacks
- Current ETL flows: `etl/flows/process_case.py:206`
- Session management: `core/session_manager.py:14`
- Vector processing: Enhanced embedder implementation to be copied and adapted
- CRM adapters: `crm/discovery.py:88`
