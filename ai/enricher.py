"""Pure LLM insights without canonical field dependencies."""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from openai import OpenAI
from pydantic import BaseModel, Field

from v2.database.models import AIInsight

logger = logging.getLogger(__name__)


class CaseAnalysisPrompt(BaseModel):
    """Structured prompt for case analysis."""
    case_data: Dict[str, Any]
    analysis_type: str = "comprehensive"
    include_timeline: bool = True
    include_risk_assessment: bool = True
    include_recommendations: bool = True


class AIOnlyEnricher:
    """Pure LLM analysis without canonical field dependencies.

    This enricher generates insights directly from raw case data without
    relying on brittle canonical field extraction, making it more robust
    and adaptable to different case data formats.
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.1):
        """Initialize AI-only enricher.

        Args:
            model: OpenAI model to use for analysis
            temperature: Model temperature for controlled randomness
        """
        self.client = OpenAI()
        self.model = model
        self.temperature = temperature
        self.max_tokens = 4000

        logger.info(f"AIOnlyEnricher initialized with model: {model}")

    def generate_insights(self, case_data: Dict[str, Any]) -> AIInsight:
        """Generate insights using pure LLM analysis.

        Args:
            case_data: Raw case data from Proclaim or other sources

        Returns:
            AIInsight object with structured analysis
        """
        case_ref = case_data.get("case_ref", "unknown")
        logger.info(f"Generating AI insights for case {case_ref}")

        try:
            # Create comprehensive analysis prompt
            prompt = self._create_analysis_prompt(case_data)

            # Get structured response from LLM
            analysis_response = self._query_llm(prompt)

            # Parse and validate response
            insights = self._parse_analysis_response(analysis_response, case_ref)

            logger.info(f"AI insights generated successfully for case {case_ref}")
            logger.info(f"Settlement likelihood: {insights.settlement_likelihood:.2f}")

            return insights

        except Exception as e:
            logger.error(f"Failed to generate AI insights for case {case_ref}: {e}")

            # Return minimal fallback insights
            return AIInsight(
                case_summary=f"Analysis failed for case {case_ref}: {str(e)}",
                key_issues=["Analysis error - manual review required"],
                timeline_summary="Timeline analysis unavailable due to processing error",
                settlement_likelihood=0.5,  # Neutral likelihood
                risk_factors=["Processing error - requires manual assessment"],
                recommended_actions=["Manual case review recommended"],
                confidence_score=0.0
            )

    def _create_analysis_prompt(self, case_data: Dict[str, Any]) -> str:
        """Create comprehensive analysis prompt for the LLM.

        Args:
            case_data: Raw case data

        Returns:
            Formatted prompt string
        """
        case_ref = case_data.get("case_ref", "unknown")

        # Extract key data sections
        core_details = case_data.get("core_details", {})
        history = case_data.get("history", [])
        parties = case_data.get("parties", [])
        documents = case_data.get("document_manifest", [])

        prompt = f"""
You are an expert legal case analyst. Analyze this legal case data and provide structured insights.

CASE REFERENCE: {case_ref}

CASE DATA:
{json.dumps(case_data, indent=2, default=str)[:3000]}...

Please analyze this case and provide your response in the following JSON format:

{{
    "case_summary": "A 2-3 sentence summary of the case and its current status",
    "key_issues": ["List of 3-5 key legal issues or points of concern"],
    "timeline_summary": "Brief timeline of significant events and milestones",
    "settlement_likelihood": 0.0-1.0 (decimal representing probability of settlement),
    "risk_factors": ["List of 3-5 risk factors that could impact the case"],
    "recommended_actions": ["List of 3-5 recommended next steps or actions"],
    "confidence_score": 0.0-1.0 (your confidence in this analysis)
}}

ANALYSIS GUIDELINES:
1. Focus on the legal substance rather than procedural details
2. Consider the case type, parties involved, and any patterns in the history
3. Settlement likelihood should reflect realistic assessment based on case characteristics
4. Risk factors should identify potential complications or challenges
5. Recommended actions should be specific and actionable
6. Base confidence score on data quality and completeness

