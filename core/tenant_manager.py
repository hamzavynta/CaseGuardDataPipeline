"""Multi-tenant configuration management and isolation."""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TenantConfig(BaseModel):
    """Tenant configuration model."""

    tenant_id: str = Field(..., description="Unique tenant identifier")
    display_name: str = Field(..., description="Human-readable tenant name")
    is_active: bool = Field(default=True, description="Whether tenant is active")
    created_at: str = Field(..., description="Tenant creation timestamp")

    # CRM configuration
    crm_config: Dict[str, Any] = Field(default_factory=dict)

    # Processing configuration
    processing_config: Dict[str, Any] = Field(default_factory=dict)

    # Vector configuration
    vector_config: Dict[str, Any] = Field(default_factory=dict)

    # Document configuration
    document_config: Dict[str, Any] = Field(default_factory=dict)

    # Database configuration
    database_config: Dict[str, Any] = Field(default_factory=dict)

    # AI configuration
    ai_config: Dict[str, Any] = Field(default_factory=dict)

    # Sync configuration
    sync_config: Dict[str, Any] = Field(default_factory=dict)

    # Monitoring configuration
    monitoring_config: Dict[str, Any] = Field(default_factory=dict)

    # Compliance configuration
    compliance_config: Dict[str, Any] = Field(default_factory=dict)


