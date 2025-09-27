"""TDD interface tests for SOAP downloader - written before implementation."""

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