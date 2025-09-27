"""Abstract interface for case discovery with multiple adapter implementations."""

import csv
import logging
import yaml
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class CRMCaseDiscovery(ABC):
    """Abstract interface for case discovery - to be implemented when CRM provides endpoints."""

    def __init__(self, tenant_id: str):
        """Initialize case discovery for a specific tenant.

        Args:
            tenant_id: Law firm tenant identifier
        """
        self.tenant_id = tenant_id
        logger.info(f"Initializing case discovery for tenant: {tenant_id}")

    @abstractmethod
    def enumerate_all_cases(self, include_closed: bool = True) -> List[Dict[str, Any]]:
        """Get complete case inventory for tenant - REQUIRES NEW CRM ENDPOINT.

        Args:
            include_closed: Whether to include closed/complete cases

        Returns:
            List of case dictionaries with metadata
        """
        pass

    @abstractmethod
    def get_active_cases(self) -> List[Dict[str, Any]]:
        """Get currently active cases - REQUIRES NEW CRM ENDPOINT.

        Returns:
            List of active case dictionaries
        """
        pass

    @abstractmethod
    def check_case_serialno(self, case_ref: str) -> int:
        """Get case serial number for change detection - REQUIRES NEW CRM ENDPOINT.

        Args:
            case_ref: Individual case reference

        Returns:
            Current serial number for the case
        """
        pass

    def get_case_summary(self) -> Dict[str, Any]:
        """Get summary statistics for tenant's cases.

        Returns:
            Summary dictionary with case counts and statistics
        """
        try:
            all_cases = self.enumerate_all_cases(include_closed=True)
            active_cases = [case for case in all_cases if case.get("is_active", True)]
            closed_cases = [case for case in all_cases if not case.get("is_active", True)]

            return {
                "tenant_id": self.tenant_id,
                "total_cases": len(all_cases),
                "active_cases": len(active_cases),
                "closed_cases": len(closed_cases),
                "summary_generated_at": datetime.utcnow().isoformat(),
                "discovery_method": self.__class__.__name__
            }

        except Exception as e:
            logger.error(f"Failed to generate case summary for {self.tenant_id}: {e}")
            return {
                "tenant_id": self.tenant_id,
                "error": str(e),
                "summary_generated_at": datetime.utcnow().isoformat()
            }


class ProclaimCRMAdapter(CRMCaseDiscovery):
    """Implementation for Proclaim CRM when endpoints become available."""

    def __init__(self, tenant_id: str, api_base_url: str = None, credentials: Dict[str, str] = None):
        """Initialize Proclaim CRM adapter.

        Args:
            tenant_id: Law firm tenant identifier
            api_base_url: Proclaim API base URL
            credentials: API credentials dictionary
        """
        super().__init__(tenant_id)
        self.api_base_url = api_base_url
        self.credentials = credentials or {}
        self.client = None  # Will use enhanced Proclaim client when available

        logger.warning("ProclaimCRMAdapter initialized but endpoints not yet available")

    def enumerate_all_cases(self, include_closed: bool = True) -> List[Dict[str, Any]]:
        """Get all cases using real ProclaimClient integration."""
        try:
            # Import here to avoid circular dependency
            from core.session_manager import V2SessionManager

            session_manager = V2SessionManager()
            proclaim_client = session_manager.get_proclaim_client(self.tenant_id)

            # Since Proclaim doesn't have bulk enumeration, we fall back to configured case list
            # This could be enhanced when bulk endpoints become available
            logger.warning("Using fallback case enumeration - bulk API endpoints not available")

            # For now, return empty list or implement search-based enumeration
            cases = []

            # Try to search for recent cases
            try:
                search_results = proclaim_client.search_cases("*", limit=1000)
                for result in search_results:
                    case_data = {
                        'case_ref': result.get('case_ref', ''),
                        'tenant_id': self.tenant_id,
                        'status': result.get('status', 'unknown'),
                        'is_active': result.get('status', '').lower() != 'complete',
                        'source': 'proclaim_search',
                        'last_modified': datetime.utcnow().isoformat()
                    }
                    cases.append(case_data)

            except Exception as e:
                logger.warning(f"Search-based enumeration failed: {e}")

            if include_closed:
                return cases
            else:
                return [case for case in cases if case.get('is_active', True)]

        except Exception as e:
            logger.error(f"Case enumeration failed: {e}")
            raise

    def get_active_cases(self) -> List[Dict[str, Any]]:
        """Get active cases using real ProclaimClient integration."""
        return self.enumerate_all_cases(include_closed=False)

    def check_case_serialno(self, case_ref: str) -> int:
        """Get case serial number using ProclaimClient integration."""
        try:
            from core.session_manager import V2SessionManager

            session_manager = V2SessionManager()
            proclaim_client = session_manager.get_proclaim_client(self.tenant_id)

            # Get case data and use hash of case_ref as serial number
            # This is a fallback until real serial numbers become available
            case_data = proclaim_client.get_case_data(case_ref)
            if case_data:
                # Use hash of case_ref + last_modified for simple versioning
                import hashlib
                data_string = f"{case_ref}_{case_data.get('last_modified', '')}"
                return abs(hash(data_string)) % 100000

            return 0

        except Exception as e:
            logger.warning(f"Serial number check failed for {case_ref}: {e}")
            return abs(hash(case_ref)) % 100000


