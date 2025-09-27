"""Smart field retrieval with tenant context and fallback mechanisms."""

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
        """Initialize field retriever.

        Args:
            canonical_fields_path: Path to canonical fields configuration
            proclaim_client: ProclaimClient instance
            tenant_id: Tenant identifier
        """
        self.tenant_id = tenant_id
        self.proclaim_client = proclaim_client

        with open(canonical_fields_path, 'r') as f:
            config = json.load(f)

        self.global_fields = config["global_fields"]["fields"]
        self.hdr_fields = config["hdr_fields"]["fields"]

        logger.info(f"SmartFieldRetriever initialized for tenant {tenant_id}")

    def extract_canonical_fields_with_tenant_context(self, case_ref: str) -> Dict[str, Any]:
        """Extract all canonical fields with tenant metadata.

        Args:
            case_ref: Case reference

        Returns:
            Dictionary with extracted fields and metadata
        """
        logger.info(f"Extracting canonical fields for case {case_ref}")

        # Get all critical fields
        critical_fields = [
            "date_opened", "date_loc_sent", "date_landlord_response_received",
            "date_expert_inspection", "date_proceedings_issued", "date_closed",
            "case_status", "case_outcome", "claimant_name", "defendant_name",
            "handler_name", "settlement_amount", "total_costs_claimed",
            "property_address", "disrepair_issues"
        ]

        extracted_data = {
            "tenant_id": self.tenant_id,
            "case_ref": case_ref,
            "extraction_timestamp": datetime.now().isoformat()
        }

        # Extract each field
        for field_name in critical_fields:
            try:
                value, success, method = self.get_field(case_ref, field_name)
                if success and value:
                    extracted_data[field_name] = {
                        "value": value,
                        "extraction_method": method,
                        "tenant_id": self.tenant_id
                    }
            except Exception as e:
                logger.warning(f"Failed to extract field {field_name}: {e}")

        logger.info(f"Extracted {len(extracted_data) - 3} fields for case {case_ref}")
        return extracted_data

    def get_field(self, case_ref: str, field_name: str, case_type: str = '104') -> Tuple[Any, bool, str]:
        """Get a specific field value using configured extraction method.

        Args:
            case_ref: Case reference
            field_name: Field name to extract
            case_type: Case type (default HDR = 104)

        Returns:
            Tuple of (value, success, extraction_method)
        """
        # Check global fields first
        if field_name in self.global_fields:
            return self._extract_global_field(case_ref, field_name)

        # Then check HDR fields
        if field_name in self.hdr_fields:
            return self._extract_hdr_field(case_ref, field_name)

        return None, False, 'field_not_found'

    def _extract_global_field(self, case_ref: str, field_name: str) -> Tuple[Any, bool, str]:
        """Extract global field via direct API access.

        Args:
            case_ref: Case reference
            field_name: Field name

        Returns:
            Tuple of (value, success, method)
        """
        field_config = self.global_fields[field_name]
        api_path = field_config['api_path']

        try:
            # Get case data from Proclaim client
            case_data = self.proclaim_client.get_case_data(case_ref)

            # Navigate API path
            value = self._navigate_dict_path(case_data, api_path)

            if value is not None:
                # Convert data type if needed
                converted_value = self._convert_data_type(value, field_config['data_type'])
                return converted_value, True, 'direct_api'

        except Exception as e:
            logger.warning(f"Failed to extract global field {field_name}: {e}")

        return None, False, 'api_error'

    def _extract_hdr_field(self, case_ref: str, field_name: str) -> Tuple[Any, bool, str]:
        """Extract HDR field using specialized extraction methods.

        Args:
            case_ref: Case reference
            field_name: Field name

        Returns:
            Tuple of (value, success, method)
        """
        field_config = self.hdr_fields[field_name]
        extraction_method = field_config['extraction_method']

        try:
            if extraction_method == 'party_extraction':
                return self._extract_party_field(case_ref, field_config)
            elif extraction_method == 'direct_hdr':
                return self._extract_direct_hdr_field(case_ref, field_config)
            elif extraction_method == 'timeline_search':
                return self._extract_timeline_field(case_ref, field_config)
            elif extraction_method == 'costs_extraction':
                return self._extract_costs_field(case_ref, field_config)
            elif extraction_method == 'case_details':
                return self._extract_case_details_field(case_ref, field_config)

        except Exception as e:
            logger.warning(f"Failed to extract HDR field {field_name}: {e}")

        return None, False, 'extraction_error'

    def _extract_party_field(self, case_ref: str, field_config: Dict) -> Tuple[Any, bool, str]:
        """Extract party-related field.

        Args:
            case_ref: Case reference
            field_config: Field configuration

        Returns:
            Tuple of (value, success, method)
        """
        try:
            case_data = self.proclaim_client.get_case_data(case_ref)
            parties = case_data.get('parties', [])

            party_type = field_config['party_type']

            for party in parties:
                if party.get('type', '').lower() == party_type.lower():
                    if 'detail_field' in field_config:
                        # Extract specific detail field
                        detail_field = field_config['detail_field']
                        value = party.get(detail_field)
                    else:
                        # Extract name or address
                        value = party.get('name') or party.get('address')

                    if value:
                        converted_value = self._convert_data_type(value, field_config['data_type'])
                        return converted_value, True, 'party_extraction'

        except Exception as e:
            logger.warning(f"Party extraction failed: {e}")

        return None, False, 'party_not_found'

    def _extract_direct_hdr_field(self, case_ref: str, field_config: Dict) -> Tuple[Any, bool, str]:
        """Extract field directly from HDR data.

        Args:
            case_ref: Case reference
            field_config: Field configuration

        Returns:
            Tuple of (value, success, method)
        """
        try:
            case_data = self.proclaim_client.get_case_data(case_ref)
            hdr_field = field_config['hdr_field']

            # Look for HDR-specific data structure
            hdr_data = case_data.get('hdr_data') or case_data.get('case_details', {})
            value = hdr_data.get(hdr_field)

            if value:
                converted_value = self._convert_data_type(value, field_config['data_type'])
                return converted_value, True, 'direct_hdr'

        except Exception as e:
            logger.warning(f"Direct HDR extraction failed: {e}")

        return None, False, 'hdr_data_not_found'

    def _extract_timeline_field(self, case_ref: str, field_config: Dict) -> Tuple[Any, bool, str]:
        """Extract field from case timeline/history.

        Args:
            case_ref: Case reference
            field_config: Field configuration

        Returns:
            Tuple of (value, success, method)
        """
        try:
            case_data = self.proclaim_client.get_case_data(case_ref)
            history = case_data.get('history', [])
            search_terms = field_config['search_terms']

            # Search through timeline events
            for event in history:
                event_text = str(event.get('description', '') + ' ' + event.get('notes', '')).lower()

                for search_term in search_terms:
                    if search_term.lower() in event_text:
                        # Found matching event, extract date or value
                        if field_config['data_type'] == 'date':
                            date_value = event.get('date') or event.get('created_date')
                            if date_value:
                                return date_value, True, 'timeline_search'
                        else:
                            # Try to extract other values from event
                            value = self._extract_value_from_text(event_text, field_config['data_type'])
                            if value:
                                return value, True, 'timeline_search'

        except Exception as e:
            logger.warning(f"Timeline extraction failed: {e}")

        return None, False, 'timeline_not_found'

    def _extract_costs_field(self, case_ref: str, field_config: Dict) -> Tuple[Any, bool, str]:
        """Extract costs-related field.

        Args:
            case_ref: Case reference
            field_config: Field configuration

        Returns:
            Tuple of (value, success, method)
        """
        try:
            case_data = self.proclaim_client.get_case_data(case_ref)
            cost_type = field_config['cost_type']

            # Look for costs data
            costs_data = case_data.get('costs', {})
            value = costs_data.get(cost_type)

            if value is not None:
                converted_value = self._convert_data_type(value, field_config['data_type'])
                return converted_value, True, 'costs_extraction'

        except Exception as e:
            logger.warning(f"Costs extraction failed: {e}")

        return None, False, 'costs_not_found'

    def _extract_case_details_field(self, case_ref: str, field_config: Dict) -> Tuple[Any, bool, str]:
        """Extract field from case details.

        Args:
            case_ref: Case reference
            field_config: Field configuration

        Returns:
            Tuple of (value, success, method)
        """
        try:
            case_data = self.proclaim_client.get_case_data(case_ref)
            detail_field = field_config['detail_field']

            case_details = case_data.get('case_details', {})
            value = case_details.get(detail_field)

            if value is not None:
                converted_value = self._convert_data_type(value, field_config['data_type'])
                return converted_value, True, 'case_details'

        except Exception as e:
            logger.warning(f"Case details extraction failed: {e}")

        return None, False, 'details_not_found'

    def _navigate_dict_path(self, data: Dict, path: str) -> Any:
        """Navigate dictionary using dot-notation path.

        Args:
            data: Dictionary to navigate
            path: Dot-notation path (e.g., 'handler.name')

        Returns:
            Value at path or None
        """
        try:
            current = data
            for key in path.split('.'):
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return None
            return current
        except Exception:
            return None

    def _convert_data_type(self, value: Any, data_type: str) -> Any:
        """Convert value to specified data type.

        Args:
            value: Raw value
            data_type: Target data type

        Returns:
            Converted value
        """
        try:
            if data_type == 'string':
                return str(value) if value is not None else None
            elif data_type == 'date':
                # Handle various date formats
                if isinstance(value, str):
                    # Try to parse common date formats
                    from dateutil.parser import parse
                    return parse(value).isoformat()
                return str(value)
            elif data_type == 'decimal':
                return float(value) if value is not None else None
            elif data_type == 'array':
                if isinstance(value, list):
                    return value
                elif isinstance(value, str):
                    # Try to split string into array
                    return [item.strip() for item in value.split(',')]
                return [str(value)] if value is not None else None
            else:
                return value
        except Exception as e:
            logger.warning(f"Data type conversion failed: {e}")
            return value

    def _extract_value_from_text(self, text: str, data_type: str) -> Any:
        """Extract value from text based on data type.

        Args:
            text: Source text
            data_type: Expected data type

        Returns:
            Extracted value or None
        """
        try:
            if data_type == 'decimal':
                # Look for currency amounts
                money_pattern = r'£?([0-9,]+\.?[0-9]*)'
                matches = re.findall(money_pattern, text)
                if matches:
                    amount_str = matches[0].replace(',', '')
                    return float(amount_str)
            elif data_type == 'date':
                # Look for dates in text
                date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
                matches = re.findall(date_pattern, text)
                if matches:
                    from dateutil.parser import parse
                    return parse(matches[0]).isoformat()
        except Exception as e:
            logger.warning(f"Value extraction from text failed: {e}")

        return None

    def get_multiple_fields(self, case_data: Dict, field_names: List[str]) -> Dict[str, Any]:
        """Get multiple fields efficiently.

        Args:
            case_data: Case data dictionary
            field_names: List of field names to extract

        Returns:
            Dictionary of field_name -> value
        """
        results = {}
        case_ref = case_data.get('case_ref', 'unknown')

        for field_name in field_names:
            try:
                value, success, method = self.get_field(case_ref, field_name)
                if success:
                    results[field_name] = value
            except Exception as e:
                logger.warning(f"Failed to get field {field_name}: {e}")

        return results