---
date: 2025-09-27T00:31:50+00:00
researcher: hamza
git_commit: 77a58925b88a478d1dc52df9aee4303d4fdbd7cb
branch: main
repository: EmbeddingPipeline
topic: "Proclaim API Implementation Details for Complete Case Data Extraction"
tags: [research, codebase, proclaim, api, case-detail-endpoint, session-management, canonical-fields, documents, history, timeline, digitalocean-spaces, vector-storage, agent-citations, data-pipeline]
status: complete
last_updated: 2025-09-27
last_updated_by: hamza
last_updated_note: "Added follow-up research for DigitalOcean Spaces integration and agent citation mechanisms"
---

# Research: Proclaim API Implementation Details for Complete Case Data Extraction

**Date**: 2025-09-27T00:31:50+00:00
**Researcher**: hamza
**Git Commit**: 77a58925b88a478d1dc52df9aee4303d4fdbd7cb
**Branch**: main
**Repository**: EmbeddingPipeline

## Research Question

Find all implementation details related to Proclaim API to get everything we need from cases: history, documents, and canonical fields. Generate research document to act as documentation for developers focusing on the critical dependencies: Proclaim API case detail endpoint (blocking requirement) and enhanced session management.

## Summary

The codebase implements a comprehensive Proclaim API integration using a hybrid REST/SOAP architecture with sophisticated session management, multi-tier field mapping, and robust document handling. The implementation provides complete case data extraction including history, documents, and canonical field mapping for HDR (Housing Disrepair) protocol analysis.

## Detailed Findings

### Proclaim API Case Detail Endpoint Implementation

**Primary Location**: `caseguard/proclaim/client.py:130`

The case detail endpoint functionality is implemented through multiple specialized API endpoints:

#### Core REST Endpoints

- **Case Validation**: `GET /rest/ProclaimCaseService/Validate/{case_ref}` (`client.py:140`)
  - Returns basic case validation and core details
  - Response structure: `response.cStatus`, `response.cSessionId`

- **Case History**: `GET /rest/ProclaimCaseService/Data/History/Dynamic/{case_ref}` (`client.py:167`)
  - Supports pagination via `MaxResults` parameter
  - Extended 60-second timeout for large history sets
  - Response structure: `response.hdsHistory.ProDataSet.ttHistory[]`

- **Party Data**: `GET /rest/ProclaimGeneralService/Correspondent/Case/{case_ref}` (`client.py:201`)
  - Enriched with correspondent type mappings (CL→Client, DFS→Defendant Solicitor)

- **Individual Fields**: `GET /rest/ProclaimCaseService/Data/{case_ref}/{field}` (`client.py:330`)
  - URL-encoded field names with smart prefix handling
  - Response validation checking `cStatus == "OK"`

#### Data Flow Architecture

1. Authentication → Session token extraction (`client.py:102`)
2. Case validation → Core details verification (`client.py:140`)
3. Parallel data retrieval:
   - History events with full field mapping (`extractor.py:148-230`)
   - Party/correspondent data with role enrichment (`client.py:191-228`)
   - Individual canonical fields via smart retrieval (`smart_field_retriever.py:53`)
4. Document metadata extraction from history (`client.py:230-269`)
5. Data structure assembly in `CaseExtractor` (`extractor.py:30-73`)

### Session Management Implementation

**Primary Location**: `caseguard/proclaim/client.py:81-117`

#### Token-Based Authentication System

- **Authentication Method**: HTTP Basic Auth with Base64 encoding (`client.py:84-87`)
- **Session Endpoint**: `/rest/ProclaimStandardService/Logon` (`client.py:93`)
- **Token Format**: `PROCLAIM-TOKEN {token}` in Authorization headers (`client.py:128`)
- **Logout Endpoint**: `/rest/ProclaimStandardService/Logout` (`client.py:362`)

#### Session Persistence & Cleanup

