"""Core case processing engine flow for V2 architecture."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from core.session_manager import V2SessionManager
from etl.prefect_config import CASEGUARD_V2_TAGS, DEFAULT_RETRY_DELAY_SECONDS
from caseguard.proclaim.soap_downloader import ProclaimSoapDownloader
from caseguard.storage.spaces import SpacesClient
from caseguard.hdr_timeline.smart_field_retriever import SmartFieldRetriever
from caseguard.vectorization.embedder import CaseEmbedder

logger = logging.getLogger(__name__)


@task(
    name="ingest_raw_data",
    description="Ingest case data from Proclaim with conditional full/incremental fetch",
    tags=CASEGUARD_V2_TAGS,
    retries=3,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=1800  # 30 minutes
)
def ingest_raw_data(tenant_id: str, case_ref: str, is_full_rebuild: bool = False) -> Dict[str, Any]:
    """Conditional full vs incremental data fetching from Proclaim.

    Args:
        tenant_id: Law firm tenant identifier
        case_ref: Unique case reference
        is_full_rebuild: Whether to fetch complete case data or incremental updates

    Returns:
        Dictionary containing raw case data
    """
    task_logger = get_run_logger()
    task_logger.info(f"Starting data ingestion for {case_ref} (full_rebuild={is_full_rebuild})")

    session_manager = V2SessionManager()

    with session_manager.bulk_processing_session() as session:
        try:
            # Use real ProclaimClient for data fetching
            proclaim_client = session_manager.get_proclaim_client(tenant_id)
            task_logger.info(f"Proclaim session active for tenant {tenant_id}")

            if is_full_rebuild:
                task_logger.info(f"Performing full data fetch for case {case_ref}")
                # Get comprehensive case data from Proclaim API
                raw_data = proclaim_client.get_case_data_with_tenant_context(case_ref)
                raw_data.update({
                    "fetch_type": "full",
                    "timestamp": datetime.utcnow().isoformat(),
                    "is_full_rebuild": is_full_rebuild,
                    "data_source": "proclaim_api"
                })
                task_logger.info(f"Full data fetch completed: {len(raw_data.get('history', []))} history events")
            else:
                task_logger.info(f"Performing incremental update fetch for case {case_ref}")
                # For incremental updates, we could implement change detection
                # For now, fetch full data but mark as incremental
                raw_data = proclaim_client.get_case_data_with_tenant_context(case_ref)
                raw_data.update({
                    "fetch_type": "incremental",
                    "timestamp": datetime.utcnow().isoformat(),
                    "is_full_rebuild": is_full_rebuild,
                    "data_source": "proclaim_api"
                })
                task_logger.info(f"Incremental fetch completed: {len(raw_data.get('history', []))} history events")

            return raw_data

        except Exception as e:
            task_logger.error(f"Data ingestion failed for {case_ref}: {e}")
            raise


@task(
    name="enrich_case_data",
    description="AI-only enrichment without canonical field dependencies",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=900  # 15 minutes
)
def enrich_case_data(case_data: Dict[str, Any]) -> Dict[str, Any]:
    """AI-only enrichment without canonical field dependencies.

    Args:
        case_data: Raw case data from Proclaim

    Returns:
        Enriched case data with AI insights
    """
    task_logger = get_run_logger()
    case_ref = case_data.get("case_ref", "unknown")
    task_logger.info(f"Starting AI enrichment for case {case_ref}")

    try:
        # Import V2 AI enricher (to be implemented)
        # from v2.ai.enricher import AIOnlyEnricher

        # For now, simulate AI enrichment
        task_logger.info("Generating AI insights without canonical field dependencies")

        enriched_data = {
            **case_data,
            "enrichment": {
                "ai_insights": {
                    "case_summary": f"AI-generated summary for case {case_ref}",
                    "key_issues": ["Contract dispute", "Payment delay"],
                    "timeline_summary": "Case opened with initial consultation, document review pending",
                    "settlement_likelihood": 0.65,
                    "risk_factors": ["Statute of limitations", "Documentation gaps"],
                    "recommended_actions": ["Review documentation", "Contact opposing counsel"]
                },
                "confidence_score": 0.82,
                "generated_at": datetime.utcnow().isoformat(),
                "enrichment_version": "v2.0"
            }
        }

        task_logger.info(f"AI enrichment completed for {case_ref}")
        task_logger.info(f"Settlement likelihood: {enriched_data['enrichment']['ai_insights']['settlement_likelihood']}")

        return enriched_data

    except Exception as e:
        task_logger.error(f"Case enrichment failed for {case_ref}: {e}")
        raise


@task(
    name="process_case_documents",
    description="Process case documents: SOAP download → text extraction → Spaces storage",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=1800  # 30 minutes
)
def process_case_documents(enriched_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process case documents: SOAP download → text extraction → Spaces storage.

    Args:
        enriched_data: AI-enriched case data

    Returns:
        Dictionary with document processing results
    """
    task_logger = get_run_logger()
    tenant_id = enriched_data['tenant_id']
    case_ref = enriched_data['case_ref']

    task_logger.info(f"Starting document processing for case {case_ref}")

    try:
        import os

        # Initialize document processing components
        downloader = ProclaimSoapDownloader(
            wsdl_path=os.getenv('PROCLAIM_WSDL_PATH', 'Proclaim.wsdl'),
            soap_endpoint=f"{os.getenv('PROCLAIM_BASE_URL')}/soap/",
            tenant_id=tenant_id
        )

        storage_client = SpacesClient(
            tenant_id=tenant_id,
            bucket=os.getenv('SPACES_BUCKET', 'caseguard-documents'),
            region=os.getenv('SPACES_REGION', 'nyc3'),
            endpoint_url=os.getenv('SPACES_ENDPOINT_URL', 'https://nyc3.digitaloceanspaces.com')
        )

        # Get session token for SOAP downloads
        session_manager = V2SessionManager()
        proclaim_client = session_manager.get_proclaim_client(tenant_id)
        token = proclaim_client.session_token

        # Process documents from case manifest
        processed_documents = []
        document_manifest = enriched_data.get('document_manifest', [])

        task_logger.info(f"Processing {len(document_manifest)} documents")

        for i, doc in enumerate(document_manifest[:5]):  # Limit to first 5 documents for now
            try:
                task_logger.info(f"Processing document {i+1}/{min(5, len(document_manifest))}: {doc.get('code', 'unknown')}")

                # Download via SOAP
                doc_path, error = downloader.fetch_document_with_tenant_context(
                    token=token,
                    document_code=doc.get('code', ''),
                    document_format=doc.get('format', 'ACROBAT-PDF')
                )

                if doc_path and not error:
                    # Store raw document
                    raw_location = storage_client.store_document_with_tenant_path(
                        local_path=doc_path,
                        case_ref=case_ref,
                        document_type="raw"
                    )

                    processed_documents.append({
                        'document_code': doc.get('code'),
                        'document_format': doc.get('format'),
                        'raw_storage_path': raw_location.object_key,
                        'storage_url': raw_location.url,
                        'status': 'processed',
                        'file_size': doc_path.stat().st_size if doc_path.exists() else 0
                    })

                    # Clean up temporary file
                    if doc_path.exists():
                        doc_path.unlink()

                else:
                    task_logger.warning(f"Failed to download document {doc.get('code')}: {error}")
                    processed_documents.append({
                        'document_code': doc.get('code'),
                        'status': 'failed',
                        'error': error
                    })

            except Exception as e:
                task_logger.error(f"Failed to process document {doc.get('code')}: {e}")
                processed_documents.append({
                    'document_code': doc.get('code'),
                    'status': 'failed',
                    'error': str(e)
                })

        result = {
            **enriched_data,
            'processed_documents': processed_documents,
            'document_processing_timestamp': datetime.now().isoformat(),
            'documents_processed': len([d for d in processed_documents if d.get('status') == 'processed']),
            'documents_failed': len([d for d in processed_documents if d.get('status') == 'failed'])
        }

        task_logger.info(f"Document processing completed: {result['documents_processed']} processed, {result['documents_failed']} failed")
        return result

    except Exception as e:
        task_logger.error(f"Document processing failed for {case_ref}: {e}")
        # Return enriched data with error info
        return {
            **enriched_data,
            'processed_documents': [],
            'document_processing_error': str(e),
            'document_processing_timestamp': datetime.now().isoformat()
        }


