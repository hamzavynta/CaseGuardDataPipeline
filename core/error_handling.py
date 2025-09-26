"""Comprehensive error handling and recovery system for V2 architecture."""

import logging
import traceback
from typing import Dict, List, Any, Optional, Union, Type, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from contextlib import contextmanager
import asyncio
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error category classifications."""
    API_ERROR = "api_error"
    DATABASE_ERROR = "database_error"
    PROCESSING_ERROR = "processing_error"
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    CONFIGURATION_ERROR = "configuration_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_ERROR = "resource_error"
    INTEGRATION_ERROR = "integration_error"
    UNKNOWN_ERROR = "unknown_error"


class RecoveryAction(str, Enum):
    """Available recovery actions."""
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ESCALATE = "escalate"
    ABORT = "abort"
    WAIT_AND_RETRY = "wait_and_retry"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class ErrorContext:
    """Error context information."""
    tenant_id: Optional[str] = None
    case_ref: Optional[str] = None
    job_id: Optional[str] = None
    component: Optional[str] = None
    operation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Comprehensive error record."""
    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    exception_type: str
    traceback_str: str
    context: ErrorContext
    recovery_attempts: int = 0
    recovery_action: Optional[RecoveryAction] = None
    resolved: bool = False
    resolution_timestamp: Optional[datetime] = None