class TenantManager:
    """Multi-tenant configuration management with isolation and security."""

    def __init__(self, config_directory: str = "v2/configs/tenants"):
        """Initialize tenant manager.

        Args:
            config_directory: Directory containing tenant configuration files
        """
        self.config_directory = Path(config_directory)
        self.tenant_cache = {}
        self.cache_ttl_seconds = 300  # 5 minutes

        logger.info(f"TenantManager initialized with config directory: {self.config_directory}")

    async def get_tenant_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant configuration by ID.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Tenant configuration dictionary or None if not found
        """
        # Check cache first
        cache_key = f"tenant_config_{tenant_id}"
        cached = self.tenant_cache.get(cache_key)

        if cached and (datetime.utcnow() - cached['timestamp']).seconds < self.cache_ttl_seconds:
            return cached['config']

        try:
            config_file = self.config_directory / f"{tenant_id}.json"

            if not config_file.exists():
                logger.warning(f"Tenant configuration not found: {config_file}")
                return None

            with open(config_file, 'r') as f:
                config = json.load(f)

            # Validate configuration
            tenant_config = TenantConfig(**config)

            # Cache the configuration
            self.tenant_cache[cache_key] = {
                'config': config,
                'timestamp': datetime.utcnow()
            }

            logger.debug(f"Loaded configuration for tenant {tenant_id}")
            return config

        except Exception as e:
            logger.error(f"Failed to load tenant configuration for {tenant_id}: {e}")
            return None

    async def get_active_tenants(self) -> List[Dict[str, Any]]:
        """Get all active tenant configurations.

        Returns:
            List of active tenant configurations
        """
        active_tenants = []

        try:
            if not self.config_directory.exists():
                logger.warning(f"Tenant config directory does not exist: {self.config_directory}")
                return []

            # Load all tenant configuration files
            for config_file in self.config_directory.glob("*.json"):
                tenant_id = config_file.stem
                config = await self.get_tenant_config(tenant_id)

                if config and config.get('is_active', False):
                    active_tenants.append(config)

            logger.info(f"Found {len(active_tenants)} active tenants")
            return active_tenants

        except Exception as e:
            logger.error(f"Failed to get active tenants: {e}")
            return []

    async def get_tenant_processing_limits(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant-specific processing limits and quotas.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Processing limits configuration
        """
        config = await self.get_tenant_config(tenant_id)
        if not config:
            return self._get_default_processing_limits()

        processing_config = config.get('processing_config', {})
        return {
            'concurrent_limit': processing_config.get('concurrent_limit', 25),
            'retry_attempts': processing_config.get('retry_attempts', 3),
            'session_timeout_hours': processing_config.get('session_timeout_hours', 6),
            'max_jobs_per_hour': processing_config.get('max_jobs_per_hour', 120),
            'batch_size': processing_config.get('batch_size', 100),
            'rate_limiting': processing_config.get('rate_limiting', {
                'enabled': True,
                'requests_per_minute': 60,
                'burst_limit': 10
            })
        }

    async def get_tenant_vector_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant vector storage configuration.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Vector configuration with isolation settings
        """
        config = await self.get_tenant_config(tenant_id)
        if not config:
            return self._get_default_vector_config(tenant_id)

        vector_config = config.get('vector_config', {})

        # Ensure tenant isolation in metadata filters
        metadata_filters = vector_config.get('metadata_filters', {})
        metadata_filters['tenant_id'] = tenant_id

        return {
            'shared_indexes': vector_config.get('shared_indexes', True),
            'case_summaries_index': vector_config.get('case_summaries_index', 'caseguard-case-summaries'),
            'case_details_index': vector_config.get('case_details_index', 'caseguard-case-details'),
            'embedding_model': vector_config.get('embedding_model', 'text-embedding-3-large'),
            'chunk_size': vector_config.get('chunk_size', 800),
            'dimension': vector_config.get('dimension', 3072),
            'metadata_filters': metadata_filters
        }

    async def get_tenant_crm_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant CRM integration configuration.

        Args:
            tenant_id: Tenant identifier

        Returns:
            CRM configuration with credentials handling
        """
        config = await self.get_tenant_config(tenant_id)
        if not config:
            return {}

        crm_config = config.get('crm_config', {})

        # Resolve environment variables in credentials
        credentials = crm_config.get('credentials', {})
        resolved_credentials = self._resolve_credential_variables(credentials)

        return {
            'type': crm_config.get('type', 'unknown'),
            'api_base_url': crm_config.get('api_base_url'),
            'credentials': resolved_credentials,
            'case_discovery': crm_config.get('case_discovery', {}),
            'api_limitations': crm_config.get('api_limitations', {})
        }

    async def validate_tenant_access(self, tenant_id: str, resource_type: str = None) -> bool:
        """Validate tenant access permissions.

        Args:
            tenant_id: Tenant identifier
            resource_type: Optional resource type for fine-grained access control

        Returns:
            True if access is allowed, False otherwise
        """
        config = await self.get_tenant_config(tenant_id)

        if not config:
            logger.warning(f"Access denied: tenant {tenant_id} not found")
            return False

        if not config.get('is_active', False):
            logger.warning(f"Access denied: tenant {tenant_id} is inactive")
            return False

        # Additional resource-specific validation can be added here
        if resource_type:
            access_controls = config.get('compliance_config', {}).get('access_controls', {})
            # Implement resource-specific access control logic

        return True

    async def get_tenant_isolation_context(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant isolation context for database and processing operations.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Isolation context with schema, filters, and security settings
        """
        config = await self.get_tenant_config(tenant_id)
        if not config:
            return {'tenant_id': tenant_id, 'schema': 'public', 'isolation_level': 'basic'}

        database_config = config.get('database_config', {})

        return {
            'tenant_id': tenant_id,
            'schema': database_config.get('schema', tenant_id),
            'isolation_level': database_config.get('isolation_level', 'strict'),
            'metadata_filters': {
                'tenant_id': tenant_id,
                'privacy_level': config.get('vector_config', {}).get('metadata_filters', {}).get('privacy_level', 'confidential')
            },
            'retention_policy': database_config.get('retention_policy', {}),
            'encryption_required': config.get('compliance_config', {}).get('data_encryption') == 'AES-256'
        }

    async def create_tenant_config(self, tenant_config: Dict[str, Any]) -> bool:
        """Create new tenant configuration.

        Args:
            tenant_config: Tenant configuration dictionary

        Returns:
            True if created successfully, False otherwise
        """
        try:
            # Validate configuration
            tenant = TenantConfig(**tenant_config)

            config_file = self.config_directory / f"{tenant.tenant_id}.json"

            if config_file.exists():
                logger.warning(f"Tenant configuration already exists: {tenant.tenant_id}")
                return False

            # Ensure directory exists
            self.config_directory.mkdir(parents=True, exist_ok=True)

            # Write configuration
            with open(config_file, 'w') as f:
                json.dump(tenant_config, f, indent=2)

            # Clear cache
            cache_key = f"tenant_config_{tenant.tenant_id}"
            if cache_key in self.tenant_cache:
                del self.tenant_cache[cache_key]

            logger.info(f"Created tenant configuration: {tenant.tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create tenant configuration: {e}")
            return False

    async def update_tenant_config(self, tenant_id: str, updates: Dict[str, Any]) -> bool:
        """Update existing tenant configuration.

        Args:
            tenant_id: Tenant identifier
            updates: Configuration updates to apply

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            config = await self.get_tenant_config(tenant_id)
            if not config:
                logger.error(f"Cannot update non-existent tenant: {tenant_id}")
                return False

            # Apply updates
            config.update(updates)

            # Validate updated configuration
            TenantConfig(**config)

            # Write updated configuration
            config_file = self.config_directory / f"{tenant_id}.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)

            # Clear cache
            cache_key = f"tenant_config_{tenant_id}"
            if cache_key in self.tenant_cache:
                del self.tenant_cache[cache_key]

            logger.info(f"Updated tenant configuration: {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update tenant configuration for {tenant_id}: {e}")
            return False

    async def get_tenant_stats(self) -> Dict[str, Any]:
        """Get tenant management statistics.

        Returns:
            Statistics about tenant configurations and status
        """
        try:
            all_tenants = []
            active_tenants = []

            if self.config_directory.exists():
                for config_file in self.config_directory.glob("*.json"):
                    tenant_id = config_file.stem
                    config = await self.get_tenant_config(tenant_id)

                    if config:
                        all_tenants.append(config)
                        if config.get('is_active', False):
                            active_tenants.append(config)

            # Aggregate statistics
            crm_types = {}
            total_cases = 0

            for tenant in active_tenants:
                crm_type = tenant.get('crm_config', {}).get('type', 'unknown')
                crm_types[crm_type] = crm_types.get(crm_type, 0) + 1

                case_summary = tenant.get('case_data_summary', {})
                total_cases += case_summary.get('total_cases', 0)

            return {
                'total_tenants': len(all_tenants),
                'active_tenants': len(active_tenants),
                'inactive_tenants': len(all_tenants) - len(active_tenants),
                'crm_types': crm_types,
                'total_cases_managed': total_cases,
                'config_directory': str(self.config_directory),
                'cache_entries': len(self.tenant_cache),
                'last_updated': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get tenant stats: {e}")
            return {
                'total_tenants': 0,
                'active_tenants': 0,
                'error': str(e)
            }

    def _get_default_processing_limits(self) -> Dict[str, Any]:
        """Get default processing limits for tenants without configuration."""
        return {
            'concurrent_limit': 10,
            'retry_attempts': 2,
            'session_timeout_hours': 4,
            'max_jobs_per_hour': 60,
            'batch_size': 50,
            'rate_limiting': {
                'enabled': True,
                'requests_per_minute': 30,
                'burst_limit': 5
            }
        }

    def _get_default_vector_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get default vector configuration for tenant."""
        return {
            'shared_indexes': True,
            'case_summaries_index': 'caseguard-case-summaries',
            'case_details_index': 'caseguard-case-details',
            'embedding_model': 'text-embedding-3-large',
            'chunk_size': 800,
            'dimension': 3072,
            'metadata_filters': {
                'tenant_id': tenant_id,
                'privacy_level': 'confidential'
            }
        }

    def _resolve_credential_variables(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """Resolve environment variables in credential configurations.

        Args:
            credentials: Raw credentials configuration with potential env vars

        Returns:
            Resolved credentials with actual values
        """
        import os
        import re

        resolved = {}

        for key, value in credentials.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # Extract environment variable name
                env_var = value[2:-1]  # Remove ${ and }
                resolved_value = os.getenv(env_var)

                if resolved_value is None:
                    logger.warning(f"Environment variable {env_var} not found for credential {key}")
                    resolved[key] = value  # Keep original if not found
                else:
                    resolved[key] = resolved_value
            else:
                resolved[key] = value

        return resolved

    def clear_cache(self):
        """Clear tenant configuration cache."""
        self.tenant_cache.clear()
        logger.info("Tenant configuration cache cleared")


# Utility functions
def create_tenant_manager(config_directory: str = "v2/configs/tenants") -> TenantManager:
    """Create a tenant manager instance.

    Args:
        config_directory: Directory containing tenant configurations

    Returns:
        Configured TenantManager instance
    """
    return TenantManager(config_directory=config_directory)


async def validate_all_tenant_configs(config_directory: str = "v2/configs/tenants") -> Dict[str, Any]:
    """Validate all tenant configurations in a directory.

    Args:
        config_directory: Directory containing tenant configurations

    Returns:
        Validation results
    """
    manager = TenantManager(config_directory=config_directory)
    validation_results = {
        'valid_tenants': [],
        'invalid_tenants': [],
        'validation_errors': [],
        'total_checked': 0
    }

    config_dir = Path(config_directory)
    if not config_dir.exists():
        validation_results['validation_errors'].append(f"Config directory does not exist: {config_directory}")
        return validation_results

    for config_file in config_dir.glob("*.json"):
        tenant_id = config_file.stem
        validation_results['total_checked'] += 1

        try:
            config = await manager.get_tenant_config(tenant_id)
            if config:
                # Validate configuration structure
                TenantConfig(**config)
                validation_results['valid_tenants'].append(tenant_id)
            else:
                validation_results['invalid_tenants'].append(tenant_id)
                validation_results['validation_errors'].append(f"Failed to load config for {tenant_id}")

        except Exception as e:
            validation_results['invalid_tenants'].append(tenant_id)
            validation_results['validation_errors'].append(f"Validation failed for {tenant_id}: {str(e)}")

    logger.info(f"Tenant validation complete: {len(validation_results['valid_tenants'])}/{validation_results['total_checked']} valid")
    return validation_results