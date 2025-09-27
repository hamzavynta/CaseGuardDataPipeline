# Technical Implementation Guide: CaseGuard Data Pipeline Components

**Generated**: 2025-09-27T03:01:28+00:00
**Researcher**: hamza
**Git Commit**: 77a58925b88a478d1dc52df9aee4303d4fdbd7cb
**Repository**: EmbeddingPipeline

This document provides complete implementation details with exact code examples for three critical components of the CaseGuard data pipeline.

## Table of Contents

1. [SOAP Document Downloader](#soap-document-downloader)
2. [DigitalOcean Spaces Integration](#digitalocean-spaces-integration)
3. [Canonical Field Mapping Configuration](#canonical-field-mapping-configuration)

---

## SOAP Document Downloader

### Overview

The SOAP Document Downloader handles binary-safe document retrieval from Proclaim's SOAP API using the `proGetDocument` service method.

### File Location

`caseguard/proclaim/soap_downloader.py`

### Complete Implementation

```python
"""SOAP document downloader for Proclaim (binary-safe).

Uses zeep with a local WSDL and the Proclaim SOAP endpoint to call proGetDocument.
Intended to run with a valid REST session token (csessionid) obtained from ProclaimClient.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from zeep import Client, Settings
from zeep.transports import Transport

logger = logging.getLogger(__name__)

# Comprehensive format-to-MIME type mapping
FORMAT_TO_MIME = {
    # Word processors
    "WORD-DOC": "application/msword",
    "WORD-DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "WORD-RTF": "application/rtf",
    "TEXT-RTF": "application/rtf",
    # PDF
    "ACROBAT-PDF": "application/pdf",
    # Images
    "IMAGE-JPG": "image/jpeg",
    "IMAGE-JPEG": "image/jpeg",
    "IMAGE-PNG": "image/png",
    "IMAGE-GIF": "image/gif",
    "IMAGE-BMP": "image/bmp",
    "IMAGE-TIF": "image/tiff",
    "IMAGE-TIFF": "image/tiff",
    # Spreadsheets
    "EXCEL-XLS": "application/vnd.ms-excel",
    "EXCEL-XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Presentations
    "POWERPOINT-PPT": "application/vnd.ms-powerpoint",
    "POWERPOINT-PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Emails / messages
    "EMAIL-EML": "message/rfc822",
    "EMAIL-MSG": "application/vnd.ms-outlook",
    # Plain text
    "TEXT-PLAIN": "text/plain",
}

# Direct extension mapping for formats that don't map cleanly
FORMAT_TO_EXT = {
    "WORD-RTF": ".rtf",
    "TEXT-RTF": ".rtf",
    "EMAIL-EML": ".eml",
    "EMAIL-MSG": ".msg",
    "IMAGE-TIF": ".tif",
    "IMAGE-TIFF": ".tiff",
}


class ProclaimSoapDownloader:
    """Initialize SOAP client and fetch documents by code/format."""

    def __init__(self, wsdl_path: str, soap_endpoint: str, timeout_seconds: int = 90) -> None:
        """Initialize SOAP client with zeep.

        Args:
            wsdl_path: Path to Proclaim.wsdl file
            soap_endpoint: SOAP endpoint URL (typically base_url + "/soap/")
            timeout_seconds: Request timeout (default: 90 seconds)
        """
        settings = Settings(strict=False, xml_huge_tree=True)
        transport = Transport(timeout=timeout_seconds)
        self.client = Client(wsdl_path, settings=settings, transport=transport)
        self.client.service._binding_options["address"] = soap_endpoint

    def fetch_document(
        self, token: str, document_code: str, document_format: str
    ) -> Tuple[Optional[Path], Optional[str]]:
        """Fetch a document and write to a temporary file.

        Args:
            token: Valid REST session token from ProclaimClient
            document_code: Document code from case history
            document_format: Document format (e.g., "ACROBAT-PDF", "WORD-DOC")

        Returns:
            Tuple of (temp_file_path, error_message).
            Path is None if failed. Error is None on success.
        """
        try:
            # Call SOAP service method
            result = self.client.service.proGetDocument(
                csessionid=token,
                cdocumentcode=document_code,
                cdocumentformat=document_format
            )

            # Validate response structure
            if not result or result.cstatus != "OK" or not result.ttFile or not result.ttFile.ttFileRow:
                return None, getattr(result, "cerror", "UNKNOWN_ERROR")

            # Extract binary content (zeep automatically decodes base64)
            content: bytes = result.ttFile.ttFileRow[0].filedata

            # Determine file extension
            filename = getattr(result, "curlfilename", None)
            ext = None
            if filename and isinstance(filename, str):
                _, ext = os.path.splitext(filename)

            if not ext:
                # Use format mapping to determine MIME type and extension
                mime = FORMAT_TO_MIME.get((document_format or "").upper(), "application/octet-stream")
                ext = mimetypes.guess_extension(mime)
                if not ext or ext == ".bin":
                    # Fallback to explicit extension mapping
                    ext = FORMAT_TO_EXT.get((document_format or "").upper()) or ".bin"

            # Create temporary file with appropriate extension
            tmp_dir = Path(tempfile.mkdtemp(prefix="caseguard_doc_"))
            tmp_path = tmp_dir / f"{document_code}{ext}"

            # Write binary content to file
            with open(tmp_path, "wb") as f:
                f.write(content)

            return tmp_path, None

        except Exception as e:
            logger.error(f"SOAP fetch failed for {document_code}: {e}")
            return None, str(e)
```

### Usage Example

```python
from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader

# Initialize downloader
downloader = ProclaimSoapDownloader(
    wsdl_path="Proclaim.wsdl",
    soap_endpoint="https://your-proclaim-server.com/soap/"
)

# Fetch document with session token
document_path, error = downloader.fetch_document(
    token="your_session_token",
    document_code="DOC123456",
    document_format="ACROBAT-PDF"
)

if document_path:
    print(f"Document saved to: {document_path}")
    # Process the document...
    # Clean up when done
    document_path.unlink()
    document_path.parent.rmdir()
else:
    print(f"Download failed: {error}")
```

### Key Features

1. **Binary Safety**: Uses zeep for proper base64 decoding
2. **Format Detection**: Comprehensive MIME type and extension mapping
3. **Error Handling**: Graceful failure with detailed error messages
4. **Temporary Files**: Isolated temporary directory creation
5. **Session Token Reuse**: Uses existing REST session for SOAP calls

---

## DigitalOcean Spaces Integration

### Overview

DigitalOcean Spaces integration provides S3-compatible object storage for documents and processed text with comprehensive CRUD operations.

### File Location

`caseguard/storage/spaces.py`

### Complete Implementation

```python
"""DigitalOcean Spaces client (private storage, S3-compatible).

Relies on system-wide AWS CLI credentials for authentication by default.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)


@dataclass
class SpacesLocation:
    """Represents a location in DigitalOcean Spaces."""
    bucket: str
    object_key: str
    region: str


class SpacesClient:
    """Thin wrapper around boto3 S3 client configured for DigitalOcean Spaces."""

    def __init__(self, bucket: str, region: str, endpoint_url: str, profile: Optional[str] = None) -> None:
        """Initialize Spaces client.

        Args:
            bucket: DigitalOcean Spaces bucket name
            region: DigitalOcean region (e.g., "nyc3", "ams3", "sgp1")
            endpoint_url: Full endpoint URL (e.g., "https://nyc3.digitaloceanspaces.com")
            profile: Optional AWS profile name for credentials
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.profile = profile

        # Initialize boto3 session with optional profile
        session_kwargs = {}
        if self.profile:
            try:
                session_kwargs["profile_name"] = self.profile
            except Exception:
                pass

        session = boto3.Session(**session_kwargs)

        # Configure S3 client for DigitalOcean Spaces
        self._s3 = session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            config=BotoConfig(s3={"addressing_style": "path"}),  # Required for Spaces
        )

    def upload_file(
        self,
        local_path: str | Path,
        object_key: str,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
    ) -> SpacesLocation:
        """Upload a local file to Spaces at the given object key (private).

        Args:
            local_path: Path to local file
            object_key: Object key in Spaces (e.g., "tenant/documents/raw/case123/doc.pdf")
            content_type: MIME type (auto-detected if not provided)
            cache_control: Cache control header

        Returns:
            SpacesLocation object with upload details
        """
        local_path = Path(local_path)

        # Auto-detect content type if not provided
        if not content_type:
            guessed, _ = mimetypes.guess_type(str(local_path))
            content_type = guessed or "application/octet-stream"

        # Prepare extra arguments
        extra_args = {"ContentType": content_type}
        if cache_control:
            extra_args["CacheControl"] = cache_control

        logger.info(f"Uploading to Spaces: s3://{self.bucket}/{object_key} ({content_type})")

        try:
            self._s3.upload_file(str(local_path), self.bucket, object_key, ExtraArgs=extra_args)
            logger.info(f"Uploaded: s3://{self.bucket}/{object_key}")
            return SpacesLocation(bucket=self.bucket, object_key=object_key, region=self.region)
        except Exception as e:
            logger.error(f"Spaces upload failed for s3://{self.bucket}/{object_key}: {e}")
            raise

    def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
    ) -> SpacesLocation:
        """Upload raw bytes to Spaces without creating a local file.

        Args:
            data: Binary data to upload
            object_key: Object key in Spaces
            content_type: MIME type (defaults to "application/octet-stream")
            cache_control: Cache control header

        Returns:
            SpacesLocation object with upload details
        """
        if not content_type:
            content_type = "application/octet-stream"

        extra_args = {"ContentType": content_type}
        if cache_control:
            extra_args["CacheControl"] = cache_control

        try:
            self._s3.put_object(Bucket=self.bucket, Key=object_key, Body=data, **extra_args)
            logger.info(f"Uploaded (bytes): s3://{self.bucket}/{object_key}")
            return SpacesLocation(bucket=self.bucket, object_key=object_key, region=self.region)
        except Exception as e:
            logger.error(f"Spaces byte upload failed for s3://{self.bucket}/{object_key}: {e}")
            raise

    def upload_text(
        self,
        text: str,
        object_key: str,
        content_type: str = "text/plain; charset=utf-8",
        cache_control: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> SpacesLocation:
        """Convenience helper to upload text content as UTF-8 bytes.

        Args:
            text: Text content to upload
            object_key: Object key in Spaces
            content_type: MIME type (defaults to "text/plain; charset=utf-8")
            cache_control: Cache control header
            encoding: Text encoding (defaults to "utf-8")

        Returns:
            SpacesLocation object with upload details
        """
        data = text.encode(encoding)
        return self.upload_bytes(data, object_key, content_type=content_type, cache_control=cache_control)

    def object_exists(self, object_key: str) -> bool:
        """Check if an object exists in Spaces.

        Args:
            object_key: Object key to check

        Returns:
            True if object exists, False otherwise
        """
        try:
            self._s3.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except Exception:
            return False

    def generate_presigned_url(self, object_key: str, expires_in_seconds: int = 900) -> str:
        """Generate a short-lived pre-signed URL for private access.

        Args:
            object_key: Object key in Spaces
            expires_in_seconds: URL expiration time (default: 15 minutes)

        Returns:
            Pre-signed URL string
        """
        return self._s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_in_seconds,
        )

    def list_objects(self, prefix: str) -> list[dict]:
        """List objects under a given prefix, returning dicts with at least Key and LastModified.

        Args:
            prefix: Object key prefix to filter by

        Returns:
            List of object dictionaries sorted by LastModified ascending
        """
        try:
            paginator = self._s3.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=self.bucket, Prefix=prefix)

            objects: list[dict] = []
            for page in page_iterator:
                contents = page.get('Contents') or []
                for obj in contents:
                    objects.append({
                        'Key': obj['Key'],
                        'LastModified': obj.get('LastModified')
                    })

            # Sort by LastModified ascending (None last)
            objects.sort(key=lambda o: o.get('LastModified') or 0)
            return objects

        except Exception as e:
            logger.error(f"Failed to list objects for prefix {prefix}: {e}")
            return []

    def download_object(self, object_key: str, dest_path: str | Path) -> Path:
        """Download a single object to a local path and return the path.

        Args:
            object_key: Object key in Spaces
            dest_path: Local destination path

        Returns:
            Path object of downloaded file
        """
        try:
            dest = Path(dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._s3.download_file(self.bucket, object_key, str(dest))
            logger.info(f"Downloaded s3://{self.bucket}/{object_key} -> {dest}")
            return dest
        except Exception as e:
            logger.error(f"Failed to download s3://{self.bucket}/{object_key}: {e}")
            raise

    def get_object_text(self, object_key: str, encoding: str = 'utf-8') -> str:
        """Read object content as text.

        Args:
            object_key: Object key in Spaces
            encoding: Text encoding (default: utf-8)

        Returns:
            Object content as string
        """
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=object_key)
            data = resp['Body'].read()
            return data.decode(encoding)
        except Exception as e:
            logger.error(f"Failed to read s3://{self.bucket}/{object_key} as text: {e}")
            raise
```

### Object Key Hierarchy

The system uses a consistent tenant-based key naming strategy:

```
{tenant_id}/
├── documents/
│   ├── raw/{case_ref}/{filename}              # Raw document files from Proclaim
│   └── processed_text/{case_ref}/{doc_code}.txt  # Processed text versions
└── dossiers/
    └── raw_dossiers_{timestamp}.json          # Case metadata snapshots
```

### Usage Example

```python
from caseguard.storage.spaces import SpacesClient

# Initialize client
spaces = SpacesClient(
    bucket="caseguard-documents",
    region="nyc3",
    endpoint_url="https://nyc3.digitaloceanspaces.com",
    profile="digitalocean"  # Optional AWS profile
)

# Upload a document
location = spaces.upload_file(
    local_path="/tmp/document.pdf",
    object_key="fdm_solicitors/documents/raw/NBC123456.001/document.pdf"
)
print(f"Uploaded to: {location.object_key}")

# Upload processed text
text_location = spaces.upload_text(
    text="Processed document content...",
    object_key="fdm_solicitors/documents/processed_text/NBC123456.001/DOC123.txt"
)

# Generate pre-signed URL for agent access
url = spaces.generate_presigned_url(
    object_key=location.object_key,
    expires_in_seconds=3600  # 1 hour
)

# Check if object exists
exists = spaces.object_exists(location.object_key)

# List objects with prefix
docs = spaces.list_objects("fdm_solicitors/documents/raw/NBC123456.001/")
```

### Environment Configuration

```bash
# Required environment variables
SPACES_BUCKET=caseguard-documents
SPACES_REGION=nyc3
SPACES_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com
SPACES_PROFILE=digitalocean  # Optional

# AWS credentials (via AWS CLI or environment)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

### Integration with Data Pipeline

```python
# From caseguard/main.py:608-625
def _fetch_and_process_documents(self, case: CaseData) -> None:
    """Document processing with Spaces integration."""
    for doc in case.document_manifest:
        # Download document via SOAP
        tmp_path, err = self.soap_downloader.fetch_document(token, code, fmt)

        # Process text with LlamaParse
        text = self.llamaparse.convert_to_text(tmp_path)

        if text and text.strip():
            # Store raw document
            raw_key = f"fdm_solicitors/documents/raw/{case.case_ref}/{tmp_path.name}"
            raw_location = self.spaces.upload_file(tmp_path, raw_key)

            # Store processed text
            proc_key = f"fdm_solicitors/documents/processed_text/{case.case_ref}/{code}.txt"
            proc_location = self.spaces.upload_text(text, proc_key)

            # Update document manifest with storage reference
            doc.file_path = raw_location.object_key
```

---

## Canonical Field Mapping Configuration

### Overview

The canonical field mapping system provides a configuration-driven approach to extract standardized fields from Proclaim API, supporting global fields, HDR-specific fields, and fallback mechanisms.

### File Location

`config/canonical_fields_corrected.json`

### Configuration Structure

```json
{
  "version": "2.0.0",
  "last_updated": "2025-01-07",
  "test_accuracy": "100%",
  "description": "Corrected canonical field mappings based on comprehensive Proclaim API testing",
  "endpoint_format": "/rest/ProclaimCaseService/Data/<case>/<field>?CaseType=<type>",

  "global_fields": {
    "description": "Fields that work without any prefix across all case types",
    "prefix": "",
    "count": 10,
    "fields": {
      "case_ref": {
        "proclaim_field": "case.key",
        "data_type": "string",
        "category": "core_metadata",
        "status": "working",
        "sample_value": "NBC204874.001"
      },
      "handler_name": {
        "proclaim_field": "Fee Earner.Description",
        "data_type": "string",
        "category": "core_metadata",
        "status": "working",
        "sample_value": "Ellie Braiden"
      },
      "date_opened": {
        "proclaim_field": "File Opened.Date",
        "data_type": "date",
        "category": "timeline",
        "status": "working",
        "sample_value": "18/09/2024"
      },
      "profit_costs_incurred": {
        "proclaim_field": "WIP Total.Value",
        "data_type": "currency",
        "category": "financial",
        "status": "working",
        "sample_value": "4,781.40"
      },
      "claimant_name": {
        "proclaim_field": "Client (global).Full Name/Company Name",
        "data_type": "string",
        "category": "parties",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "defendant_name": {
        "proclaim_field": "Landlord.Full Name/Company Name",
        "data_type": "string",
        "category": "parties",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "defendant_solicitor_firm": {
        "proclaim_field": "Defendant Solicitor.Full Name/Company Name",
        "data_type": "string",
        "category": "parties",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "property_address_full": {
        "proclaim_field": "Client (global).DX/Address block with commas",
        "data_type": "string",
        "category": "property",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "date_closed": {
        "proclaim_field": "File Closure Requested.Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "case_closed",
        "status": "working",
        "sample_value": "28/02/2025"
      },
      "date_loc_sent": {
        "proclaim_field": "LOC Sent Date.Full Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "letter_of_claim",
        "status": "working",
        "sample_value": "4th October 2024",
        "success_rate": "100%"
      }
    }
  },

  "hdr_fields": {
    "description": "HDR-specific fields that require 'HDR Link.' prefix",
    "prefix": "HDR Link.",
    "count": 17,
    "fields": {
      "case_status": {
        "proclaim_field": "Case Status.Desc",
        "data_type": "string",
        "category": "core_metadata",
        "status": "working",
        "sample_value": "Closure Checklist Complete"
      },
      "case_outcome": {
        "proclaim_field": "File Closed Reason.Desc",
        "data_type": "string",
        "category": "core_metadata",
        "status": "working",
        "sample_value": "Settled"
      },
      "property_address_postcode": {
        "proclaim_field": "Client (global).Postcode",
        "data_type": "string",
        "category": "property",
        "status": "working",
        "sample_value": "PO8 8BT"
      },
      "date_landlord_response_due": {
        "proclaim_field": "LOC Response Due Date.Full Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "landlord_response_due",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "date_landlord_response_received": {
        "proclaim_field": "LOC Response 63 Received Date.Full Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "landlord_response",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "date_expert_inspection": {
        "proclaim_field": "Surveyor Inspection Date.Full Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "expert_inspection",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "date_proceedings_issued": {
        "proclaim_field": "Litigation - Issued to Court.Full Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "proceedings_issued",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "date_trial_listed": {
        "proclaim_field": "Litigation - Hearing Date.Full Date",
        "data_type": "date",
        "category": "timeline_critical",
        "hdr_protocol_stage": "trial_listed",
        "status": "working",
        "sample_value": "[Empty]"
      },
      "damages_estimate_general": {
        "proclaim_field": "Quantum - P36 - General Damages.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "0.00"
      },
      "damages_estimate_special": {
        "proclaim_field": "Special Damages - Cost.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "0.00"
      },
      "disbursements_incurred": {
        "proclaim_field": "Disbursements Total.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "0.00"
      },
      "part36_offer_made_value": {
        "proclaim_field": "Offers - Latest Counter Offer Made Value.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "400.00"
      },
      "part36_offer_made_date": {
        "proclaim_field": "Offers - Latest Counter Offer Made Date.Date",
        "data_type": "date",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "13/02/2025"
      },
      "part36_offer_received_value": {
        "proclaim_field": "Offers - Latest Counter Offer Received Value.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "200.00"
      },
      "part36_offer_received_date": {
        "proclaim_field": "Offers - Latest Counter Offer Received Date.Date",
        "data_type": "date",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "13/02/2025"
      },
      "final_damages_settlement": {
        "proclaim_field": "Settlement - Total Damages.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "200.00"
      },
      "final_costs_settlement": {
        "proclaim_field": "Settlement - Total Costs.Value",
        "data_type": "currency",
        "category": "financial_critical",
        "status": "working",
        "sample_value": "600.00"
      }
    }
  }
}
```

### Smart Field Retriever Implementation

**File Location**: `caseguard/hdr_timeline/smart_field_retriever.py`

```python
class SmartFieldRetriever:
    """Smart field retrieval with fallback mechanisms."""

    def __init__(self, canonical_fields_path: str, proclaim_client):
        """Initialize with canonical field configuration."""
        with open(canonical_fields_path, 'r') as f:
            config = json.load(f)

        # Separate field types for routing
        self.global_fields = config["global_fields"]["fields"]
        self.hdr_fields = config["hdr_fields"]["fields"]
        self.proclaim_client = proclaim_client

    def get_field(self, case_ref: str, canonical_field_name: str, case_type: str = "104"):
        """Retrieve canonical field with smart routing and fallbacks."""

        # Route to appropriate handler based on field type
        if canonical_field_name in self.global_fields:
            return self._get_global_field(case_ref, canonical_field_name, case_type)
        elif canonical_field_name in self.hdr_fields:
            return self._get_hdr_field(case_ref, canonical_field_name, case_type)
        else:
            return self._get_broken_field(case_ref, canonical_field_name, case_type)

    def _get_global_field(self, case_ref: str, field_name: str, case_type: str):
        """Retrieve global field (no prefix required)."""
        field_config = self.global_fields[field_name]
        proclaim_field = field_config["proclaim_field"]

        # Direct API call without prefix
        value, success, method = self._call_proclaim_api(case_ref, proclaim_field, case_type)

        if success and value:
            converted_value = self._convert_value(value, field_config["data_type"])
            return converted_value, True, "direct_global"

        # Fallback to party extraction for party fields
        if field_config["category"] == "parties":
            return self._get_party_field_fallback(case_ref, field_name)

        return value, success, method

    def _get_hdr_field(self, case_ref: str, field_name: str, case_type: str):
        """Retrieve HDR field (requires 'HDR Link.' prefix)."""
        field_config = self.hdr_fields[field_name]
        proclaim_field = field_config["proclaim_field"]

        # Add HDR Link prefix
        prefixed_field = f"HDR Link.{proclaim_field}"

        value, success, method = self._call_proclaim_api(case_ref, prefixed_field, case_type)

        if success and value:
            converted_value = self._convert_value(value, field_config["data_type"])
            return converted_value, True, "direct_hdr"

        return value, success, method

    def _call_proclaim_api(self, case_ref: str, field_name: str, case_type: str):
        """Make API call to Proclaim field endpoint."""
        try:
            # Transform field name: replace '/' with '.'
            transformed_field = field_name.replace('/', '.')

            # URL encode the field name (preserve dots)
            from urllib.parse import quote
            encoded_field = quote(transformed_field, safe='.')

            # Construct endpoint URL
            url = f"{self.proclaim_client.base_url}/rest/ProclaimCaseService/Data/{case_ref}/{encoded_field}"
            params = {"CaseType": case_type}

            # Make request
            response = requests.get(
                url,
                headers=self.proclaim_client._get_headers(),
                params=params,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            # Validate response
            if data.get('response', {}).get('cStatus') == 'OK':
                field_value = data.get('response', {}).get('cFieldValue')
                return field_value, True, "direct_api"
            else:
                error = data.get('response', {}).get('cError', 'Unknown error')
                return error, False, "api_error"

        except Exception as e:
            return str(e), False, "exception"

    def _convert_value(self, value: str, data_type: str):
        """Convert field value based on data type."""
        if not value or value == '[Empty]':
            return None

        if data_type == "date":
            return self._parse_date_string(value)
        elif data_type == "currency":
            # Remove commas and convert to float
            clean_value = value.replace(',', '')
            try:
                return float(clean_value)
            except ValueError:
                return None
        else:
            return value  # String - return as is

    def _parse_date_string(self, date_str: str):
        """Parse date from various Proclaim formats."""
        if not date_str:
            return None

        # Try multiple date formats
        date_formats = [
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%Y-%m-%d',
            '%d %B %Y',  # "4th October 2024"
            '%dst %B %Y', '%dnd %B %Y', '%drd %B %Y', '%dth %B %Y'
        ]

        # Clean ordinal suffixes for parsing
        cleaned_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

        for fmt in date_formats:
            try:
                return datetime.strptime(cleaned_date, fmt)
            except ValueError:
                continue

        return None

    def _get_party_field_fallback(self, case_ref: str, field_name: str):
        """Fallback: extract party information using corrtype matching."""
        try:
            # Get case data with parties
            case_data = self.proclaim_client.get_case_data(case_ref)
            if not case_data or not case_data.parties:
                return None, False, "no_parties"

            # Field name to corrtype mapping
            field_mappings = {
                "claimant_name": "cl",
                "defendant_name": "ll",
                "defendant_solicitor_firm": "dfs"
            }

            target_corrtype = field_mappings.get(field_name)
            if not target_corrtype:
                return None, False, "unmapped_field"

            # Find matching party
            for party in case_data.parties:
                if party.corrtype and party.corrtype.lower() == target_corrtype:
                    name = party.corrdesc or party.name
                    return name, True, "party_extraction"

            return None, False, "party_not_found"

        except Exception as e:
            return str(e), False, "party_extraction_error"
```

### HDR Protocol Stage Mapping

```python
# HDR Protocol stages with canonical field associations
HDR_PROTOCOL_STAGES = {
    "evidence_gathering": {
        "stage_number": 1,
        "day_range": [0, 7],
        "canonical_fields": ["date_opened"],
        "settlement_likelihood": 0.025
    },
    "letter_of_claim": {
        "stage_number": 3,
        "day_range": [30, 35],
        "canonical_fields": ["date_loc_sent"],
        "settlement_likelihood": 0.15
    },
    "landlord_response": {
        "stage_number": 4,
        "day_range": [50, 63],
        "canonical_fields": ["date_landlord_response_received", "date_landlord_response_due"],
        "settlement_likelihood": 0.35
    },
    "expert_inspection": {
        "stage_number": 5,
        "day_range": [70, 90],
        "canonical_fields": ["date_expert_inspection"],
        "settlement_likelihood": 0.55
    },
    "proceedings_issued": {
        "stage_number": 7,
        "day_range": [120, 150],
        "canonical_fields": ["date_proceedings_issued"],
        "settlement_likelihood": 0.75
    },
    "trial_listed": {
        "stage_number": 8,
        "day_range": [180, 365],
        "canonical_fields": ["date_trial_listed"],
        "settlement_likelihood": 0.85
    },
    "case_closed": {
        "stage_number": 9,
        "day_range": [1, 9999],
        "canonical_fields": ["date_closed"],
        "settlement_likelihood": 1.0
    }
}
```

### Extraction Methods Summary

1. **Direct Field Extraction**: 100% success rate using corrected field names
2. **Party Extraction**: Fallback using `corrtype` matching for party information
3. **History Pattern Matching**: Extract timeline dates from case history using regex

### Usage Example

```python
from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever

# Initialize retriever
retriever = SmartFieldRetriever(
    canonical_fields_path="config/canonical_fields_corrected.json",
    proclaim_client=proclaim_client
)

# Extract critical timeline fields
critical_fields = [
    "date_opened", "date_loc_sent", "date_landlord_response_received",
    "date_expert_inspection", "date_proceedings_issued", "date_closed"
]

case_timeline = {}
for field_name in critical_fields:
    value, success, method = retriever.get_field(
        case_ref="NBC123456.001",
        canonical_field_name=field_name,
        case_type="104"
    )

    if success and value:
        case_timeline[field_name] = {
            "value": value,
            "extraction_method": method
        }

print(f"Extracted {len(case_timeline)} timeline fields")
```

### Key Features

1. **100% Success Rate**: All 27 canonical fields tested and working
2. **Three-Tier Architecture**: Global fields, HDR fields, and fallback mechanisms
3. **Type-Aware Conversion**: Automatic data type conversion (date, currency, string)
4. **Smart Routing**: Automatic prefix application based on field type
5. **Fallback Mechanisms**: Party extraction and history pattern matching
6. **HDR Protocol Integration**: Direct mapping to legal protocol stages

---

## Integration Architecture

These three components work together in the CaseGuard data pipeline:

1. **Document Discovery**: Case history analysis identifies documents
2. **SOAP Download**: Binary documents retrieved via ProclaimSoapDownloader
3. **Text Processing**: LlamaParse extracts text from documents
4. **Spaces Storage**: Raw and processed documents stored with structured keys
5. **Field Extraction**: SmartFieldRetriever extracts canonical metadata
6. **Vector Generation**: Document content and metadata embedded with storage references
7. **Agent Citations**: Pinecone search results link back to original documents in Spaces

This creates a complete pipeline from Proclaim API data to searchable, citable document collections for AI agents.
