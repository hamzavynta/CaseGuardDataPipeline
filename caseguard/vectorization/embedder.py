"""Case embedder with DataPipelines tenant support and comprehensive metadata."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI
from tqdm import tqdm

logger = logging.getLogger(__name__)


class CaseEmbedder:
    """Generates embeddings for case data with DataPipelines tenant support."""

    def __init__(self, openai_client: OpenAI, tenant_id: str = None,
                 model: str = "text-embedding-3-large"):
        """Initialize case embedder.

        Args:
            openai_client: OpenAI client instance
            tenant_id: Tenant identifier for isolation
            model: Embedding model to use
        """
        self.openai_client = openai_client
        self.tenant_id = tenant_id
        self.model = model

        logger.info(f"CaseEmbedder initialized for tenant {tenant_id} with model {model}")

    def create_vectors_with_tenant_isolation(self, cases: List[Dict]) -> List[Dict]:
        """Create vectors with DataPipelines tenant metadata.

        Args:
            cases: List of case data dictionaries

        Returns:
            List of vector dictionaries ready for Pinecone
        """
        vectors = []

        logger.info(f"Creating embeddings for {len(cases)} cases")

        for case in tqdm(cases, desc="Embedding Cases"):
            try:
                case_ref = case.get('case_ref', 'unknown')

                # Create summary text from case data
                text = self._create_summary_text(case)

                # Generate embedding
                embedding = self._generate_embedding(text)
                if not embedding:
                    logger.warning(f"Failed to generate embedding for {case_ref}")
                    continue

                # Create comprehensive metadata with tenant isolation
                metadata = self._extract_comprehensive_metadata(case)
                metadata["tenant_id"] = self.tenant_id
                metadata["source_type"] = "case_summary"

                vector = {
                    "id": f"{self.tenant_id}_{case_ref}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "values": embedding,
                    "metadata": metadata
                }

                vectors.append(vector)

            except Exception as e:
                logger.error(f"Failed to create vector for {case.get('case_ref')}: {e}")

        logger.info(f"Successfully created {len(vectors)} vectors")
        return vectors

    def _create_summary_text(self, case: Dict[str, Any]) -> str:
        """Create comprehensive summary text for embedding.

        Args:
            case: Case data dictionary

        Returns:
            Summary text for embedding
        """
        try:
            # Start with basic case information
            parts = []

            case_ref = case.get('case_ref', 'Unknown')
            parts.append(f"Case Reference: {case_ref}")

            # Add AI insights if available
            ai_insights = case.get('enrichment', {}).get('ai_insights', {})
            if ai_insights:
                summary = ai_insights.get('case_summary', '')
                if summary:
                    parts.append(f"Summary: {summary}")

                key_issues = ai_insights.get('key_issues', [])
                if key_issues:
                    parts.append(f"Key Issues: {', '.join(key_issues)}")

                timeline_summary = ai_insights.get('timeline_summary', '')
                if timeline_summary:
                    parts.append(f"Timeline: {timeline_summary}")

            # Add canonical fields if available
            for field_name in ['claimant_name', 'defendant_name', 'case_status', 'handler_name']:
                field_data = case.get(field_name)
                if field_data and isinstance(field_data, dict):
                    value = field_data.get('value')
                    if value:
                        parts.append(f"{field_name.replace('_', ' ').title()}: {value}")

            # Add case details
            core_details = case.get('core_details', {})
            for key, value in core_details.items():
                if value and key not in ['case_ref']:
                    parts.append(f"{key.replace('_', ' ').title()}: {value}")

            # Add recent history items
            history = case.get('history', [])
            if history:
                recent_events = history[:5]  # Take first 5 events
                history_text = "; ".join([
                    event.get('description', '') for event in recent_events
                    if event.get('description')
                ])
                if history_text:
                    parts.append(f"Recent Activity: {history_text}")

            return ". ".join(parts)

        except Exception as e:
            logger.warning(f"Failed to create summary text: {e}")
            return f"Case {case.get('case_ref', 'Unknown')}"

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            List of embedding values or None
        """
        try:
            # Truncate text if too long (model limits)
            max_tokens = 8000  # Conservative limit for text-embedding-3-large
            if len(text) > max_tokens * 4:  # Rough estimate: 4 chars per token
                text = text[:max_tokens * 4]

            response = self.openai_client.embeddings.create(
                model=self.model,
                input=text
            )

            embedding = response.data[0].embedding
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def _extract_comprehensive_metadata(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Extract comprehensive metadata for vector search.

        Args:
            case: Case data dictionary

        Returns:
            Metadata dictionary
        """
        metadata = {
            "case_ref": case.get('case_ref', 'unknown'),
            "created_at": datetime.now().isoformat()
        }

        try:
            # Add basic case information
            core_details = case.get('core_details', {})
            metadata.update({
                "case_status": core_details.get('case_status', 'unknown'),
                "handler_name": core_details.get('handler_name', 'unknown'),
                "client_name": core_details.get('client_name', 'unknown')
            })

            # Add AI insights metadata
            ai_insights = case.get('enrichment', {}).get('ai_insights', {})
            if ai_insights:
                metadata.update({
                    "settlement_likelihood": ai_insights.get('settlement_likelihood', 0.0),
                    "confidence_score": case.get('enrichment', {}).get('confidence_score', 0.0),
                    "key_issues_count": len(ai_insights.get('key_issues', [])),
                    "risk_factors_count": len(ai_insights.get('risk_factors', []))
                })

            # Add canonical field metadata
            canonical_fields = ['claimant_name', 'defendant_name', 'date_opened', 'date_closed']
            for field_name in canonical_fields:
                field_data = case.get(field_name)
                if field_data and isinstance(field_data, dict):
                    value = field_data.get('value')
                    if value:
                        metadata[field_name] = str(value)

            # Add activity metadata
            history = case.get('history', [])
            metadata.update({
                "activity_count": len(history),
                "has_recent_activity": len(history) > 0
            })

            # Add document metadata
            document_manifest = case.get('document_manifest', [])
            metadata.update({
                "document_count": len(document_manifest),
                "has_documents": len(document_manifest) > 0
            })

            # Add data source metadata
            metadata.update({
                "data_source": case.get('data_source', 'unknown'),
                "fetch_type": case.get('fetch_type', 'unknown'),
                "is_full_rebuild": case.get('is_full_rebuild', False)
            })

            # Ensure all metadata values are strings or numbers (Pinecone requirement)
            cleaned_metadata = {}
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    cleaned_metadata[key] = value
                else:
                    cleaned_metadata[key] = str(value)

            return cleaned_metadata

        except Exception as e:
            logger.warning(f"Failed to extract comprehensive metadata: {e}")
            return metadata

    def create_detail_vectors(self, case: Dict[str, Any]) -> List[Dict]:
        """Create detailed vectors for specific case components.

        Args:
            case: Case data dictionary

        Returns:
            List of detail vector dictionaries
        """
        vectors = []
        case_ref = case.get('case_ref', 'unknown')

        try:
            # Create vectors for key issues
            ai_insights = case.get('enrichment', {}).get('ai_insights', {})
            key_issues = ai_insights.get('key_issues', [])

            for i, issue in enumerate(key_issues):
                try:
                    embedding = self._generate_embedding(issue)
                    if embedding:
                        metadata = {
                            "case_ref": case_ref,
                            "tenant_id": self.tenant_id,
                            "source_type": "key_issue",
                            "issue_index": i,
                            "issue_text": issue,
                            "created_at": datetime.now().isoformat()
                        }

                        vector = {
                            "id": f"{self.tenant_id}_{case_ref}_issue_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            "values": embedding,
                            "metadata": metadata
                        }

                        vectors.append(vector)

                except Exception as e:
                    logger.warning(f"Failed to create vector for issue {i}: {e}")

            # Create vectors for significant history events
            history = case.get('history', [])
            significant_events = [
                event for event in history[:10]  # Take top 10 events
                if len(event.get('description', '')) > 50  # Only meaningful events
            ]

            for i, event in enumerate(significant_events):
                try:
                    event_text = f"{event.get('description', '')} {event.get('notes', '')}"
                    embedding = self._generate_embedding(event_text)

                    if embedding:
                        metadata = {
                            "case_ref": case_ref,
                            "tenant_id": self.tenant_id,
                            "source_type": "history_event",
                            "event_index": i,
                            "event_date": event.get('date', ''),
                            "created_at": datetime.now().isoformat()
                        }

                        vector = {
                            "id": f"{self.tenant_id}_{case_ref}_event_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            "values": embedding,
                            "metadata": metadata
                        }

                        vectors.append(vector)

                except Exception as e:
                    logger.warning(f"Failed to create vector for history event {i}: {e}")

        except Exception as e:
            logger.error(f"Failed to create detail vectors for {case_ref}: {e}")

        return vectors

    def get_embedding_stats(self, vectors: List[Dict]) -> Dict[str, Any]:
        """Get statistics about created embeddings.

        Args:
            vectors: List of vector dictionaries

        Returns:
            Statistics dictionary
        """
        if not vectors:
            return {"total_vectors": 0}

        try:
            stats = {
                "total_vectors": len(vectors),
                "tenant_id": self.tenant_id,
                "model": self.model,
                "created_at": datetime.now().isoformat()
            }

            # Count by source type
            source_types = {}
            for vector in vectors:
                source_type = vector.get('metadata', {}).get('source_type', 'unknown')
                source_types[source_type] = source_types.get(source_type, 0) + 1

            stats["source_type_distribution"] = source_types

            # Get dimension info from first vector
            if vectors and vectors[0].get('values'):
                stats["embedding_dimension"] = len(vectors[0]['values'])

            return stats

        except Exception as e:
            logger.error(f"Failed to calculate embedding stats: {e}")
            return {"total_vectors": len(vectors), "error": str(e)}