- **Session Storage**: `~/.caseguard/proclaim_session.json` (`session_manager.py:13`)
- **Automatic Cleanup**: `atexit` and signal handlers (`client.py:52-65`)
- **Process Tracking**: Session file includes PID for debugging (`session_manager.py:41`)
- **Force Cleanup Utility**: `scripts/force_cleanup_proclaim_session.py:119`

#### Timeout Configuration

- Default REST timeout: 30 seconds
- History endpoint timeout: 60 seconds
- SOAP timeout: 90 seconds
- Request delay: 500ms between SOAP calls

### Document Handling Implementation

**Primary Location**: `caseguard/proclaim/soap_downloader.py:71-107`

#### Document Metadata Extraction

Documents are discovered through history event analysis (`client.py:230-269`):

- Extracts document references from case history events
- Filters out system actions (MO, TC, MC) that aren't real documents
- Validates meaningful document codes and formats
- Returns structured metadata for further processing

#### SOAP Document Downloads

- **SOAP Method**: `proGetDocument(csessionid, cdocumentcode, cdocumentformat)` (`soap_downloader.py:79`)
- **WSDL Definition**: `Proclaim.wsdl` file provides service specification
- **Binary Safety**: Base64 decoding handled automatically by zeep library
- **File Extensions**: Comprehensive format-to-MIME-type mapping (`soap_downloader.py:22-49`)

#### Document Processing Pipeline

1. History-based document discovery (`client.py:241`)
2. SOAP download with format validation (`soap_downloader.py:86`)
3. Multi-processor text extraction (LlamaParse + Docling fallback) (`main.py:195-250`)
4. Cloud storage upload to DigitalOcean Spaces (`storage/spaces.py:51-76`)
5. Only processable documents are stored to avoid unprocessable file accumulation

### Canonical Field Mapping Implementation

**Primary Location**: `config/canonical_fields_corrected.json`

#### Three-Tier Field Architecture

- **Global Fields** (no prefix): 10 core fields including `case_ref`, `handler_name`, `date_opened`
- **HDR Fields** ("HDR Link." prefix): 17 specialized timeline/financial fields
- **Fixed Fields**: Previously broken fields with correction methodology

#### Smart Field Retrieval System (`smart_field_retriever.py`)

- **Field Resolution**: Routes to appropriate handler based on field type (`get_field:66-76`)
- **API Translation**: Applies prefixes and URL encoding (`_call_proclaim_api:244-251`)
- **Type Conversion**: Date parsing, currency conversion, string normalization (`_convert_value:274-302`)
- **Fallback Mechanisms**: Party extraction, history pattern matching for failed direct access

#### Autonomous Field Discovery (`scripts/agent_map_hdr_fields.py`)

- **LangGraph Agent**: Pinecone vector search + LLM re-ranking for new field discovery
- **Type Validation**: Live API testing with sample value collection
- **Rate Limiting**: 0.25 QPS to prevent API overload

### History/Timeline Data Extraction

**Primary Location**: `caseguard/proclaim/extractor.py:148-230`

#### Comprehensive Event Mapping

- **Full Field Extraction**: Maps all 60+ Proclaim history fields including cost tracking, email data
- **Data Structures**: Uses comprehensive `HistoryEvent` model (`models/case_data.py:46-164`)
- **Chronological Ordering**: Sorts by sequence number for proper timeline analysis

#### Enhanced Timeline Pattern Matching (`test_hdr_timeline.py:179-236`)

- **Multi-Pattern Matching**: Combines text patterns with Proclaim action/correspondent codes
- **Glossary Integration**: Uses domain-specific legal protocol knowledge
- **Milestone Detection**: Letter of Claim, landlord response, expert inspection, proceedings issued
- **Confidence Levels**: Strong vs moderate pattern confidence with configurable thresholds

#### Bulk Processing Support (`proclaim_bulk_extractor.py`)

- **Concurrent Processing**: ThreadPoolExecutor for field-level concurrency
- **Retry Logic**: Exponential backoff with jitter for resilience
- **Progress Persistence**: Pickle-based progress saving for interruption recovery
- **Performance Monitoring**: Rolling metrics with ETA calculation

