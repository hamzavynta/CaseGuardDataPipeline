"""Configurable document format filtering for tenant-specific processing."""

import logging
from typing import List, Set, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DocumentFormatConfig(BaseModel):
    """Configuration for document format processing."""

    # File extensions to process
    allowed_extensions: Set[str] = Field(
        default={
            '.pdf', '.doc', '.docx', '.txt', '.rtf',
            '.xls', '.xlsx', '.ppt', '.pptx',
            '.jpg', '.jpeg', '.png', '.tiff',
            '.eml', '.msg', '.zip'
        },
        description="Set of allowed file extensions for processing"
    )

    # File size limits
    max_file_size_mb: int = Field(
        default=50,
        description="Maximum file size in MB"
    )

    # V2 is LlamaParse-only (no Docling fallback)
    llamaparse_only: bool = Field(
        default=True,
        description="Use only LlamaParse for V2 architecture"
    )

    # Extensions to skip entirely
    skip_formats: Set[str] = Field(
        default={'.tmp', '.log', '.bak', '.cache', '.lock'},
        description="File extensions to skip entirely"
    )

    # Processing priority order
    processing_priority: Dict[str, List[str]] = Field(
        default={
            "high": [".pdf", ".doc", ".docx"],      # Legal documents
            "medium": [".eml", ".msg", ".txt"],      # Correspondence
            "low": [".xls", ".xlsx", ".ppt", ".pptx"], # Data files
            "archive": [".zip", ".rar"]              # Archives (special handling)
        },
        description="Processing priority groups"
    )

    # Content type detection
    mime_type_mapping: Dict[str, str] = Field(
        default={
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.rtf': 'text/rtf',
            '.eml': 'message/rfc822',
            '.msg': 'application/vnd.ms-outlook'
        },
        description="MIME type mapping for file extensions"
    )


