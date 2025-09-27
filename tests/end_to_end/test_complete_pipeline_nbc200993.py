"""End-to-end test for complete NBC200993.001 pipeline."""

import pytest
from unittest.mock import Mock, patch
import os
from datetime import datetime


class TestCompletePipelineNBC200993:
    """Test complete NBC200993.001 processing through all stages."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {
        'PROCLAIM_BASE_URL': 'http://52.158.28.226:8085',
        'PROCLAIM_USERNAME': 'test_user',
        'PROCLAIM_PASSWORD': 'test_pass',
        'PROCLAIM_WSDL_PATH': 'Proclaim.wsdl',
        'SPACES_BUCKET': 'caseguard-documents',
        'SPACES_REGION': 'nyc3',
        'SPACES_ENDPOINT_URL': 'https://nyc3.digitaloceanspaces.com',
        'OPENAI_API_KEY': 'test-key'
    })
    async def test_full_case_processing_pipeline(self):
        """Test complete NBC200993.001 processing through all stages."""
        from etl.flows.process_case import process_proclaim_case
        from unittest.mock import AsyncMock

        # Mock the Prefect flow runner
        with patch('etl.flows.process_case.get_run_logger') as mock_logger:
            mock_logger.return_value = Mock()

            # Mock ProclaimClient authentication
            with patch('caseguard.proclaim.client.ProclaimClient._authenticate') as mock_auth:
                mock_auth.return_value = None

                # Mock case data
                with patch('caseguard.proclaim.client.ProclaimClient.get_case_data_with_tenant_context') as mock_get_case:
                    mock_get_case.return_value = {
                        'case_ref': 'NBC200993.001',
                        'tenant_id': 'fdm_solicitors',
                        'core_details': {
                            'case_status': 'Complete',
                            'handler_name': 'Ellie Braiden',
                            'client_name': 'FDM Solicitors'
                        },
                        'history': [
                            {'description': 'Case opened', 'date': '2024-09-18'},
                            {'description': 'Letter of claim sent', 'date': '2024-09-20'}
                        ],
                        'parties': [
                            {'type': 'claimant', 'name': 'FDM Solicitors'},
                            {'type': 'defendant', 'name': 'Landlord ABC'}
                        ],
                        'document_manifest': [
                            {'code': 'DOC001', 'format': 'ACROBAT-PDF', 'filename': 'claim_letter.pdf'}
                        ]
                    }

                    # Mock SOAP downloader
                    with patch('caseguard.proclaim.soap_downloader.ProclaimSoapDownloader.fetch_document_with_tenant_context') as mock_soap:
                        from pathlib import Path
                        import tempfile

                        # Create mock document file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                            f.write(b'Mock PDF content')
                            mock_file = Path(f.name)

                        mock_soap.return_value = (mock_file, None)

                        # Mock Spaces client
                        with patch('caseguard.storage.spaces.SpacesClient.store_document_with_tenant_path') as mock_spaces, \
                             patch('boto3.Session') as mock_session:

                            from caseguard.storage.spaces import SpacesLocation
                            mock_session.return_value.client.return_value = Mock()
                            mock_spaces.return_value = SpacesLocation(
                                bucket='caseguard-documents',
                                object_key='fdm_solicitors/documents/raw/NBC200993.001/claim_letter.pdf',
                                region='nyc3',
                                tenant_id='fdm_solicitors'
                            )

                            # Mock OpenAI embeddings
                            with patch('openai.OpenAI') as mock_openai:
                                mock_client = Mock()
                                mock_response = Mock()
                                mock_response.data = [Mock(embedding=[0.1] * 3072)]
                                mock_client.embeddings.create.return_value = mock_response
                                mock_openai.return_value = mock_client

                                # Run the complete pipeline
                                result = await process_proclaim_case(
                                    tenant_id='fdm_solicitors',
                                    case_ref='NBC200993.001',
                                    is_full_rebuild=True
                                )

                                # Verify pipeline completion
                                assert result['status'] == 'completed'
                                assert result['case_ref'] == 'NBC200993.001'
                                assert result['tenant_id'] == 'fdm_solicitors'
                                assert 'data_ingestion' in result['steps_completed']
                                assert 'ai_enrichment' in result['steps_completed']
                                assert 'document_processing' in result['steps_completed']
                                assert 'vectorization' in result['steps_completed']

                                # Verify processing results
                                assert result.get('documents_processed', 0) > 0
                                assert result.get('vectors_created', 0) > 0
                                assert result.get('processing_time_seconds', 0) > 0

                        # Cleanup
                        mock_file.unlink()

    def test_performance_baseline(self):
        """Establish performance baseline for integrated system."""
        from core.session_manager import V2SessionManager
        from caseguard.proclaim.client import ProclaimClient
        from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader
        from caseguard.storage.spaces import SpacesClient
        from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever

        start_time = datetime.now()

        # Test component initialization times
        session_manager = V2SessionManager()
        assert session_manager is not None

        # Mock authentication for timing test
        with patch('caseguard.proclaim.client.ProclaimClient._authenticate'):
            client = ProclaimClient(
                base_url='http://52.158.28.226:8085',
                username='test',
                password='test',
                tenant_id='fdm_solicitors'
            )
            assert client.tenant_id == 'fdm_solicitors'

        # Test SOAP downloader initialization
        downloader = ProclaimSoapDownloader(
            wsdl_path='Proclaim.wsdl',
            soap_endpoint='http://52.158.28.226:8085/soap',
            tenant_id='fdm_solicitors'
        )
        assert downloader.tenant_id == 'fdm_solicitors'

        # Test Spaces client initialization
        with patch('boto3.Session'):
            spaces_client = SpacesClient(
                tenant_id='fdm_solicitors',
                bucket='caseguard-documents',
                region='nyc3',
                endpoint_url='https://nyc3.digitaloceanspaces.com'
            )
            assert spaces_client.tenant_id == 'fdm_solicitors'

        # Test field extractor initialization
        field_extractor = SmartFieldRetriever(
            canonical_fields_path='config/canonical_fields_corrected.json',
            proclaim_client=Mock(),
            tenant_id='fdm_solicitors'
        )
        assert field_extractor.tenant_id == 'fdm_solicitors'

        end_time = datetime.now()
        initialization_time = (end_time - start_time).total_seconds()

        # Assert reasonable initialization time (under 5 seconds)
        assert initialization_time < 5.0, f"Component initialization took {initialization_time:.2f}s"

    def test_tenant_isolation_maintained(self):
        """Verify tenant isolation throughout integrated pipeline."""
        from caseguard.proclaim.client import ProclaimClient
        from caseguard.storage.spaces import SpacesLocation
        from caseguard.vectorization.embedder import CaseEmbedder
        from openai import OpenAI

        # Test client tenant isolation
        with patch('caseguard.proclaim.client.ProclaimClient._authenticate'):
            client1 = ProclaimClient(
                base_url='http://52.158.28.226:8085',
                username='test1',
                password='test1',
                tenant_id='tenant_1'
            )

            client2 = ProclaimClient(
                base_url='http://52.158.28.226:8085',
                username='test2',
                password='test2',
                tenant_id='tenant_2'
            )

            assert client1.tenant_id != client2.tenant_id

        # Test Spaces isolation
        location1 = SpacesLocation(
            bucket='caseguard-documents',
            object_key='tenant_1/documents/raw/case1/doc.pdf',
            region='nyc3',
            tenant_id='tenant_1'
        )

        location2 = SpacesLocation(
            bucket='caseguard-documents',
            object_key='tenant_2/documents/raw/case1/doc.pdf',
            region='nyc3',
            tenant_id='tenant_2'
        )

        assert location1.tenant_id != location2.tenant_id
        assert 'tenant_1' in location1.object_key
        assert 'tenant_2' in location2.object_key

        # Test vector embedder isolation
        with patch('openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.data = [Mock(embedding=[0.1] * 3072)]
            mock_client.embeddings.create.return_value = mock_response
            mock_openai.return_value = mock_client

            embedder1 = CaseEmbedder(
                openai_client=mock_client,
                tenant_id='tenant_1'
            )

            embedder2 = CaseEmbedder(
                openai_client=mock_client,
                tenant_id='tenant_2'
            )

            test_case = {
                'case_ref': 'TEST001',
                'tenant_id': 'tenant_1',
                'enrichment': {
                    'ai_insights': {
                        'case_summary': 'Test case',
                        'key_issues': ['Issue 1']
                    }
                }
            }

            vectors1 = embedder1.create_vectors_with_tenant_isolation([test_case])
            vectors2 = embedder2.create_vectors_with_tenant_isolation([{**test_case, 'tenant_id': 'tenant_2'}])

            # Verify tenant isolation in vector metadata
            assert vectors1[0]['metadata']['tenant_id'] == 'tenant_1'
            assert vectors2[0]['metadata']['tenant_id'] == 'tenant_2'
            assert 'tenant_1' in vectors1[0]['id']
            assert 'tenant_2' in vectors2[0]['id']

    def test_error_handling_resilience(self):
        """Test system resilience to various error conditions."""
        from core.session_manager import V2SessionManager
        from caseguard.proclaim.client import ProclaimClient

        # Test session manager with invalid credentials
        session_manager = V2SessionManager()

        with patch.dict(os.environ, {
            'PROCLAIM_BASE_URL': 'http://invalid-url:9999',
            'PROCLAIM_USERNAME': 'invalid',
            'PROCLAIM_PASSWORD': 'invalid'
        }):
            # This should handle authentication errors gracefully
            with pytest.raises(Exception):  # Expected to fail with invalid credentials
                session_manager.get_proclaim_client('test_tenant')

        # Test SOAP downloader with invalid WSDL
        from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader

        with pytest.raises(Exception):  # Expected to fail with invalid WSDL
            ProclaimSoapDownloader(
                wsdl_path='nonexistent.wsdl',
                soap_endpoint='http://invalid-endpoint',
                tenant_id='test_tenant'
            )