Provide ONLY the JSON response, no additional text.
        """

        return prompt.strip()

    def _query_llm(self, prompt: str) -> str:
        """Query the LLM with the analysis prompt.

        Args:
            prompt: Formatted analysis prompt

        Returns:
            Raw LLM response

        Raises:
            Exception: If LLM query fails
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )

            if not response.choices:
                raise ValueError("No response choices returned from LLM")

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response content from LLM")

            return content

        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            raise

    def _parse_analysis_response(self, response: str, case_ref: str) -> AIInsight:
        """Parse and validate LLM analysis response.

        Args:
            response: Raw LLM response
            case_ref: Case reference for logging

        Returns:
            Validated AIInsight object

        Raises:
            Exception: If parsing or validation fails
        """
        try:
            # Parse JSON response
            analysis_data = json.loads(response)

            # Validate required fields
            required_fields = [
                "case_summary", "key_issues", "timeline_summary",
                "settlement_likelihood", "risk_factors", "recommended_actions"
            ]

            for field in required_fields:
                if field not in analysis_data:
                    raise ValueError(f"Missing required field: {field}")

            # Validate and clean data types
            settlement_likelihood = float(analysis_data.get("settlement_likelihood", 0.5))
            settlement_likelihood = max(0.0, min(1.0, settlement_likelihood))  # Clamp to 0-1

            confidence_score = float(analysis_data.get("confidence_score", 0.8))
            confidence_score = max(0.0, min(1.0, confidence_score))  # Clamp to 0-1

            # Ensure lists are actually lists
            key_issues = analysis_data.get("key_issues", [])
            if not isinstance(key_issues, list):
                key_issues = [str(key_issues)]

            risk_factors = analysis_data.get("risk_factors", [])
            if not isinstance(risk_factors, list):
                risk_factors = [str(risk_factors)]

            recommended_actions = analysis_data.get("recommended_actions", [])
            if not isinstance(recommended_actions, list):
                recommended_actions = [str(recommended_actions)]

            # Create validated AIInsight object
            insights = AIInsight(
                case_summary=str(analysis_data.get("case_summary", "Summary not provided")),
                key_issues=key_issues[:10],  # Limit to 10 items
                timeline_summary=str(analysis_data.get("timeline_summary", "Timeline not provided")),
                settlement_likelihood=settlement_likelihood,
                risk_factors=risk_factors[:10],  # Limit to 10 items
                recommended_actions=recommended_actions[:10],  # Limit to 10 items
                confidence_score=confidence_score
            )

            # Log analysis quality metrics
            logger.info(f"Analysis quality for {case_ref}: confidence={confidence_score:.2f}, "
                       f"issues={len(key_issues)}, risks={len(risk_factors)}")

            return insights

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response for {case_ref}: {e}")
            logger.error(f"Raw response: {response[:500]}...")
            raise ValueError(f"Invalid JSON in LLM response: {e}")

        except Exception as e:
            logger.error(f"Failed to validate analysis response for {case_ref}: {e}")
            raise

    def generate_case_priority_score(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate priority score for case processing order.

        Args:
            case_data: Raw case data

        Returns:
            Priority scoring results
        """
        case_ref = case_data.get("case_ref", "unknown")
        logger.info(f"Generating priority score for case {case_ref}")

        try:
            # Generate basic insights first
            insights = self.generate_insights(case_data)

            # Calculate priority score based on multiple factors
            priority_factors = {
                "settlement_likelihood": insights.settlement_likelihood * 0.3,  # 30% weight
                "risk_level": len(insights.risk_factors) / 10.0 * 0.2,  # 20% weight
                "complexity": len(insights.key_issues) / 10.0 * 0.2,  # 20% weight
                "urgency": self._assess_urgency(case_data) * 0.3  # 30% weight
            }

            # Calculate overall priority (0-1 scale)
            priority_score = sum(priority_factors.values())
            priority_score = max(0.0, min(1.0, priority_score))

            # Categorize priority level
            if priority_score >= 0.8:
                priority_level = "critical"
            elif priority_score >= 0.6:
                priority_level = "high"
            elif priority_score >= 0.4:
                priority_level = "medium"
            else:
                priority_level = "low"

            priority_result = {
                "case_ref": case_ref,
                "priority_score": priority_score,
                "priority_level": priority_level,
                "factors": priority_factors,
                "insights_summary": {
                    "settlement_likelihood": insights.settlement_likelihood,
                    "risk_count": len(insights.risk_factors),
                    "issue_count": len(insights.key_issues),
                    "confidence": insights.confidence_score
                },
                "generated_at": datetime.utcnow().isoformat()
            }

            logger.info(f"Priority score for {case_ref}: {priority_score:.2f} ({priority_level})")
            return priority_result

        except Exception as e:
            logger.error(f"Failed to generate priority score for {case_ref}: {e}")
            return {
                "case_ref": case_ref,
                "priority_score": 0.5,  # Default medium priority
                "priority_level": "medium",
                "error": str(e),
                "generated_at": datetime.utcnow().isoformat()
            }

    def _assess_urgency(self, case_data: Dict[str, Any]) -> float:
        """Assess case urgency based on available data.

        Args:
            case_data: Raw case data

        Returns:
            Urgency score (0-1)
        """
        urgency_score = 0.5  # Default medium urgency

        try:
            # Check case age (newer cases might be more urgent)
            core_details = case_data.get("core_details", {})
            opened_date = core_details.get("opened_date") or core_details.get("date_opened")

            if opened_date:
                # Newer cases get higher urgency (within reason)
                # This is a simplified heuristic
                urgency_score += 0.1

            # Check for status indicators
            status = core_details.get("case_status", "").lower()
            if "urgent" in status or "critical" in status:
                urgency_score += 0.3
            elif "active" in status:
                urgency_score += 0.1

            # Check history for recent activity
            history = case_data.get("history", [])
            if len(history) > 10:  # High activity
                urgency_score += 0.2
            elif len(history) > 5:  # Medium activity
                urgency_score += 0.1

            # Clamp to valid range
            urgency_score = max(0.0, min(1.0, urgency_score))

        except Exception as e:
            logger.warning(f"Error assessing urgency: {e}")
            urgency_score = 0.5

        return urgency_score

    def batch_enrich_cases(
        self,
        cases: List[Dict[str, Any]],
        max_concurrent: int = 5,
        include_priority: bool = False
    ) -> List[Dict[str, Any]]:
        """Enrich multiple cases with AI analysis.

        Args:
            cases: List of case data dictionaries
            max_concurrent: Maximum concurrent analyses (rate limiting)
            include_priority: Whether to include priority scoring

        Returns:
            List of enrichment results
        """
        logger.info(f"Starting batch enrichment of {len(cases)} cases")

        results = []

        for i, case_data in enumerate(cases):
            case_ref = case_data.get("case_ref", f"case_{i}")
            logger.info(f"Processing case {i+1}/{len(cases)}: {case_ref}")

            try:
                # Generate insights
                insights = self.generate_insights(case_data)

                result = {
                    "case_ref": case_ref,
                    "enrichment_status": "completed",
                    "insights": insights.dict(),
                    "processed_at": datetime.utcnow().isoformat()
                }

                # Add priority scoring if requested
                if include_priority:
                    priority_result = self.generate_case_priority_score(case_data)
                    result["priority"] = priority_result

                results.append(result)

                # Simple rate limiting
                if (i + 1) % max_concurrent == 0 and i < len(cases) - 1:
                    import time
                    time.sleep(1)  # Brief pause every N cases

            except Exception as e:
                logger.error(f"Batch enrichment failed for case {case_ref}: {e}")
                results.append({
                    "case_ref": case_ref,
                    "enrichment_status": "failed",
                    "error": str(e),
                    "processed_at": datetime.utcnow().isoformat()
                })

        logger.info(f"Batch enrichment completed: {len(results)} results")
        return results


# Factory function for easy instantiation
def create_ai_enricher(model: str = "gpt-4o-mini", temperature: float = 0.1) -> AIOnlyEnricher:
    """Create an AI enricher instance with specified configuration.

    Args:
        model: OpenAI model to use
        temperature: Model temperature

    Returns:
        Configured AIOnlyEnricher instance
    """
    return AIOnlyEnricher(model=model, temperature=temperature)