## Code References

- `caseguard/proclaim/client.py:19` - ProclaimClient main class
- `caseguard/proclaim/client.py:130` - get_case_data() method
- `caseguard/proclaim/client.py:156` - get_case_history() with pagination
- `caseguard/proclaim/extractor.py:30` - extract_case() orchestration
- `caseguard/proclaim/soap_downloader.py:71` - fetch_document() SOAP implementation
- `caseguard/utils/session_manager.py:16` - SessionManager for token persistence
- `caseguard/hdr_timeline/smart_field_retriever.py:53` - Smart field retrieval
- `config/canonical_fields_corrected.json` - Field mapping configuration
- `Proclaim.wsdl` - SOAP service definition

## Architecture Documentation

### Current Design Patterns

#### Hybrid REST/SOAP Architecture

- **REST APIs**: Used for metadata, validation, field data, authentication
- **SOAP APIs**: Used exclusively for binary document downloads
- **Session Sharing**: Single session token works across both REST and SOAP

#### Configuration-Driven Field Mapping

- **Central JSON Config**: All field relationships defined in `canonical_fields_corrected.json`
- **Type-Aware Validation**: Field retrievals include data type for proper parsing
- **Multi-Method Extraction**: Direct API + party extraction + history parsing

#### Robust Error Handling

- **Exponential Backoff**: Configurable retry logic with jitter
- **Graceful Degradation**: Continues processing when individual components fail
- **Progress Persistence**: Bulk operations can resume from interruption points

#### Multi-Processor Document Handling

- **Processing Pipeline**: LlamaParse primary, Docling fallback
- **Storage Strategy**: Only store successfully processable documents
- **Rate Limit Awareness**: Intelligent handling of external service limits

### Critical Dependencies

#### Proclaim API Case Detail Endpoint (Blocking Requirement)

**Status**: ✅ Fully Implemented

- Multiple specialized endpoints provide comprehensive case data access
- Robust error handling and retry mechanisms in place
- Supports both individual case and bulk processing scenarios
- Session management handles authentication lifecycle properly

#### Enhanced Session Management

**Status**: ✅ Fully Implemented

- Token-based authentication with automatic cleanup
- Persistent session storage for debugging and monitoring
- Graceful handling of session timeouts and renewals
- Force cleanup utilities for session recovery

### Integration Points

- **Timeline Engine**: Canonical fields feed HDR protocol stage detection
- **Case Enrichment**: Enricher extracts canonical data for timeline analysis
- **Vector Search**: Pinecone integration for semantic field discovery
- **Database Storage**: Structured data persistence for timeline views
- **Document Processing**: Multi-stage text extraction and cloud storage

### Environment Configuration

Required environment variables:

- `PROCLAIM_BASE_URL`: API base endpoint
- `PROCLAIM_USERNAME`: Authentication username
- `PROCLAIM_PASSWORD`: Authentication password
- `PROCLAIM_WSDL_PATH`: Path to SOAP WSDL file
- `SOAP_REQUEST_DELAY_MS`: Delay between SOAP requests (default: 500ms)

### Testing Infrastructure

- **Integration Tests**: End-to-end case processing verification
- **Unit Tests**: Individual component validation
- **Performance Tests**: Bulk processing benchmarks
- **Connection Tests**: API connectivity validation scripts

## Related Research

This research builds upon the existing implementation and provides comprehensive documentation for the complete Proclaim API integration architecture.

## Open Questions

None identified - the implementation appears comprehensive and production-ready for the specified requirements.

## Follow-up Research 2025-09-27T03:01:28+00:00

### DigitalOcean Spaces Storage Implementation

**Primary Location**: `caseguard/storage/spaces.py`

#### S3-Compatible Storage Architecture

- **Client Initialization**: Uses boto3 S3 client with DigitalOcean endpoint (`spaces.py:30-49`)
- **Authentication**: AWS CLI/system credentials with optional profile support (`spaces.py:37-43`)
- **Endpoint Configuration**: Path-style addressing for Spaces compatibility (`spaces.py:48`)