class DocumentProcessor:
    """Configurable document processor with tenant-specific rules."""

    def __init__(self, tenant_config: Dict[str, Any] = None):
        """Initialize document processor with tenant configuration.

        Args:
            tenant_config: Tenant configuration dictionary
        """
        self.tenant_config = tenant_config or {}
        doc_config = self.tenant_config.get('document_config', {})

        # Create format configuration
        self.format_config = DocumentFormatConfig(**doc_config)

        logger.info(f"DocumentProcessor initialized with {len(self.format_config.allowed_extensions)} allowed formats")

    def should_process_document(self, filename: str, file_size_bytes: int = 0) -> Dict[str, Any]:
        """Check if document should be processed based on configuration.

        Args:
            filename: Document filename
            file_size_bytes: File size in bytes

        Returns:
            Decision dictionary with processing recommendation and metadata
        """
        file_path = Path(filename)
        ext = file_path.suffix.lower()
        size_mb = file_size_bytes / (1024 * 1024) if file_size_bytes > 0 else 0

        decision = {
            "should_process": False,
            "filename": filename,
            "extension": ext,
            "size_mb": size_mb,
            "priority": "skip",
            "reasons": [],
            "warnings": []
        }

        # Check skip formats first
        if ext in self.format_config.skip_formats:
            decision["reasons"].append(f"Extension {ext} in skip list")
            return decision

        # Check allowed extensions
        if ext not in self.format_config.allowed_extensions:
            decision["reasons"].append(f"Extension {ext} not in allowed list")
            return decision

        # Check file size
        if size_mb > self.format_config.max_file_size_mb:
            decision["reasons"].append(f"File size {size_mb:.1f}MB exceeds limit of {self.format_config.max_file_size_mb}MB")
            return decision

        # Determine processing priority
        priority = "low"  # default
        for priority_level, extensions in self.format_config.processing_priority.items():
            if ext in extensions:
                priority = priority_level
                break

        # Document passes all checks
        decision.update({
            "should_process": True,
            "priority": priority,
            "reasons": ["All checks passed"],
            "mime_type": self.format_config.mime_type_mapping.get(ext, "application/octet-stream")
        })

        # Add warnings for large files
        if size_mb > self.format_config.max_file_size_mb * 0.8:  # 80% of limit
            decision["warnings"].append(f"Large file: {size_mb:.1f}MB (near {self.format_config.max_file_size_mb}MB limit)")

        logger.debug(f"Processing decision for {filename}: {decision['should_process']} (priority: {priority})")
        return decision

    def process_with_llamaparse(self, document_path: str, **kwargs) -> Dict[str, Any]:
        """LlamaParse-only processing for V2 architecture.

        Args:
            document_path: Path to document file
            **kwargs: Additional LlamaParse arguments

        Returns:
            Processing result dictionary
        """
        try:
            from llama_parse import LlamaParse
            import os

            # Get LlamaParse configuration
            api_key = os.getenv('LLAMA_CLOUD_API_KEY') or os.getenv('LLAMAPARSE_API_KEY')
            if not api_key:
                raise ValueError("LlamaParse API key not found in environment")

            # Configure parser
            parser_config = {
                "api_key": api_key,
                "result_type": kwargs.get("result_type", "markdown"),
                "language": kwargs.get("language", "en"),
                "verbose": kwargs.get("verbose", False)
            }

            # Add any additional parser arguments
            parser_config.update(kwargs)

            parser = LlamaParse(**parser_config)

            logger.info(f"Processing document with LlamaParse: {document_path}")

            # Process document
            documents = parser.load_data(document_path)

            # Extract text content
            if not documents:
                return {
                    "success": False,
                    "error": "No content extracted from document",
                    "text": "",
                    "metadata": {}
                }

            # Combine text from all document parts
            combined_text = "\n\n".join(doc.text for doc in documents if hasattr(doc, 'text'))

            result = {
                "success": True,
                "text": combined_text,
                "text_length": len(combined_text),
                "document_count": len(documents),
                "metadata": {
                    "processor": "LlamaParse",
                    "result_type": parser_config["result_type"],
                    "language": parser_config["language"],
                    "processing_timestamp": logger.handlers[0].formatter.formatTime(logger.makeRecord("", 0, "", 0, "", (), None)) if logger.handlers else None
                }
            }

            logger.info(f"LlamaParse processing successful: {result['text_length']} characters extracted")
            return result

        except ImportError:
            error_msg = "LlamaParse not available - install llama-parse package"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "text": "",
                "metadata": {}
            }

        except Exception as e:
            error_msg = f"LlamaParse processing failed: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "text": "",
                "metadata": {"processor": "LlamaParse", "error_type": type(e).__name__}
            }

    def batch_process_documents(
        self,
        document_paths: List[str],
        max_concurrent: int = 4,
        **processing_kwargs
    ) -> List[Dict[str, Any]]:
        """Process multiple documents with rate limiting.

        Args:
            document_paths: List of document file paths
            max_concurrent: Maximum concurrent processing
            **processing_kwargs: Arguments to pass to document processor

        Returns:
            List of processing results
        """
        logger.info(f"Starting batch processing of {len(document_paths)} documents")

        results = []

        for i, doc_path in enumerate(document_paths):
            logger.info(f"Processing document {i+1}/{len(document_paths)}: {doc_path}")

            try:
                # Check if document should be processed
                file_size = Path(doc_path).stat().st_size if Path(doc_path).exists() else 0
                decision = self.should_process_document(doc_path, file_size)

                if not decision["should_process"]:
                    result = {
                        "document_path": doc_path,
                        "success": False,
                        "skipped": True,
                        "reasons": decision["reasons"],
                        "text": "",
                        "metadata": decision
                    }
                    results.append(result)
                    continue

                # Process document
                processing_result = self.process_with_llamaparse(doc_path, **processing_kwargs)
                processing_result["document_path"] = doc_path
                processing_result["skipped"] = False
                processing_result["priority"] = decision["priority"]

                results.append(processing_result)

                # Rate limiting between documents
                if (i + 1) % max_concurrent == 0 and i < len(document_paths) - 1:
                    import time
                    time.sleep(1)  # Brief pause every N documents

            except Exception as e:
                logger.error(f"Batch processing failed for {doc_path}: {e}")
                results.append({
                    "document_path": doc_path,
                    "success": False,
                    "skipped": False,
                    "error": str(e),
                    "text": "",
                    "metadata": {}
                })

        successful = sum(1 for r in results if r.get("success", False))
        skipped = sum(1 for r in results if r.get("skipped", False))
        failed = len(results) - successful - skipped

        logger.info(f"Batch processing complete: {successful} successful, {skipped} skipped, {failed} failed")

        return results

    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get processing statistics and configuration summary.

        Returns:
            Statistics dictionary
        """
        config = self.format_config

        return {
            "configuration": {
                "allowed_extensions": list(config.allowed_extensions),
                "max_file_size_mb": config.max_file_size_mb,
                "llamaparse_only": config.llamaparse_only,
                "skip_formats": list(config.skip_formats),
                "priority_groups": {
                    group: extensions for group, extensions in config.processing_priority.items()
                }
            },
            "capabilities": {
                "total_supported_formats": len(config.allowed_extensions),
                "high_priority_formats": len(config.processing_priority.get("high", [])),
                "mime_types_supported": len(config.mime_type_mapping)
            },
            "tenant_id": self.tenant_config.get("tenant_id", "unknown"),
            "processor_version": "v2.0",
            "processor_type": "LlamaParse-only"
        }


# Utility functions
def create_document_processor(tenant_config: Dict[str, Any] = None) -> DocumentProcessor:
    """Create a document processor with tenant configuration.

    Args:
        tenant_config: Tenant configuration dictionary

    Returns:
        Configured DocumentProcessor instance
    """
    return DocumentProcessor(tenant_config=tenant_config)


def validate_document_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate document processing configuration.

    Args:
        config: Document configuration to validate

    Returns:
        Validation results
    """
    validation = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "suggestions": []
    }

    try:
        # Test configuration creation
        format_config = DocumentFormatConfig(**config)

        # Check for common issues
        if format_config.max_file_size_mb > 100:
            validation["warnings"].append(f"Large max file size: {format_config.max_file_size_mb}MB may cause memory issues")

        if len(format_config.allowed_extensions) < 5:
            validation["warnings"].append("Limited file format support - consider adding more extensions")

        # Check for missing common formats
        common_formats = {'.pdf', '.doc', '.docx', '.txt'}
        missing_common = common_formats - format_config.allowed_extensions
        if missing_common:
            validation["suggestions"].append(f"Consider adding common formats: {', '.join(missing_common)}")

    except Exception as e:
        validation["valid"] = False
        validation["errors"].append(f"Configuration validation failed: {str(e)}")

    return validation