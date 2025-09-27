#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test script for Proclaim integration validation.
Tests all components independently without Prefect dependencies.
"""

import os
import sys
import traceback
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any


def test_proclaim_client_integration():
    """Test ProclaimClient integration."""
    print("🔄 Testing ProclaimClient integration...")

    try:
        from caseguard.proclaim.client import ProclaimClient

        # Mock authentication to avoid real API calls
        with patch.object(ProclaimClient, '_authenticate') as mock_auth:
            mock_auth.return_value = None

            client = ProclaimClient(
                base_url='http://52.158.28.226:8085',
                username='test_user',
                password='test_pass',
                tenant_id='fdm_solicitors'
            )

            assert client.tenant_id == 'fdm_solicitors'
            assert client.base_url == 'http://52.158.28.226:8085'

            # Test tenant context method
            with patch.object(client, 'get_case_data') as mock_get:
                mock_get.return_value = {
                    'case_ref': 'NBC200993.001',
                    'status': 'Complete'
                }

                result = client.get_case_data_with_tenant_context('NBC200993.001')
                assert result['tenant_id'] == 'fdm_solicitors'
                assert result['case_ref'] == 'NBC200993.001'

        print("✅ ProclaimClient integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ ProclaimClient integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_soap_downloader_integration():
    """Test SOAP downloader integration."""
    print("🔄 Testing SOAP downloader integration...")

    try:
        from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader, FORMAT_TO_MIME

        downloader = ProclaimSoapDownloader(
            wsdl_path='Proclaim.wsdl',
            soap_endpoint='http://52.158.28.226:8085/soap',
            tenant_id='fdm_solicitors'
        )

        assert downloader.tenant_id == 'fdm_solicitors'
        assert 'ACROBAT-PDF' in FORMAT_TO_MIME
        assert FORMAT_TO_MIME['ACROBAT-PDF'] == 'application/pdf'

        # Test format mapping
        formats = downloader.get_supported_formats()
        assert len(formats) > 20  # Should have many formats

        print("✅ SOAP downloader integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ SOAP downloader integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_spaces_client_integration():
    """Test Spaces client integration."""
    print("🔄 Testing Spaces client integration...")

    try:
        from caseguard.storage.spaces import SpacesClient, SpacesLocation

        with patch('boto3.Session') as mock_session:
            mock_session.return_value.client.return_value = Mock()

            client = SpacesClient(
                tenant_id='fdm_solicitors',
                bucket='caseguard-documents',
                region='nyc3',
                endpoint_url='https://nyc3.digitaloceanspaces.com'
            )

            assert client.tenant_id == 'fdm_solicitors'
            assert client.bucket == 'caseguard-documents'

            # Test location object
            location = SpacesLocation(
                bucket='caseguard-documents',
                object_key='fdm_solicitors/documents/raw/NBC200993.001/test.pdf',
                region='nyc3',
                tenant_id='fdm_solicitors'
            )

            assert location.tenant_id == 'fdm_solicitors'
            assert 'fdm_solicitors' in location.object_key

        print("✅ Spaces client integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ Spaces client integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_field_extractor_integration():
    """Test field extractor integration."""
    print("🔄 Testing field extractor integration...")

    try:
        from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever

        # Mock Proclaim client
        mock_client = Mock()
        mock_client.get_case_data.return_value = {
            'case_ref': 'NBC200993.001',
            'core_details': {
                'case_status': 'Complete',
                'handler_name': 'Ellie Braiden'
            },
            'parties': [
                {'type': 'claimant', 'name': 'FDM Solicitors'}
            ]
        }

        extractor = SmartFieldRetriever(
            canonical_fields_path='config/canonical_fields_corrected.json',
            proclaim_client=mock_client,
            tenant_id='fdm_solicitors'
        )

        assert extractor.tenant_id == 'fdm_solicitors'
        assert extractor.global_fields is not None
        assert extractor.hdr_fields is not None

        # Test field extraction
        result = extractor.extract_canonical_fields_with_tenant_context('NBC200993.001')
        assert result['tenant_id'] == 'fdm_solicitors'
        assert result['case_ref'] == 'NBC200993.001'
        assert 'extraction_timestamp' in result

        print("✅ Field extractor integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ Field extractor integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_embedder_integration():
    """Test case embedder integration."""
    print("🔄 Testing case embedder integration...")

    try:
        from caseguard.vectorization.embedder import CaseEmbedder

        # Mock OpenAI client
        mock_openai = Mock()
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1] * 3072)]
        mock_openai.embeddings.create.return_value = mock_response

        embedder = CaseEmbedder(
            openai_client=mock_openai,
            tenant_id='fdm_solicitors',
            model='text-embedding-3-large'
        )

        assert embedder.tenant_id == 'fdm_solicitors'
        assert embedder.model == 'text-embedding-3-large'

        # Test vector creation
        test_case = {
            'case_ref': 'NBC200993.001',
            'tenant_id': 'fdm_solicitors',
            'enrichment': {
                'ai_insights': {
                    'case_summary': 'Test case for FDM',
                    'key_issues': ['Issue 1', 'Issue 2']
                }
            }
        }

        vectors = embedder.create_vectors_with_tenant_isolation([test_case])
        assert len(vectors) == 1
        assert vectors[0]['metadata']['tenant_id'] == 'fdm_solicitors'
        assert 'fdm_solicitors' in vectors[0]['id']

        # Test detail vectors
        detail_vectors = embedder.create_detail_vectors(test_case)
        assert len(detail_vectors) > 0

        print("✅ Case embedder integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ Case embedder integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_session_manager_integration():
    """Test session manager integration."""
    print("🔄 Testing session manager integration...")

    try:
        from core.session_manager import V2SessionManager

        session_manager = V2SessionManager()
        assert session_manager is not None
        assert hasattr(session_manager, 'get_proclaim_client')
        assert hasattr(session_manager, 'bulk_processing_session')

        # Test with mocked environment
        with patch.dict(os.environ, {
            'PROCLAIM_BASE_URL': 'http://52.158.28.226:8085',
            'PROCLAIM_USERNAME': 'test_user',
            'PROCLAIM_PASSWORD': 'test_pass'
        }):
            with patch('caseguard.proclaim.client.ProclaimClient._authenticate'):
                client = session_manager.get_proclaim_client('fdm_solicitors')
                assert client.tenant_id == 'fdm_solicitors'

        print("✅ Session manager integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ Session manager integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_crm_adapter_integration():
    """Test CRM adapter integration."""
    print("🔄 Testing CRM adapter integration...")

    try:
        from crm.discovery import ProclaimCRMAdapter, CSVFallbackAdapter, create_case_discovery_adapter

        # Test ProclaimCRMAdapter initialization
        adapter = ProclaimCRMAdapter(
            tenant_id='fdm_solicitors',
            api_base_url='http://52.158.28.226:8085'
        )
        assert adapter.tenant_id == 'fdm_solicitors'

        # Test CSV fallback adapter
        csv_adapter = CSVFallbackAdapter(
            tenant_id='fdm_solicitors',
            csv_path='configs/tenants/FDM example Funded Cases.csv'
        )
        assert csv_adapter.tenant_id == 'fdm_solicitors'

        # Test factory function
        created_adapter = create_case_discovery_adapter(
            tenant_id='fdm_solicitors',
            adapter_type='csv'
        )
        assert created_adapter.tenant_id == 'fdm_solicitors'

        print("✅ CRM adapter integration: PASSED")
        return True

    except Exception as e:
        print(f"❌ CRM adapter integration: FAILED - {e}")
        traceback.print_exc()
        return False


def test_configuration_files():
    """Test configuration files exist and are valid."""
    print("🔄 Testing configuration files...")

    try:
        # Test canonical fields config
        config_path = Path('config/canonical_fields_corrected.json')
        assert config_path.exists(), f"Canonical fields config not found: {config_path}"

        import json
        with open(config_path) as f:
            config = json.load(f)

        assert 'global_fields' in config
        assert 'hdr_fields' in config
        assert len(config['global_fields']['fields']) > 0
        assert len(config['hdr_fields']['fields']) > 0

        # Test WSDL file
        wsdl_path = Path('Proclaim.wsdl')
        assert wsdl_path.exists(), f"WSDL file not found: {wsdl_path}"

        # Test environment example
        env_path = Path('deployment/.env.example')
        assert env_path.exists(), f"Environment example not found: {env_path}"

        print("✅ Configuration files: PASSED")
        return True

    except Exception as e:
        print(f"❌ Configuration files: FAILED - {e}")
        traceback.print_exc()
        return False


def main():
    """Run comprehensive integration test suite."""
    print("🚀 Starting Proclaim Integration Test Suite")
    print("=" * 60)

    tests = [
        test_configuration_files,
        test_proclaim_client_integration,
        test_soap_downloader_integration,
        test_spaces_client_integration,
        test_field_extractor_integration,
        test_embedder_integration,
        test_session_manager_integration,
        test_crm_adapter_integration,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: FAILED - {e}")
            failed += 1
        print()

    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All Proclaim integration tests PASSED!")
        print("\n✅ Ready for deployment with:")
        print("   - Real Proclaim API credentials")
        print("   - DigitalOcean Spaces credentials")
        print("   - OpenAI API key")
        print("   - NBC200993.001 test case")
        return 0
    else:
        print("❌ Some tests failed. Please review and fix issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())