#### Core Storage Operations

##### File Upload Methods

- **Raw File Upload**: `upload_file()` with automatic MIME type detection (`spaces.py:51-75`)
- **Binary Data Upload**: `upload_bytes()` for direct byte arrays (`spaces.py:77-96`)
- **Text Upload**: `upload_text()` convenience method with UTF-8 encoding (`spaces.py:98-108`)

##### Object Management

- **Existence Check**: `object_exists()` using HEAD requests (`spaces.py:110-115`)
- **Pre-signed URLs**: `generate_presigned_url()` for temporary access (`spaces.py:117-123`)
- **Object Listing**: `list_objects()` with prefix filtering and pagination (`spaces.py:125-143`)
- **Download Methods**: `download_object()` and `get_object_text()` (`spaces.py:145-165`)

### Document Upload Patterns and Object Key Strategies

**Primary Location**: `caseguard/main.py:549-628`

#### Object Key Hierarchical Structure

The codebase uses a consistent tenant-based key naming strategy:

```
fdm_solicitors/
├── documents/
│   ├── raw/{case_ref}/{filename}              # Raw document files from Proclaim
│   └── processed_text/{case_ref}/{doc_code}.txt  # Processed text versions
└── dossiers/
    └── raw_dossiers_{timestamp}.json          # Case metadata snapshots
```

#### Document Processing Pipeline

1. **Document Discovery**: Metadata extracted from case history events (`client.py:230-269`)
2. **SOAP Download**: Binary documents fetched via ProclaimSoapDownloader (`main.py:573`)
3. **Text Processing**: LlamaParse conversion with rate limit handling (`main.py:596-603`)
4. **Conditional Storage**: Only processable documents are stored (`main.py:606-627`)

##### Storage Strategy Implementation (`main.py:608-625`)

- **Raw Document Storage**: `fdm_solicitors/documents/raw/{case_ref}/{filename}`
- **Processed Text Storage**: `fdm_solicitors/documents/processed_text/{case_ref}/{doc_code}.txt`
- **Metadata Update**: `doc.file_path = raw_location.object_key` links document manifest to storage
- **Quality Control**: Only documents with successful text extraction are stored

### Vector Storage with Object Paths for Agent Citations

**Primary Location**: `caseguard/vectorization/embedder.py:413-479`

#### Vector Metadata Structure

Each vector stored in Pinecone includes comprehensive metadata for agent citations:

##### Document Vector Metadata (`embedder.py:458-474`)

```python
metadata = {
    # Storage references for agent retrieval
    "object_key": doc.file_path,  # DigitalOcean Spaces path
    "s3_key": doc.file_path,      # Alternative reference name

    # Document identification
    "document_id": doc.document_code,
    "document_type": doc.document_type,
    "document_date": doc.date_created,

    # Multi-tenant isolation
    "tenant_id": "fdm_solicitors",

    # Case context
    "case_ref": case.case_ref,
    "source_type": "document_chunk" | "document"
}
```

##### History Event Vector Metadata (`embedder.py:322-341`)

```python
metadata = {
    # Event identification
    "source_type": "history_event",
    "event_date": event.createddate,
    "event_handler": event.handler,
    "action_type": event.actiontype,

    # Temporal context
    "days_from_opening": calculated_days,

    # Case-level metadata inherited
    **case_metadata
}
```

#### Vector-to-Storage Linking Pattern

- **Document Chunks**: `object_key` field contains full Spaces path (`fdm_solicitors/documents/raw/...`)
- **Processed Text**: Corresponding processed text accessible via pattern `processed_text/{case_ref}/{doc_code}.txt`
- **Stable IDs**: Vector IDs include case reference and document code for deterministic retrieval

### Agent Citation Mechanisms

**Primary Location**: `agents/application/citation_enhancer.py`

#### Citation Enhancement Architecture

The system provides structured citation enhancement for agent responses:

