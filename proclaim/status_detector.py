"""Status detection integrating with existing canonical fields system."""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class CaseStatus(str, Enum):
    """Case status enumeration based on FDM data."""
    ACTIVE = "active"
    COMPLETE = "complete"
    CLOSED = "closed"
    PENDING = "pending"
    UNKNOWN = "unknown"


class ProcessingPriority(str, Enum):
    """Case processing priority levels."""
    CRITICAL = "critical"    # Settlement likelihood >= 0.8
    HIGH = "high"           # Settlement likelihood >= 0.6
    MEDIUM = "medium"       # Settlement likelihood >= 0.3
    LOW = "low"            # Settlement likelihood < 0.3 or complete cases
    SKIP = "skip"          # Cases that don't need processing


class StatusDetector:
    """Integrate with existing canonical fields system for status detection."""

    def __init__(self):
        """Initialize status detector with existing HDR system integration."""
        # Import existing components from the current implementation
        try:
            from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever
            self.field_retriever = SmartFieldRetriever()
            self.has_field_retriever = True
            logger.info("StatusDetector initialized with SmartFieldRetriever integration")
        except ImportError as e:
            logger.warning(f"SmartFieldRetriever not available: {e}. Using fallback methods.")
            self.field_retriever = None
            self.has_field_retriever = False

    def detect_case_status(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract status information using proven canonical fields extraction.

        Args:
            case_data: Raw case data from Proclaim or other sources

        Returns:
            Dictionary with status information and metadata
        """
        case_ref = case_data.get("case_ref", "unknown")
        logger.debug(f"Detecting status for case {case_ref}")

        status_info = {
            "case_ref": case_ref,
            "detection_method": "canonical_fields" if self.has_field_retriever else "fallback",
            "detected_at": datetime.utcnow().isoformat()
        }

        try:
            if self.has_field_retriever:
                # Use existing smart field retriever
                canonical_fields = self.field_retriever.get_multiple_fields(case_data, [
                    'case_status', 'case_outcome', 'date_opened', 'date_closed',
                    'handler_name', 'client_name', 'case_type'
                ])

                status_info.update({
                    'case_status': canonical_fields.get('case_status', 'Unknown'),
                    'case_outcome': canonical_fields.get('case_outcome'),
                    'date_opened': canonical_fields.get('date_opened'),
                    'date_closed': canonical_fields.get('date_closed'),
                    'handler_name': canonical_fields.get('handler_name'),
                    'client_name': canonical_fields.get('client_name'),
                    'case_type': canonical_fields.get('case_type'),
                    'canonical_fields_available': True
                })

                # Determine active status using canonical fields
                status_info['is_active'] = self._determine_active_status(canonical_fields)

                # Calculate settlement likelihood using existing system
                status_info['settlement_likelihood'] = self._calculate_settlement_probability(case_data)

            else:
                # Fallback to basic field extraction
                status_info.update(self._fallback_status_detection(case_data))

        except Exception as e:
            logger.error(f"Status detection failed for {case_ref}: {e}")
            status_info.update(self._fallback_status_detection(case_data))
            status_info['detection_error'] = str(e)

        return status_info

    def _determine_active_status(self, canonical_fields: Dict[str, Any]) -> bool:
        """Determine if case is active based on canonical fields.

        Based on FDM CSV data showing Active (1037 cases) vs Complete (1080 cases).

        Args:
            canonical_fields: Extracted canonical fields

        Returns:
            True if case is active, False otherwise
        """
        case_status = str(canonical_fields.get('case_status', '')).lower()

        # Primary status indicators from FDM data
        if 'complete' in case_status or 'closed' in case_status:
            return False
        elif 'active' in case_status or 'open' in case_status:
            return True

        # Fallback logic using dates
        date_closed = canonical_fields.get('date_closed')
        if date_closed:
            return False  # Case has close date, assume complete

        # Default to active if no clear indicators
        return True

    def _calculate_settlement_probability(self, case_data: Dict[str, Any]) -> float:
        """Use existing HDR settlement predictor if available.

        Args:
            case_data: Complete case data

        Returns:
            Settlement probability (0.0 to 1.0)
        """
        try:
            # Try to use existing settlement prediction system
            from caseguard.hdr_timeline.settlement import HDRSettlementPredictor

            settlement_predictor = HDRSettlementPredictor()
            probability = settlement_predictor.predict_settlement_probability(case_data)

            logger.debug(f"Settlement probability calculated: {probability:.2f}")
            return probability

        except ImportError:
            logger.warning("HDRSettlementPredictor not available, using fallback calculation")
            return self._fallback_settlement_calculation(case_data)

        except Exception as e:
            logger.warning(f"Settlement prediction failed: {e}, using fallback")
            return self._fallback_settlement_calculation(case_data)

    def _fallback_settlement_calculation(self, case_data: Dict[str, Any]) -> float:
        """Fallback settlement probability calculation.

        Args:
            case_data: Case data dictionary

        Returns:
            Estimated settlement probability
        """
        probability = 0.5  # Default neutral probability

        try:
            # Simple heuristics based on available data
            core_details = case_data.get("core_details", {})
            history = case_data.get("history", [])

            # Case age factor (newer cases might be more likely to settle)
            opened_date = core_details.get("date_opened") or core_details.get("opened_date")
            if opened_date:
                probability += 0.1

            # Activity level factor
            if len(history) > 20:  # High activity
                probability += 0.2
            elif len(history) > 10:  # Medium activity
                probability += 0.1

            # Case type considerations
            case_type = str(core_details.get("case_type", "")).lower()
            if "personal injury" in case_type or "clinical" in case_type:
                probability += 0.1  # These often settle

            # Status indicators
            status = str(core_details.get("case_status", "")).lower()
            if "settlement" in status or "negotiation" in status:
                probability += 0.3
            elif "litigation" in status or "court" in status:
                probability -= 0.1  # Less likely to settle quickly

            # Clamp to valid range
            probability = max(0.0, min(1.0, probability))

        except Exception as e:
            logger.warning(f"Fallback settlement calculation failed: {e}")
            probability = 0.5

        return probability

    def _fallback_status_detection(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback status detection when canonical fields system not available.

        Args:
            case_data: Raw case data

        Returns:
            Basic status information
        """
        core_details = case_data.get("core_details", {})

        # Extract basic fields directly
        case_status = str(core_details.get("case_status") or core_details.get("status", "")).lower()

        return {
            'case_status': core_details.get("case_status", "Unknown"),
            'case_outcome': core_details.get("case_outcome"),
            'date_opened': core_details.get("date_opened") or core_details.get("opened_date"),
            'date_closed': core_details.get("date_closed") or core_details.get("closed_date"),
            'handler_name': core_details.get("handler_name") or core_details.get("handler"),
            'client_name': core_details.get("client_name") or core_details.get("client"),
            'case_type': core_details.get("case_type") or core_details.get("category"),
            'is_active': 'complete' not in case_status and 'closed' not in case_status,
            'settlement_likelihood': self._fallback_settlement_calculation(case_data),
            'canonical_fields_available': False
        }


class ProcessingPriorityManager:
    """Manage case processing priority based on status detection and HDR compliance logic."""

    def __init__(self):
        """Initialize priority manager with status detector."""
        self.status_detector = StatusDetector()

    def prioritize_cases(self, case_refs: List[str], case_data_map: Dict[str, Dict[str, Any]] = None) -> Dict[str, List[str]]:
        """Organize cases by processing priority based on HDR compliance logic.

        Args:
            case_refs: List of case references to prioritize
            case_data_map: Optional mapping of case_ref to case data

        Returns:
            Dictionary with priority levels and corresponding case lists
        """
        logger.info(f"Prioritizing {len(case_refs)} cases for processing")

        priorities = {
            'critical': [],  # Active cases with high settlement likelihood (>= 0.8)
            'high': [],      # Active cases with moderate settlement likelihood (>= 0.6)
            'medium': [],    # Active cases with low settlement likelihood (>= 0.3)
            'low': [],       # Complete cases or very low likelihood (< 0.3)
            'skip': []       # Cases that don't need processing
        }

        for case_ref in case_refs:
            try:
                # Get case data if available
                case_data = case_data_map.get(case_ref, {}) if case_data_map else {"case_ref": case_ref}

                # Detect case status
                status_info = self.status_detector.detect_case_status(case_data)

                # Determine priority based on status and settlement likelihood
                priority = self._calculate_processing_priority(status_info)
                priorities[priority].append(case_ref)

                logger.debug(f"Case {case_ref}: priority={priority}, "
                           f"active={status_info.get('is_active')}, "
                           f"settlement={status_info.get('settlement_likelihood', 0):.2f}")

            except Exception as e:
                logger.error(f"Failed to prioritize case {case_ref}: {e}")
                priorities['medium'].append(case_ref)  # Default to medium priority

        # Log priority distribution
        total_cases = sum(len(cases) for cases in priorities.values())
        priority_summary = {level: len(cases) for level, cases in priorities.items()}
        logger.info(f"Priority distribution: {priority_summary} (total: {total_cases})")

        return priorities

    def _calculate_processing_priority(self, status_info: Dict[str, Any]) -> str:
        """Calculate processing priority based on status information.

        Uses thresholds from caseguard/hdr_timeline/stage_detector.py:92-398.

        Args:
            status_info: Status detection results

        Returns:
            Priority level string
        """
        is_active = status_info.get('is_active', True)
        settlement_likelihood = status_info.get('settlement_likelihood', 0.5)

        # Complete/closed cases get low priority
        if not is_active:
            return 'low'

        # Active cases prioritized by settlement likelihood
        if settlement_likelihood >= 0.8:
            return 'critical'  # Very high likelihood
        elif settlement_likelihood >= 0.6:
            return 'high'      # High likelihood
        elif settlement_likelihood >= 0.3:
            return 'medium'    # Moderate likelihood
        else:
            return 'low'       # Low likelihood

    def get_processing_recommendations(
        self,
        priorities: Dict[str, List[str]],
        max_concurrent: int = 25
    ) -> Dict[str, Any]:
        """Get recommendations for processing based on priority analysis.

        Args:
            priorities: Priority distribution from prioritize_cases
            max_concurrent: Maximum concurrent processing capacity

        Returns:
            Processing recommendations
        """
        total_cases = sum(len(cases) for cases in priorities.values())
        actionable_cases = total_cases - len(priorities['skip'])

        recommendations = {
            "total_cases": total_cases,
            "actionable_cases": actionable_cases,
            "skippable_cases": len(priorities['skip']),
            "priority_distribution": {level: len(cases) for level, cases in priorities.items()},
            "processing_batches": [],
            "estimated_processing_time_hours": 0
        }

        # Create processing batches in priority order
        batch_order = ['critical', 'high', 'medium', 'low']
        current_batch = []
        batch_number = 1

        for priority_level in batch_order:
            cases = priorities[priority_level]
            if not cases:
                continue

            for case_ref in cases:
                current_batch.append({
                    "case_ref": case_ref,
                    "priority": priority_level
                })

                # Create batch when we reach max concurrent limit
                if len(current_batch) >= max_concurrent:
                    recommendations["processing_batches"].append({
                        "batch_number": batch_number,
                        "cases": current_batch.copy(),
                        "priority_mix": self._get_batch_priority_mix(current_batch)
                    })
                    current_batch = []
                    batch_number += 1

        # Add remaining cases as final batch
        if current_batch:
            recommendations["processing_batches"].append({
                "batch_number": batch_number,
                "cases": current_batch,
                "priority_mix": self._get_batch_priority_mix(current_batch)
            })

        # Estimate processing time (rough calculation)
        high_priority_cases = len(priorities['critical']) + len(priorities['high'])
        medium_priority_cases = len(priorities['medium'])
        low_priority_cases = len(priorities['low'])

        # Assume different processing times per priority
        estimated_hours = (
            high_priority_cases * 0.5 +  # 30 minutes per high priority case
            medium_priority_cases * 0.25 +  # 15 minutes per medium priority case
            low_priority_cases * 0.1  # 6 minutes per low priority case
        )
        recommendations["estimated_processing_time_hours"] = estimated_hours

        return recommendations

    def _get_batch_priority_mix(self, batch_cases: List[Dict[str, str]]) -> Dict[str, int]:
        """Get priority mix for a batch of cases.

        Args:
            batch_cases: List of case dictionaries with priority information

        Returns:
            Priority mix dictionary
        """
        mix = {}
        for case in batch_cases:
            priority = case.get("priority", "unknown")
            mix[priority] = mix.get(priority, 0) + 1
        return mix


# Utility functions
def create_status_detector() -> StatusDetector:
    """Create a status detector instance.

    Returns:
        Configured StatusDetector instance
    """
    return StatusDetector()


def create_priority_manager() -> ProcessingPriorityManager:
    """Create a processing priority manager.

    Returns:
        Configured ProcessingPriorityManager instance
    """
    return ProcessingPriorityManager()


def analyze_case_portfolio(case_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze a portfolio of cases for status and priority insights.

    Args:
        case_data_list: List of case data dictionaries

    Returns:
        Portfolio analysis results
    """
    logger.info(f"Analyzing portfolio of {len(case_data_list)} cases")

    status_detector = StatusDetector()
    priority_manager = ProcessingPriorityManager()

    # Analyze each case
    case_analyses = []
    case_data_map = {}

    for case_data in case_data_list:
        case_ref = case_data.get("case_ref", f"case_{len(case_analyses)}")

        try:
            status_info = status_detector.detect_case_status(case_data)
            case_analyses.append(status_info)
            case_data_map[case_ref] = case_data
        except Exception as e:
            logger.error(f"Failed to analyze case {case_ref}: {e}")

    # Get case references and prioritize
    case_refs = [analysis["case_ref"] for analysis in case_analyses]
    priorities = priority_manager.prioritize_cases(case_refs, case_data_map)

    # Calculate portfolio statistics
    active_cases = sum(1 for analysis in case_analyses if analysis.get("is_active", False))
    complete_cases = len(case_analyses) - active_cases
    avg_settlement_likelihood = sum(
        analysis.get("settlement_likelihood", 0.5) for analysis in case_analyses
    ) / max(len(case_analyses), 1)

    portfolio_analysis = {
        "total_cases": len(case_data_list),
        "active_cases": active_cases,
        "complete_cases": complete_cases,
        "average_settlement_likelihood": avg_settlement_likelihood,
        "priority_distribution": {level: len(cases) for level, cases in priorities.items()},
        "status_distribution": {},
        "processing_recommendations": priority_manager.get_processing_recommendations(priorities),
        "analysis_timestamp": datetime.utcnow().isoformat()
    }

    # Calculate status distribution
    status_counts = {}
    for analysis in case_analyses:
        status = analysis.get("case_status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    portfolio_analysis["status_distribution"] = status_counts

    logger.info(f"Portfolio analysis complete: {active_cases}/{len(case_data_list)} active cases, "
               f"avg settlement likelihood: {avg_settlement_likelihood:.2f}")

    return portfolio_analysis