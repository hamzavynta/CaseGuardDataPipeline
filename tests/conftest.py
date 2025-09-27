"""TDD Test infrastructure for Proclaim integration."""

import pytest
import os
import json
import tempfile
from unittest.mock import Mock, MagicMock
from pathlib import Path
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