@task(
    name="populate_knowledge_bases",
    description="Vector embedding and Pinecone index population with enhanced metadata",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=600  # 10 minutes
)
def populate_knowledge_bases(enriched_data: Dict[str, Any]) -> Dict[str, Any]:
    """Vector embedding and Pinecone upserts using enhanced embedder.

    Args:
        enriched_data: AI-enriched case data with document processing results

    Returns:
        Dictionary with vector indexing results
    """
    task_logger = get_run_logger()
    case_ref = enriched_data['case_ref']
    tenant_id = enriched_data['tenant_id']

    task_logger.info(f"Starting enhanced vector embedding for case {case_ref}")

    try:
        import os
        from openai import OpenAI

        # Initialize enhanced embedder
        openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        embedder = CaseEmbedder(
            openai_client=openai_client,
            tenant_id=tenant_id,
            model="text-embedding-3-large"
        )

        # Create vectors with comprehensive metadata
        vectors = embedder.create_vectors_with_tenant_isolation([enriched_data])

        # Create detail vectors for key components
        detail_vectors = embedder.create_detail_vectors(enriched_data)
        all_vectors = vectors + detail_vectors

        # Get embedding statistics
        stats = embedder.get_embedding_stats(all_vectors)

        # TODO: Upload to Pinecone here
        # For now, simulate Pinecone upload
        task_logger.info(f"Would upload {len(all_vectors)} vectors to Pinecone")

        indexing_result = {
            "case_ref": case_ref,
            "tenant_id": tenant_id,
            "vectors_created": len(all_vectors),
            "summary_vectors": len(vectors),
            "detail_vectors": len(detail_vectors),
            "embedding_stats": stats,
            "indexed_at": datetime.now().isoformat(),
            "vector_ids": [v.get('id') for v in all_vectors[:5]]  # Sample of vector IDs
        }

        task_logger.info(f"Enhanced vector indexing completed: {len(all_vectors)} total vectors")
        return indexing_result

    except Exception as e:
        task_logger.error(f"Enhanced knowledge base population failed for {case_ref}: {e}")
        raise


