"""Core case processing engine flow for V2 architecture."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from v2.core.session_manager import V2SessionManager
from v2.etl.prefect_config import CASEGUARD_V2_TAGS, DEFAULT_RETRY_DELAY_SECONDS

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

    with V2SessionManager().bulk_processing_session() as session:
        try:
            # Import V2 Proclaim client (to be implemented)
            # from v2.proclaim.client import V2ProclaimClient

            # For now, simulate the client usage
            task_logger.info(f"Proclaim session active for tenant {tenant_id}")

            if is_full_rebuild:
                task_logger.info(f"Performing full data fetch for case {case_ref}")
                # Simulate full case data fetch
                raw_data = {
                    "case_ref": case_ref,
                    "tenant_id": tenant_id,
                    "fetch_type": "full",
                    "timestamp": datetime.utcnow().isoformat(),
                    "core_details": {
                        "case_status": "active",
                        "handler_name": "John Doe",
                        "client_name": "Client ABC"
                    },
                    "history": [],
                    "parties": [],
                    "document_manifest": []
                }
                task_logger.info(f"Full data fetch completed: {len(raw_data.get('history', []))} history events")
            else:
                task_logger.info(f"Performing incremental update fetch for case {case_ref}")
                # Simulate incremental update fetch
                raw_data = {
                    "case_ref": case_ref,
                    "tenant_id": tenant_id,
                    "fetch_type": "incremental",
                    "timestamp": datetime.utcnow().isoformat(),
                    "updates": [],
                    "new_documents": []
                }
                task_logger.info(f"Incremental fetch completed: {len(raw_data.get('updates', []))} updates")

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
    name="populate_knowledge_bases",
    description="Vector embedding and Pinecone index population",
    tags=CASEGUARD_V2_TAGS,
    retries=2,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    timeout_seconds=600  # 10 minutes
)
def populate_knowledge_bases(case_ref: str, enriched_data: Dict[str, Any]) -> Dict[str, Any]:
    """Vector embedding and Pinecone upserts for search indexing.

    Args:
        case_ref: Unique case reference
        enriched_data: AI-enriched case data

    Returns:
        Dictionary with vector indexing results
    """
    task_logger = get_run_logger()
    task_logger.info(f"Starting vector embedding and indexing for case {case_ref}")

    try:
        # Import V2 case embedder (to be implemented)
        # from v2.vectorization.embedder import V2CaseEmbedder

        # For now, simulate vector embedding and indexing
        task_logger.info("Creating embeddings with text-embedding-3-large model")

        # Simulate summary vector creation
        summary_text = enriched_data.get("enrichment", {}).get("ai_insights", {}).get("case_summary", "")
        summary_vector_id = f"{case_ref}_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Simulate detail vector creation
        detail_vectors = []
        for i, issue in enumerate(enriched_data.get("enrichment", {}).get("ai_insights", {}).get("key_issues", [])):
            detail_vector_id = f"{case_ref}_detail_{i}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            detail_vectors.append({
                "vector_id": detail_vector_id,
                "content": issue,
                "metadata": {
                    "case_ref": case_ref,
                    "tenant_id": enriched_data.get("tenant_id"),
                    "vector_type": "detail",
                    "issue_index": i
                }
            })

        indexing_result = {
            "case_ref": case_ref,
            "summary_vector": {
                "vector_id": summary_vector_id,
                "index": "case-summaries",
                "content_length": len(summary_text)
            },
            "detail_vectors": detail_vectors,
            "total_vectors": 1 + len(detail_vectors),
            "indexed_at": datetime.utcnow().isoformat()
        }

        task_logger.info(f"Vector indexing completed: {indexing_result['total_vectors']} vectors created")
        return indexing_result

    except Exception as e:
        task_logger.error(f"Knowledge base population failed for {case_ref}: {e}")
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
    skip_vectorization: bool = False
) -> Dict[str, Any]:
    """Core engine for individual case processing.

    This flow orchestrates the complete processing pipeline for a single case:
    1. Ingest raw data from Proclaim
    2. Enrich with AI analysis
    3. Create and index vectors

    Args:
        tenant_id: Law firm tenant identifier
        case_ref: Unique case reference to process
        is_full_rebuild: Whether to perform full rebuild or incremental update
        skip_enrichment: Skip AI enrichment step (for testing/debugging)
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

        # Step 3: Vector population (conditional)
        if not skip_vectorization:
            flow_logger.info("Step 3: Populating knowledge bases")
            vector_result = populate_knowledge_bases(case_ref, enriched_data)
            processing_results["steps_completed"].append("vectorization")
            processing_results["vectors_created"] = vector_result.get("total_vectors", 0)
        else:
            flow_logger.info("Step 3: Skipping vectorization")
            vector_result = {"total_vectors": 0, "indexed_at": datetime.utcnow().isoformat()}

        # Final results
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()

        final_result = {
            **processing_results,
            "status": "completed",
            "completed_at": end_time.isoformat(),
            "processing_time_seconds": processing_time,
            "vector_ids": vector_result.get("summary_vector", {}).get("vector_id"),
            "total_vectors": vector_result.get("total_vectors", 0)
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