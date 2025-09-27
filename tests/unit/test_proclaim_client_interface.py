"""TDD interface tests for ProclaimClient - written before implementation."""

import pytest
from unittest.mock import Mock, patch


class TestProclaimClientInterface:
    """Test ProclaimClient interface before implementation."""

    def test_proclaim_client_initialization_fdm(self, fdm_proclaim_credentials):
        """Test ProclaimClient can be initialized with FDM tenant context."""
        # This test will fail initially - that's the point of TDD
        from caseguard.proclaim.client import ProclaimClient

        # Mock the authentication to avoid real API calls
        with patch.object(ProclaimClient, '_authenticate') as mock_auth:
            mock_auth.return_value = None

            client = ProclaimClient(
                tenant_id='fdm_solicitors',
                **fdm_proclaim_credentials
            )

            assert client.tenant_id == 'fdm_solicitors'
            assert client.base_url == 'http://52.158.28.226:8085'

    def test_get_case_data_with_fdm_context(self, fdm_proclaim_credentials, fdm_primary_test_case):
        """Test case data includes FDM tenant metadata for NBC200993.001."""
        from caseguard.proclaim.client import ProclaimClient

        with patch.object(ProclaimClient, '_authenticate') as mock_auth, \
             patch.object(ProclaimClient, 'get_case_data') as mock_get:

            mock_auth.return_value = None
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

        with patch.object(ProclaimClient, '_authenticate') as mock_auth:
            mock_auth.return_value = None

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