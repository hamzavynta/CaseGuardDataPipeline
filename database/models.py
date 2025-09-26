"""Simplified Pydantic models for V2 without HDR complexity."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CaseStatus(str, Enum):
    """Case status enumeration."""
    ACTIVE = "active"
    COMPLETE = "complete"
    CLOSED = "closed"
    PENDING = "pending"


class ProcessingStatus(str, Enum):
    """Processing status for various operations."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CaseModel(BaseModel):
    """Simplified case model for V2 architecture."""
    case_ref: str = Field(..., description="Unique case reference")
    tenant_id: str = Field(..., description="Tenant/law firm identifier")
    status: CaseStatus = Field(default=CaseStatus.ACTIVE, description="Current case status")
    opened_date: Optional[datetime] = Field(None, description="Case opening date")
    closed_date: Optional[datetime] = Field(None, description="Case closing date")
    handler_name: Optional[str] = Field(None, description="Case handler name")
    client_name: Optional[str] = Field(None, description="Client name")
    case_type: Optional[str] = Field(None, description="Type of case")
    ai_insights: Optional[Dict[str, Any]] = Field(None, description="AI-generated insights")
    is_active: bool = Field(True, description="Whether case is currently active")
    last_serialno: int = Field(0, description="Last processed serial number for change detection")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CaseDocument(BaseModel):
    """Document model for case files."""
    id: Optional[int] = Field(None, description="Database primary key")
    case_ref: str = Field(..., description="Associated case reference")
    tenant_id: str = Field(..., description="Tenant identifier")
    document_id: str = Field(..., description="Unique document identifier")
    proclaim_doc_code: Optional[str] = Field(None, description="Proclaim document code")
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="Document file type/extension")
    file_size: int = Field(0, description="File size in bytes")
    processing_status: ProcessingStatus = Field(default=ProcessingStatus.PENDING)
    llama_parse_result: Optional[Dict[str, Any]] = Field(None, description="LlamaParse processing result")
    raw_s3_key: Optional[str] = Field(None, description="Raw file S3 storage key")
    processed_s3_key: Optional[str] = Field(None, description="Processed text S3 storage key")
    processed_text_length: int = Field(0, description="Length of processed text")
    document_description: Optional[str] = Field(None, description="Document description")
    date_created: Optional[datetime] = Field(None, description="Document creation date")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIInsight(BaseModel):
    """AI-generated case insights."""
    case_summary: str = Field(..., description="AI-generated case summary")
    key_issues: List[str] = Field(default_factory=list, description="Identified key legal issues")
    timeline_summary: str = Field("", description="Timeline of significant events")
    settlement_likelihood: float = Field(0.0, ge=0.0, le=1.0, description="Settlement probability (0-1)")
    risk_factors: List[str] = Field(default_factory=list, description="Identified risk factors")
    recommended_actions: List[str] = Field(default_factory=list, description="AI-recommended next actions")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="AI confidence in analysis")
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class VectorRecord(BaseModel):
    """Vector embedding record for search indexing."""
    id: Optional[int] = Field(None, description="Database primary key")
    case_ref: str = Field(..., description="Associated case reference")
    tenant_id: str = Field(..., description="Tenant identifier")
    vector_type: str = Field(..., description="Type of vector (summary, detail, etc.)")
    vector_id: str = Field(..., description="Pinecone vector ID")
    content_hash: str = Field(..., description="Hash of source content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Vector metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProcessingJob(BaseModel):
    """Processing job for queue management."""
    id: Optional[int] = Field(None, description="Database primary key")
    tenant_id: str = Field(..., description="Tenant identifier")
    case_ref: str = Field(..., description="Case to process")
    job_type: str = Field(..., description="Type of processing job")
    is_full_rebuild: bool = Field(False, description="Whether this is a full rebuild")
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING)
    priority: int = Field(0, description="Job priority (higher = more urgent)")
    attempts: int = Field(0, description="Number of processing attempts")
    max_attempts: int = Field(3, description="Maximum retry attempts")
    error_message: Optional[str] = Field(None, description="Last error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Job metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None, description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")


class TenantConfig(BaseModel):
    """Tenant configuration model."""
    tenant_id: str = Field(..., description="Unique tenant identifier")
    display_name: str = Field(..., description="Human-readable tenant name")
    is_active: bool = Field(True, description="Whether tenant is active")

    # CRM configuration
    crm_type: str = Field("proclaim", description="CRM system type")
    crm_api_base_url: str = Field(..., description="CRM API base URL")
    crm_credentials: Dict[str, str] = Field(..., description="CRM credentials")

    # Processing configuration
    concurrent_limit: int = Field(25, description="Concurrent processing limit")
    retry_attempts: int = Field(3, description="Default retry attempts")
    session_timeout_hours: int = Field(6, description="Session timeout")

    # Vector configuration
    use_shared_indexes: bool = Field(True, description="Use shared Pinecone indexes")
    case_summaries_index: str = Field("case-summaries", description="Summaries index name")
    case_details_index: str = Field("case-details", description="Details index name")
    embedding_model: str = Field("text-embedding-3-large", description="OpenAI embedding model")
    chunk_size: int = Field(1000, description="Text chunking size")

    # Document processing configuration
    allowed_extensions: List[str] = Field(default_factory=lambda: [
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".xls", ".xlsx",
        ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".tiff", ".eml", ".msg"
    ])
    max_file_size_mb: int = Field(50, description="Maximum file size in MB")
    llamaparse_only: bool = Field(True, description="Use only LlamaParse for processing")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SystemHealth(BaseModel):
    """System health status model."""
    component_name: str = Field(..., description="System component name")
    status: str = Field(..., description="Component status (healthy/degraded/failed)")
    last_check: datetime = Field(default_factory=datetime.utcnow)
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional health data")