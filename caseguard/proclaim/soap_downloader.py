"""SOAP document downloader for Proclaim with binary-safe handling."""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from zeep import Client, Settings
from zeep.transports import Transport

logger = logging.getLogger(__name__)

# Format mappings from technical-details.md
FORMAT_TO_MIME = {
    "WORD-DOC": "application/msword",
    "ACROBAT-PDF": "application/pdf",
    "WORD-DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "EXCEL-XLS": "application/vnd.ms-excel",
    "EXCEL-XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "POWERPOINT-PPT": "application/vnd.ms-powerpoint",
    "POWERPOINT-PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "TEXT": "text/plain",
    "RTF": "application/rtf",
    "EMAIL-MSG": "application/vnd.ms-outlook",
    "EMAIL-EML": "message/rfc822",
    "IMAGE-JPEG": "image/jpeg",
    "IMAGE-PNG": "image/png",
    "IMAGE-TIFF": "image/tiff",
    "IMAGE-BMP": "image/bmp",
    "IMAGE-GIF": "image/gif",
    "HTML": "text/html",
    "XML": "application/xml",
    "ZIP": "application/zip",
    "RAR": "application/x-rar-compressed",
    "7Z": "application/x-7z-compressed",
    "TAR": "application/x-tar",
    "GZIP": "application/gzip"
}

EXTENSION_MAP = {
    "WORD-DOC": ".doc",
    "ACROBAT-PDF": ".pdf",
    "WORD-DOCX": ".docx",
    "EXCEL-XLS": ".xls",
    "EXCEL-XLSX": ".xlsx",
    "POWERPOINT-PPT": ".ppt",
    "POWERPOINT-PPTX": ".pptx",
    "TEXT": ".txt",
    "RTF": ".rtf",
    "EMAIL-MSG": ".msg",
    "EMAIL-EML": ".eml",
    "IMAGE-JPEG": ".jpg",
    "IMAGE-PNG": ".png",
    "IMAGE-TIFF": ".tiff",
    "IMAGE-BMP": ".bmp",
    "IMAGE-GIF": ".gif",
    "HTML": ".html",
    "XML": ".xml",
    "ZIP": ".zip",
    "RAR": ".rar",
    "7Z": ".7z",
    "TAR": ".tar",
    "GZIP": ".gz"
}


class ProclaimSoapDownloader:
    """SOAP document downloader with tenant context support."""

    def __init__(self, wsdl_path: str, soap_endpoint: str,
                 tenant_id: str = None, timeout_seconds: int = 90):
        """Initialize SOAP downloader.

        Args:
            wsdl_path: Path to WSDL file
            soap_endpoint: SOAP service endpoint URL
            tenant_id: Tenant identifier for context
            timeout_seconds: Request timeout
        """
        self.tenant_id = tenant_id
        self.timeout_seconds = timeout_seconds

        try:
            # Configure SOAP client with proper settings
            settings = Settings(strict=False, xml_huge_tree=True)
            transport = Transport(timeout=timeout_seconds)

            self.client = Client(wsdl_path, settings=settings, transport=transport)
            self.client.service._binding_options["address"] = soap_endpoint

            logger.info(f"SOAP client initialized for tenant {tenant_id}")

        except Exception as e:
            logger.error(f"Failed to initialize SOAP client: {e}")
            raise

    def fetch_document(self, token: str, document_code: str,
                      document_format: str) -> Tuple[Optional[Path], Optional[str]]:
        """Fetch document via SOAP with binary-safe handling.

        Args:
            token: Session token
            document_code: Document identifier
            document_format: Document format (e.g., 'ACROBAT-PDF')

        Returns:
            Tuple of (file_path, error_message)
        """
        try:
            logger.info(f"Fetching document {document_code} in format {document_format}")

            # Call SOAP service to get document
            response = self.client.service.GetDocument(
                sessionToken=token,
                documentCode=document_code,
                format=document_format
            )

            if not response or not hasattr(response, 'content'):
                return None, f"No content returned for document {document_code}"

            # Get binary content
            content = response.content
            if not content:
                return None, f"Empty content for document {document_code}"

            # Determine file extension
            extension = EXTENSION_MAP.get(document_format, '.bin')
            mime_type = FORMAT_TO_MIME.get(document_format, 'application/octet-stream')

            # Create temporary file with proper extension
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=extension,
                prefix=f"caseguard_doc_{document_code.replace('/', '_')}_"
            )

            try:
                # Write binary content to file
                temp_file.write(content)
                temp_file.flush()
                temp_path = Path(temp_file.name)

                logger.info(f"Document {document_code} saved to {temp_path}")
                return temp_path, None

            except Exception as e:
                logger.error(f"Failed to write document content: {e}")
                return None, str(e)

            finally:
                temp_file.close()

        except Exception as e:
            error_msg = f"SOAP document fetch failed for {document_code}: {e}"
            logger.error(error_msg)
            return None, error_msg

    def fetch_document_with_tenant_context(self, token: str, document_code: str,
                                         document_format: str) -> Tuple[Optional[Path], Optional[str]]:
        """Fetch document with tenant metadata for processing pipeline.

        Args:
            token: Session token
            document_code: Document identifier
            document_format: Document format

        Returns:
            Tuple of (file_path, error_message)
        """
        logger.debug(f"Fetching document for tenant {self.tenant_id}")
        return self.fetch_document(token, document_code, document_format)

    def get_document_info(self, token: str, document_code: str) -> Optional[Dict[str, Any]]:
        """Get document metadata without downloading the content.

        Args:
            token: Session token
            document_code: Document identifier

        Returns:
            Document metadata dictionary or None
        """
        try:
            response = self.client.service.GetDocumentInfo(
                sessionToken=token,
                documentCode=document_code
            )

            if response:
                return {
                    'document_code': document_code,
                    'available_formats': getattr(response, 'formats', []),
                    'size_bytes': getattr(response, 'size', 0),
                    'filename': getattr(response, 'filename', document_code),
                    'tenant_id': self.tenant_id
                }

        except Exception as e:
            logger.error(f"Failed to get document info for {document_code}: {e}")

        return None

    def check_document_availability(self, token: str, document_codes: List[str]) -> Dict[str, bool]:
        """Check availability of multiple documents.

        Args:
            token: Session token
            document_codes: List of document identifiers

        Returns:
            Dictionary mapping document_code to availability boolean
        """
        availability = {}

        for doc_code in document_codes:
            try:
                info = self.get_document_info(token, doc_code)
                availability[doc_code] = info is not None

            except Exception as e:
                logger.warning(f"Could not check availability for {doc_code}: {e}")
                availability[doc_code] = False

        return availability

    def cleanup_temp_files(self, file_paths: List[Path]) -> None:
        """Clean up temporary files created during document downloads.

        Args:
            file_paths: List of file paths to clean up
        """
        for file_path in file_paths:
            try:
                if file_path.exists():
                    os.unlink(file_path)
                    logger.debug(f"Cleaned up temp file: {file_path}")

            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path}: {e}")

    def get_supported_formats(self) -> Dict[str, str]:
        """Get mapping of supported document formats to MIME types.

        Returns:
            Dictionary mapping format names to MIME types
        """
        return FORMAT_TO_MIME.copy()