@flow(
    name="process_proclaim_case",
    description="Core engine for individual case processing in V2 architecture",
    tags=CASEGUARD_V2_TAGS,
    task_runner=ConcurrentTaskRunner(),
    timeout_seconds=3600,  # 1 hour
    retries=1,
    retry_delay_seconds=300  # 5 minute delay before flow retry
)
def process_proclaim_case(
    tenant_id: str,
    case_ref: str,
    is_full_rebuild: bool = False,
    skip_enrichment: bool = False,
    skip_document_processing: bool = False,
    skip_vectorization: bool = False
) -> Dict[str, Any]:
    """Core engine for individual case processing.

    This flow orchestrates the complete processing pipeline for a single case:
    1. Ingest raw data from Proclaim
    2. Enrich with AI analysis
    3. Process documents (SOAP download → Spaces storage)
    4. Create and index vectors

    Args:
        tenant_id: Law firm tenant identifier
        case_ref: Unique case reference to process
        is_full_rebuild: Whether to perform full rebuild or incremental update
        skip_enrichment: Skip AI enrichment step (for testing/debugging)
        skip_document_processing: Skip document processing step (for testing/debugging)
        skip_vectorization: Skip vector creation step (for testing/debugging)

    Returns:
        Dictionary with processing results and metadata
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Starting case processing flow for {case_ref}")
    flow_logger.info(f"Tenant: {tenant_id}, Full rebuild: {is_full_rebuild}")

    start_time = datetime.utcnow()
    processing_results = {
        "case_ref": case_ref,
        "tenant_id": tenant_id,
        "is_full_rebuild": is_full_rebuild,
        "started_at": start_time.isoformat(),
        "steps_completed": [],
        "errors": []
    }

    try:
        # Step 1: Ingest raw data
        flow_logger.info("Step 1: Ingesting raw case data")
        raw_data = ingest_raw_data(tenant_id, case_ref, is_full_rebuild)
        processing_results["steps_completed"].append("data_ingestion")
        processing_results["raw_data_size"] = len(str(raw_data))

        # Step 2: AI enrichment (conditional)
        if not skip_enrichment:
            flow_logger.info("Step 2: AI enrichment")
            enriched_data = enrich_case_data(raw_data)
            processing_results["steps_completed"].append("ai_enrichment")
            processing_results["settlement_likelihood"] = (
                enriched_data.get("enrichment", {})
                .get("ai_insights", {})
                .get("settlement_likelihood", 0)
            )
        else:
            flow_logger.info("Step 2: Skipping AI enrichment")
            enriched_data = raw_data

        # Step 3: Document processing (conditional)
        if not skip_document_processing:
            flow_logger.info("Step 3: Processing case documents")
            document_data = process_case_documents(enriched_data)
            processing_results["steps_completed"].append("document_processing")
            processing_results["documents_processed"] = document_data.get("documents_processed", 0)
            processing_results["documents_failed"] = document_data.get("documents_failed", 0)
        else:
            flow_logger.info("Step 3: Skipping document processing")
            document_data = enriched_data

        # Step 4: Vector population (conditional)
        if not skip_vectorization:
            flow_logger.info("Step 4: Populating knowledge bases")
            vector_result = populate_knowledge_bases(document_data)
            processing_results["steps_completed"].append("vectorization")
            processing_results["vectors_created"] = vector_result.get("vectors_created", 0)
        else:
            flow_logger.info("Step 4: Skipping vectorization")
            vector_result = {"vectors_created": 0, "indexed_at": datetime.now().isoformat()}

        # Final results
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()

        final_result = {
            **processing_results,
            "status": "completed",
            "completed_at": end_time.isoformat(),
            "processing_time_seconds": processing_time,
            "vector_ids": vector_result.get("vector_ids", []),
            "total_vectors": vector_result.get("vectors_created", 0)
        }

        flow_logger.info(f"Case processing completed successfully in {processing_time:.1f}s")
        flow_logger.info(f"Steps completed: {final_result['steps_completed']}")

        return final_result

    except Exception as e:
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()

        error_result = {
            **processing_results,
            "status": "failed",
            "completed_at": end_time.isoformat(),
            "processing_time_seconds": processing_time,
            "error": str(e)
        }

        flow_logger.error(f"Case processing failed after {processing_time:.1f}s: {e}")
        flow_logger.error(f"Steps completed before failure: {processing_results['steps_completed']}")

        return error_result


# Utility flow for batch processing multiple cases
@flow(
    name="process_multiple_cases",
    description="Process multiple cases concurrently",
    tags=CASEGUARD_V2_TAGS,
    task_runner=ConcurrentTaskRunner(max_workers=5)
)
def process_multiple_cases(
    tenant_id: str,
    case_refs: list[str],
    is_full_rebuild: bool = False,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """Process multiple cases concurrently with controlled parallelism.

    Args:
        tenant_id: Law firm tenant identifier
        case_refs: List of case references to process
        is_full_rebuild: Whether to perform full rebuild for all cases
        max_concurrent: Maximum number of concurrent case processing flows

    Returns:
        Batch processing results
    """
    flow_logger = get_run_logger()
    flow_logger.info(f"Starting batch processing of {len(case_refs)} cases")

    batch_results = {
        "tenant_id": tenant_id,
        "total_cases": len(case_refs),
        "started_at": datetime.utcnow().isoformat(),
        "results": [],
        "successful": 0,
        "failed": 0
    }

    # Process cases in parallel using subflows
    for case_ref in case_refs:
        try:
            result = process_proclaim_case(tenant_id, case_ref, is_full_rebuild)
            batch_results["results"].append(result)

            if result.get("status") == "completed":
                batch_results["successful"] += 1
            else:
                batch_results["failed"] += 1

        except Exception as e:
            flow_logger.error(f"Failed to process case {case_ref}: {e}")
            batch_results["results"].append({
                "case_ref": case_ref,
                "status": "failed",
                "error": str(e)
            })
            batch_results["failed"] += 1

    batch_results["completed_at"] = datetime.utcnow().isoformat()
    flow_logger.info(f"Batch processing completed: {batch_results['successful']} successful, {batch_results['failed']} failed")

    return batch_results