class CSVFallbackAdapter(CRMCaseDiscovery):
    """Fallback adapter using FDM CSV case data - 2117 cases (1037 Active, 1080 Complete)."""

    def __init__(self, tenant_id: str, csv_path: str = "FDM example Funded Cases.csv"):
        """Initialize CSV fallback adapter.

        Args:
            tenant_id: Law firm tenant identifier
            csv_path: Path to CSV file with case data
        """
        super().__init__(tenant_id)
        self.csv_path = Path(csv_path)
        self.case_data = None
        self._load_csv_data()

        logger.info(f"CSVFallbackAdapter loaded {len(self.case_data) if self.case_data is not None else 0} cases")

    def _load_csv_data(self) -> None:
        """Load case data from CSV file."""
        try:
            if not self.csv_path.exists():
                logger.error(f"CSV file not found: {self.csv_path}")
                self.case_data = []
                return

            cases = []
            with open(self.csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Map CSV columns to standard case format
                    case_ref = row.get('Solicitor Reference', '').strip()
                    if not case_ref:
                        continue

                    case = {
                        'case_ref': case_ref,
                        'tenant_id': self.tenant_id,
                        'status': row.get('Status', '').strip(),
                        'is_active': row.get('Status', '').strip().lower() == 'active',
                        'case_type': row.get('Category', '').strip(),
                        'client_name': row.get('Client', '').strip(),
                        'handler': row.get('Handler', '').strip(),
                        'opened_date': self._parse_date(row.get('Date Opened')),
                        'closed_date': self._parse_date(row.get('Date Closed')) if row.get('Status', '').lower() == 'complete' else None,
                        'source': 'csv_fallback',
                        'serialno': hash(case_ref) % 100000,  # Generate consistent fake serial numbers
                        'last_modified': datetime.utcnow().isoformat()
                    }
                    cases.append(case)

            self.case_data = cases
            logger.info(f"Loaded {len(cases)} cases from CSV: {sum(1 for c in cases if c['is_active'])} active, "
                       f"{sum(1 for c in cases if not c['is_active'])} complete")

        except Exception as e:
            logger.error(f"Failed to load CSV data from {self.csv_path}: {e}")
            self.case_data = []

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format.

        Args:
            date_str: Date string in various formats

        Returns:
            ISO formatted date string or None
        """
        if not date_str or date_str.strip() == '':
            return None

        try:
            # Try common date formats
            import dateutil.parser
            parsed_date = dateutil.parser.parse(date_str)
            return parsed_date.isoformat()
        except Exception:
            logger.warning(f"Could not parse date: {date_str}")
            return None

    def enumerate_all_cases(self, include_closed: bool = True) -> List[Dict[str, Any]]:
        """Load all 2117 cases from FDM CSV.

        Args:
            include_closed: Whether to include completed cases

        Returns:
            List of case dictionaries
        """
        if self.case_data is None:
            logger.error("CSV data not loaded")
            return []

        if include_closed:
            return self.case_data.copy()
        else:
            # Return only active cases
            active_cases = [case for case in self.case_data if case.get('is_active', True)]
            logger.info(f"Returning {len(active_cases)} active cases (excluding {len(self.case_data) - len(active_cases)} closed)")
            return active_cases

    def get_active_cases(self) -> List[Dict[str, Any]]:
        """Get only Active cases (1037 cases from FDM CSV).

        Returns:
            List of active case dictionaries
        """
        if self.case_data is None:
            logger.error("CSV data not loaded")
            return []

        active_cases = [case for case in self.case_data if case.get('is_active', True)]
        logger.info(f"Returning {len(active_cases)} active cases from CSV")
        return active_cases

    def check_case_serialno(self, case_ref: str) -> int:
        """Get simulated serial number for case.

        Args:
            case_ref: Case reference

        Returns:
            Simulated serial number
        """
        if self.case_data is None:
            return 0

        # Find case and return its serialno
        for case in self.case_data:
            if case['case_ref'] == case_ref:
                return case.get('serialno', 0)

        logger.warning(f"Case not found for serialno check: {case_ref}")
        return 0


class YAMLFallbackAdapter(CRMCaseDiscovery):
    """Legacy YAML fallback adapter - kept for compatibility."""

    def __init__(self, tenant_id: str, yaml_path: str = "config/cases.yaml"):
        """Initialize YAML fallback adapter.

        Args:
            tenant_id: Law firm tenant identifier
            yaml_path: Path to YAML configuration file
        """
        super().__init__(tenant_id)
        self.yaml_path = Path(yaml_path)
        self.yaml_config = self._load_yaml_config()

        case_count = len(self.yaml_config.get('case_numbers', []))
        logger.info(f"YAMLFallbackAdapter loaded {case_count} cases from {yaml_path}")

    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load YAML configuration file.

        Returns:
            Configuration dictionary
        """
        try:
            if not self.yaml_path.exists():
                logger.error(f"YAML file not found: {self.yaml_path}")
                return {}

            with open(self.yaml_path, 'r') as f:
                config = yaml.safe_load(f)
                return config or {}

        except Exception as e:
            logger.error(f"Failed to load YAML config from {self.yaml_path}: {e}")
            return {}

    def enumerate_all_cases(self, include_closed: bool = True) -> List[Dict[str, Any]]:
        """Use existing YAML case lists as temporary solution.

        Args:
            include_closed: Whether to include closed cases (ignored for YAML)

        Returns:
            List of case dictionaries from YAML
        """
        case_numbers = self.yaml_config.get('case_numbers', [])
        cases = []

        for case_ref in case_numbers:
            case = {
                'case_ref': str(case_ref),
                'tenant_id': self.tenant_id,
                'status': 'active',  # YAML doesn't specify status
                'is_active': True,
                'source': 'yaml_fallback',
                'serialno': hash(str(case_ref)) % 100000,  # Generate fake serial numbers
                'last_modified': datetime.utcnow().isoformat()
            }
            cases.append(case)

        logger.info(f"Enumerated {len(cases)} cases from YAML config")
        return cases

    def get_active_cases(self) -> List[Dict[str, Any]]:
        """Get all cases from YAML (assumes all are active).

        Returns:
            List of case dictionaries from YAML
        """
        return self.enumerate_all_cases(include_closed=False)

    def check_case_serialno(self, case_ref: str) -> int:
        """Get simulated serial number for YAML case.

        Args:
            case_ref: Case reference

        Returns:
            Simulated serial number based on case ref hash
        """
        return hash(case_ref) % 100000


# Factory function for creating appropriate discovery adapter
def create_case_discovery_adapter(
    tenant_id: str,
    adapter_type: str = "csv",
    **kwargs
) -> CRMCaseDiscovery:
    """Create appropriate case discovery adapter based on configuration.

    Args:
        tenant_id: Law firm tenant identifier
        adapter_type: Type of adapter (csv, yaml, proclaim)
        **kwargs: Additional adapter-specific arguments

    Returns:
        Configured case discovery adapter

    Raises:
        ValueError: If adapter type is unknown
    """
    logger.info(f"Creating {adapter_type} discovery adapter for tenant {tenant_id}")

    if adapter_type.lower() == "csv":
        return CSVFallbackAdapter(tenant_id, **kwargs)
    elif adapter_type.lower() == "yaml":
        return YAMLFallbackAdapter(tenant_id, **kwargs)
    elif adapter_type.lower() == "proclaim":
        return ProclaimCRMAdapter(tenant_id, **kwargs)
    else:
        raise ValueError(f"Unknown adapter type: {adapter_type}")


# Utility function for adapter testing
def test_discovery_adapter(adapter: CRMCaseDiscovery, sample_size: int = 5) -> Dict[str, Any]:
    """Test case discovery adapter functionality.

    Args:
        adapter: Case discovery adapter to test
        sample_size: Number of cases to sample for detailed testing

    Returns:
        Test results dictionary
    """
    test_results = {
        "adapter_type": adapter.__class__.__name__,
        "tenant_id": adapter.tenant_id,
        "test_timestamp": datetime.utcnow().isoformat(),
        "tests": {}
    }

    try:
        # Test case enumeration
        logger.info("Testing case enumeration...")
        all_cases = adapter.enumerate_all_cases(include_closed=True)
        test_results["tests"]["enumerate_all"] = {
            "success": True,
            "total_cases": len(all_cases),
            "sample_cases": all_cases[:sample_size]
        }

        # Test active cases
        logger.info("Testing active case retrieval...")
        active_cases = adapter.get_active_cases()
        test_results["tests"]["get_active"] = {
            "success": True,
            "active_cases": len(active_cases),
            "sample_cases": active_cases[:sample_size]
        }

        # Test serial number check (if cases available)
        if all_cases:
            sample_case = all_cases[0]['case_ref']
            logger.info(f"Testing serial number check for {sample_case}...")
            try:
                serialno = adapter.check_case_serialno(sample_case)
                test_results["tests"]["check_serialno"] = {
                    "success": True,
                    "sample_case": sample_case,
                    "serialno": serialno
                }
            except NotImplementedError as e:
                test_results["tests"]["check_serialno"] = {
                    "success": False,
                    "not_implemented": True,
                    "message": str(e)
                }

        # Test case summary
        logger.info("Testing case summary generation...")
        summary = adapter.get_case_summary()
        test_results["tests"]["get_summary"] = {
            "success": True,
            "summary": summary
        }

        test_results["overall_success"] = True

    except Exception as e:
        logger.error(f"Adapter test failed: {e}")
        test_results["overall_success"] = False
        test_results["error"] = str(e)

    return test_results