##### Pinecone Result Enhancement (`citation_enhancer.py:23-67`)

- **Document Reference Creation**: Extracts storage paths from vector metadata (`citation_enhancer.py:36-45`)
- **Confidence Scoring**: Uses vector similarity scores for citation reliability (`citation_enhancer.py:51`)
- **Rich Metadata**: Preserves all vector metadata for contextual information (`citation_enhancer.py:54-62`)

##### Citation Data Structure

```python
Citation = {
    "chunk_id": vector_id,
    "text_snippet": content_preview,
    "confidence_score": vector_score,
    "document_reference": {
        "document_id": doc_code,
        "s3_key": spaces_object_key,  # Direct path to document
        "filename": original_filename,
        "document_type": inferred_type
    },
    "case_reference": case_ref,
    "metadata": vector_metadata
}
```

#### Agent Search Integration (`agents/application/case_agent.py:32-49`)

- **Case-Filtered Search**: Agents search within specific case boundaries
- **Metadata Filtering**: Uses `{"case_ref": case_reference}` for isolation
- **Result Processing**: Converts Pinecone results to structured citations

### Data Pipeline Integration

**Primary Location**: `caseguard/main.py:300-365`

#### Pipeline Stage Architecture

##### Stage 1: Data Acquisition (`main.py:300-322`)

- **Spaces Loading**: Direct JSON loading from `s3://` or `spaces:` URLs
- **Local File Loading**: Existing dossier file processing
- **Proclaim Extraction**: Live API extraction with document processing

##### Stage 2: Document Processing Integration (`main.py:498`)

- **Embedded in Extraction**: `_fetch_and_process_documents()` called per case
- **Parallel Processing**: Documents processed alongside case metadata extraction
- **Storage-First Strategy**: Documents stored immediately after successful processing

##### Stage 3: Vector Generation (`main.py:337-342`)

- **Document Chunk Vectors**: Processed text from Spaces used for chunking (`embedder.py:430-442`)
- **Storage Path Injection**: Object keys embedded in vector metadata
- **Multi-Source Vectors**: History events, milestones, and document chunks combined

##### Stage 4: Pinecone Upload (`main.py:358`)

- **Metadata Preservation**: All storage references maintained in vector metadata
- **Multi-Index Support**: Separate summary and detail indexes with full citation data

#### Configuration Integration (`caseguard/main.py:196-216`)

- **Spaces Client Injection**: Automatically injected into enricher and embedder
- **Tenant-Aware Paths**: `processed_text_prefix` configured with tenant ID
- **Cross-Component Integration**: Spaces client shared across pipeline components

### Storage-to-Citation Workflow

1. **Document Upload**: Raw and processed documents stored with structured object keys
2. **Vector Creation**: Object keys embedded in vector metadata during embedding
3. **Agent Search**: Vector search returns results with storage references
4. **Citation Enhancement**: Storage paths converted to structured document references
5. **Document Retrieval**: Agents can access original documents via pre-signed URLs

### Environment Configuration for Data Pipeline

Required additional environment variables for Spaces integration:

- **DigitalOcean Spaces**:
  - `SPACES_BUCKET`: Bucket name for document storage
  - `SPACES_REGION`: DigitalOcean region (e.g., "nyc3")
  - `SPACES_ENDPOINT_URL`: Full endpoint URL
  - `SPACES_PROFILE`: Optional AWS profile for credentials
- **Tenant Configuration**:
  - `DEFAULT_TENANT_ID`: Used for object key prefixing (default: "fdm_solicitors")

### Integration Points for Developer Reference

- **Storage Client**: `caseguard/storage/spaces.py` - All Spaces operations
- **Pipeline Integration**: `caseguard/main.py:549` - Document processing workflow
- **Vector Metadata**: `caseguard/vectorization/embedder.py:458` - Citation data injection
- **Agent Citations**: `agents/application/citation_enhancer.py` - Citation enhancement utilities
- **Search Integration**: `agents/application/case_agent.py:38` - Case-filtered vector search