class CaseGuardError(Exception):
    """Base exception class for CaseGuard V2."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR,
        context: ErrorContext = None,
        recovery_action: RecoveryAction = RecoveryAction.ESCALATE,
        original_exception: Exception = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.category = category
        self.context = context or ErrorContext()
        self.recovery_action = recovery_action
        self.original_exception = original_exception
        self.timestamp = datetime.utcnow()


class APIError(CaseGuardError):
    """API-related errors."""

    def __init__(self, message: str, status_code: int = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.API_ERROR,
            **kwargs
        )
        self.status_code = status_code


class ProcessingError(CaseGuardError):
    """Processing pipeline errors."""

    def __init__(self, message: str, stage: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.PROCESSING_ERROR,
            **kwargs
        )
        self.stage = stage


class ValidationError(CaseGuardError):
    """Data validation errors."""

    def __init__(self, message: str, field: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION_ERROR,
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.field = field


class ConfigurationError(CaseGuardError):
    """Configuration and setup errors."""

    def __init__(self, message: str, config_section: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION_ERROR,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        self.config_section = config_section


class CircuitBreakerError(CaseGuardError):
    """Circuit breaker activation errors."""

    def __init__(self, message: str, circuit_name: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.INTEGRATION_ERROR,
            recovery_action=RecoveryAction.WAIT_AND_RETRY,
            **kwargs
        )
        self.circuit_name = circuit_name


@dataclass
class RecoveryStrategy:
    """Error recovery strategy configuration."""
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    exponential_backoff: bool = True
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 300
    fallback_enabled: bool = True
    escalation_threshold: int = 10


class ErrorHandler:
    """Comprehensive error handling and recovery system."""

    def __init__(self, tenant_id: str = None):
        """Initialize error handler.

        Args:
            tenant_id: Optional tenant ID for tenant-specific error handling
        """
        self.tenant_id = tenant_id
        self.error_records: Dict[str, ErrorRecord] = {}
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self.recovery_strategies: Dict[ErrorCategory, RecoveryStrategy] = {}
        self.error_listeners: List[Callable] = []

        self._setup_default_strategies()
        logger.info(f"ErrorHandler initialized for tenant: {tenant_id}")

    def handle_error(
        self,
        error: Union[Exception, CaseGuardError],
        context: ErrorContext = None,
        auto_recover: bool = True
    ) -> ErrorRecord:
        """Handle an error with automatic recovery attempts.

        Args:
            error: The error/exception to handle
            context: Error context information
            auto_recover: Whether to attempt automatic recovery

        Returns:
            Error record with handling results
        """
        # Convert standard exceptions to CaseGuardError
        if not isinstance(error, CaseGuardError):
            caseguard_error = self._convert_exception(error, context)
        else:
            caseguard_error = error
            if context:
                caseguard_error.context = context

        # Create error record
        error_record = self._create_error_record(caseguard_error)

        # Log error
        self._log_error(error_record)

        # Store error record
        self.error_records[error_record.error_id] = error_record

        # Notify listeners
        self._notify_error_listeners(error_record)

        # Attempt recovery if enabled
        if auto_recover:
            self._attempt_recovery(error_record)

        return error_record

    def add_recovery_strategy(self, category: ErrorCategory, strategy: RecoveryStrategy):
        """Add custom recovery strategy for error category.

        Args:
            category: Error category
            strategy: Recovery strategy configuration
        """
        self.recovery_strategies[category] = strategy
        logger.info(f"Added recovery strategy for {category}")

    def add_error_listener(self, callback: Callable[[ErrorRecord], None]):
        """Add error event listener.

        Args:
            callback: Callback function to receive error events
        """
        self.error_listeners.append(callback)
        logger.debug(f"Added error listener: {callback.__name__}")

    @contextmanager
    def error_context(self, context: ErrorContext):
        """Context manager for error handling with context.

        Args:
            context: Error context to apply
        """
        try:
            yield
        except Exception as e:
            error_record = self.handle_error(e, context)
            # Re-raise the error after handling if it's critical
            if error_record.severity == ErrorSeverity.CRITICAL:
                raise

    async def async_handle_with_retry(
        self,
        operation: Callable,
        context: ErrorContext = None,
        max_retries: int = None,
        delay_seconds: float = None
    ) -> Any:
        """Execute operation with automatic retry on failure.

        Args:
            operation: Async operation to execute
            context: Error context
            max_retries: Override default max retries
            delay_seconds: Override default delay

        Returns:
            Operation result

        Raises:
            Exception: If all retries are exhausted
        """
        attempt = 0
        last_error = None
        current_delay = delay_seconds or 1.0

        while attempt < (max_retries or 3):
            try:
                return await operation()
            except Exception as e:
                last_error = e
                attempt += 1

                error_record = self.handle_error(e, context, auto_recover=False)

                if attempt < (max_retries or 3):
                    logger.warning(f"Operation failed, retrying in {current_delay}s (attempt {attempt})")
                    await asyncio.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Operation failed after {attempt} attempts")
                    break

        # All retries exhausted
        if last_error:
            raise last_error

    def get_circuit_breaker_status(self, circuit_name: str) -> Dict[str, Any]:
        """Get circuit breaker status.

        Args:
            circuit_name: Circuit breaker name

        Returns:
            Circuit breaker status information
        """
        if circuit_name not in self.circuit_breakers:
            return {
                "name": circuit_name,
                "state": "closed",
                "failures": 0,
                "last_failure": None,
                "next_attempt": None
            }

        breaker = self.circuit_breakers[circuit_name]
        state = "closed"

        if breaker["failures"] >= breaker.get("threshold", 5):
            if datetime.utcnow() < breaker.get("open_until", datetime.utcnow()):
                state = "open"
            else:
                state = "half_open"

        return {
            "name": circuit_name,
            "state": state,
            "failures": breaker["failures"],
            "last_failure": breaker.get("last_failure"),
            "next_attempt": breaker.get("open_until")
        }

    def reset_circuit_breaker(self, circuit_name: str):
        """Reset circuit breaker to closed state.

        Args:
            circuit_name: Circuit breaker name
        """
        if circuit_name in self.circuit_breakers:
            self.circuit_breakers[circuit_name] = {
                "failures": 0,
                "last_failure": None,
                "open_until": None
            }
            logger.info(f"Circuit breaker {circuit_name} reset")

    def get_error_statistics(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get error statistics for the specified time period.

        Args:
            hours_back: How many hours back to analyze

        Returns:
            Error statistics
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)

        # Filter recent errors
        recent_errors = [
            record for record in self.error_records.values()
            if record.timestamp >= cutoff_time
        ]

        # Calculate statistics
        total_errors = len(recent_errors)
        severity_counts = {}
        category_counts = {}
        resolution_counts = {"resolved": 0, "unresolved": 0}

        for error in recent_errors:
            # Count by severity
            severity_counts[error.severity] = severity_counts.get(error.severity, 0) + 1

            # Count by category
            category_counts[error.category] = category_counts.get(error.category, 0) + 1

            # Count resolutions
            if error.resolved:
                resolution_counts["resolved"] += 1
            else:
                resolution_counts["unresolved"] += 1

        return {
            "analysis_period_hours": hours_back,
            "total_errors": total_errors,
            "severity_distribution": severity_counts,
            "category_distribution": category_counts,
            "resolution_distribution": resolution_counts,
            "resolution_rate": (resolution_counts["resolved"] / max(total_errors, 1)) * 100,
            "timestamp": datetime.utcnow().isoformat()
        }

    def export_error_report(self, output_path: str, hours_back: int = 168) -> str:
        """Export comprehensive error report.

        Args:
            output_path: Output file path
            hours_back: How many hours back to include (default: 1 week)

        Returns:
            Path to exported report
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)

        # Filter errors
        recent_errors = [
            record for record in self.error_records.values()
            if record.timestamp >= cutoff_time
        ]

        # Create comprehensive report
        report = {
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "tenant_id": self.tenant_id,
                "analysis_period_hours": hours_back,
                "total_errors": len(recent_errors)
            },
            "error_statistics": self.get_error_statistics(hours_back),
            "circuit_breaker_status": {
                name: self.get_circuit_breaker_status(name)
                for name in self.circuit_breakers.keys()
            },
            "error_details": [
                {
                    "error_id": record.error_id,
                    "timestamp": record.timestamp.isoformat(),
                    "severity": record.severity,
                    "category": record.category,
                    "message": record.message,
                    "exception_type": record.exception_type,
                    "context": {
                        "tenant_id": record.context.tenant_id,
                        "case_ref": record.context.case_ref,
                        "job_id": record.context.job_id,
                        "component": record.context.component,
                        "operation": record.context.operation
                    },
                    "recovery_attempts": record.recovery_attempts,
                    "resolved": record.resolved,
                    "resolution_timestamp": record.resolution_timestamp.isoformat() if record.resolution_timestamp else None
                }
                for record in sorted(recent_errors, key=lambda x: x.timestamp, reverse=True)
            ]
        }

        # Write report
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Error report exported to {output_file}")
        return str(output_file)

    # Internal methods
    def _convert_exception(self, error: Exception, context: ErrorContext = None) -> CaseGuardError:
        """Convert standard exception to CaseGuardError."""
        # Determine category and severity based on exception type
        category = ErrorCategory.UNKNOWN_ERROR
        severity = ErrorSeverity.MEDIUM
        recovery_action = RecoveryAction.ESCALATE

        if isinstance(error, (ConnectionError, TimeoutError)):
            category = ErrorCategory.NETWORK_ERROR
            recovery_action = RecoveryAction.RETRY
        elif isinstance(error, ValueError):
            category = ErrorCategory.VALIDATION_ERROR
            severity = ErrorSeverity.LOW
        elif isinstance(error, PermissionError):
            category = ErrorCategory.AUTHENTICATION_ERROR
            severity = ErrorSeverity.HIGH
        elif "database" in str(error).lower() or "sql" in str(error).lower():
            category = ErrorCategory.DATABASE_ERROR
            recovery_action = RecoveryAction.RETRY
        elif "api" in str(error).lower():
            category = ErrorCategory.API_ERROR
            recovery_action = RecoveryAction.RETRY

        return CaseGuardError(
            message=str(error),
            severity=severity,
            category=category,
            context=context,
            recovery_action=recovery_action,
            original_exception=error
        )

    def _create_error_record(self, error: CaseGuardError) -> ErrorRecord:
        """Create error record from CaseGuardError."""
        import uuid

        return ErrorRecord(
            error_id=str(uuid.uuid4()),
            timestamp=error.timestamp,
            severity=error.severity,
            category=error.category,
            message=error.message,
            exception_type=type(error.original_exception).__name__ if error.original_exception else type(error).__name__,
            traceback_str=traceback.format_exc(),
            context=error.context,
            recovery_action=error.recovery_action
        )

    def _log_error(self, error_record: ErrorRecord):
        """Log error with appropriate level."""
        log_message = (
            f"[{error_record.error_id}] {error_record.category}: {error_record.message}"
        )

        if error_record.context.tenant_id:
            log_message = f"[tenant:{error_record.context.tenant_id}] {log_message}"

        if error_record.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error_record.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error_record.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)

    def _notify_error_listeners(self, error_record: ErrorRecord):
        """Notify all registered error listeners."""
        for listener in self.error_listeners:
            try:
                listener(error_record)
            except Exception as e:
                logger.error(f"Error listener failed: {e}")

    def _attempt_recovery(self, error_record: ErrorRecord):
        """Attempt error recovery based on strategy."""
        strategy = self.recovery_strategies.get(
            error_record.category,
            self.recovery_strategies.get(ErrorCategory.UNKNOWN_ERROR)
        )

        if not strategy:
            return

        if error_record.recovery_action == RecoveryAction.RETRY:
            self._handle_retry_recovery(error_record, strategy)
        elif error_record.recovery_action == RecoveryAction.CIRCUIT_BREAKER:
            self._handle_circuit_breaker(error_record, strategy)
        elif error_record.recovery_action == RecoveryAction.FALLBACK:
            self._handle_fallback_recovery(error_record)

    def _handle_retry_recovery(self, error_record: ErrorRecord, strategy: RecoveryStrategy):
        """Handle retry-based recovery."""
        if error_record.recovery_attempts < strategy.max_retries:
            error_record.recovery_attempts += 1
            logger.info(f"Scheduling retry {error_record.recovery_attempts}/{strategy.max_retries} for error {error_record.error_id}")

    def _handle_circuit_breaker(self, error_record: ErrorRecord, strategy: RecoveryStrategy):
        """Handle circuit breaker logic."""
        circuit_name = error_record.context.component or "default"

        if circuit_name not in self.circuit_breakers:
            self.circuit_breakers[circuit_name] = {
                "failures": 0,
                "threshold": strategy.circuit_breaker_threshold,
                "timeout": strategy.circuit_breaker_timeout
            }

        breaker = self.circuit_breakers[circuit_name]
        breaker["failures"] += 1
        breaker["last_failure"] = datetime.utcnow()

        if breaker["failures"] >= breaker["threshold"]:
            breaker["open_until"] = datetime.utcnow() + timedelta(seconds=breaker["timeout"])
            logger.warning(f"Circuit breaker {circuit_name} opened due to {breaker['failures']} failures")

    def _handle_fallback_recovery(self, error_record: ErrorRecord):
        """Handle fallback recovery."""
        logger.info(f"Attempting fallback recovery for error {error_record.error_id}")
        # Fallback logic would be implemented here

    def _setup_default_strategies(self):
        """Setup default recovery strategies for each error category."""
        self.recovery_strategies = {
            ErrorCategory.API_ERROR: RecoveryStrategy(
                max_retries=3,
                retry_delay_seconds=2.0,
                exponential_backoff=True,
                circuit_breaker_threshold=5
            ),
            ErrorCategory.DATABASE_ERROR: RecoveryStrategy(
                max_retries=5,
                retry_delay_seconds=1.0,
                exponential_backoff=True,
                circuit_breaker_threshold=10
            ),
            ErrorCategory.NETWORK_ERROR: RecoveryStrategy(
                max_retries=3,
                retry_delay_seconds=5.0,
                exponential_backoff=True,
                circuit_breaker_threshold=3
            ),
            ErrorCategory.PROCESSING_ERROR: RecoveryStrategy(
                max_retries=2,
                retry_delay_seconds=1.0,
                fallback_enabled=True
            ),
            ErrorCategory.RATE_LIMIT_ERROR: RecoveryStrategy(
                max_retries=5,
                retry_delay_seconds=60.0,
                exponential_backoff=False,
                circuit_breaker_threshold=2
            ),
            ErrorCategory.UNKNOWN_ERROR: RecoveryStrategy(
                max_retries=1,
                retry_delay_seconds=1.0,
                fallback_enabled=False
            )
        }


# Global error handler instance
_global_error_handler = None


def get_global_error_handler(tenant_id: str = None) -> ErrorHandler:
    """Get global error handler instance.

    Args:
        tenant_id: Optional tenant ID

    Returns:
        Global ErrorHandler instance
    """
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler(tenant_id=tenant_id)
    return _global_error_handler


def handle_error(
    error: Union[Exception, CaseGuardError],
    context: ErrorContext = None,
    tenant_id: str = None
) -> ErrorRecord:
    """Global error handling function.

    Args:
        error: Error to handle
        context: Error context
        tenant_id: Optional tenant ID

    Returns:
        Error record
    """
    handler = get_global_error_handler(tenant_id)
    return handler.handle_error(error, context)


@contextmanager
def error_context(context: ErrorContext, tenant_id: str = None):
    """Global error context manager.

    Args:
        context: Error context
        tenant_id: Optional tenant ID
    """
    handler = get_global_error_handler(tenant_id)
    with handler.error_context(context):
        yield