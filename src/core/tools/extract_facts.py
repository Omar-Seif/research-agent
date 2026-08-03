# src/core/tools/extract_facts.py

import json
from typing import List, Optional, Dict, Any
from uuid import uuid4

from src.core.models import ArticleContent, ExtractedFact
from src.core.tools.base import BaseTool
from src.core.llm_client import GroqLLMClient, LLMResponse
from src.config.logger import get_logger
from src.utils.exceptions import (
    InputValidationError,
    MalformedResponseError,
    ContextWindowExceededError,
    ExternalAPITimeoutError,
    ExternalAPIRateLimitError,
    UnexpectedError,
)

logger = get_logger(__name__)


# =============================================================================
# Extraction Prompts
# =============================================================================

EXTRACTION_SYSTEM_PROMPT = """
You are a fact extraction system. Analyze the provided article and extract factual claims that could be verified.

Focus on:
- Statements that are verifiable (not opinions or speculation)
- Concrete data, dates, numbers, names, events, and statistics
- Claims that would be useful for a research report
- The most important and relevant facts from the article

For each fact, provide:
1. statement: A clear, concise factual claim
2. extraction_confidence: A score from 0.0 to 1.0 indicating your confidence in the accuracy of the extraction
3. evidence: A direct quote or specific excerpt from the article that supports the fact

If you find no verifiable facts, return an empty facts array.
Do not include any explanation or additional text outside the tool call.
"""

EXTRACTION_USER_PROMPT_TEMPLATE = """
Article URL: {url}
Article Title: {title}

Article Content:
{content}

Extract the key factual claims from this article that could be verified.
"""

# =============================================================================
# Tool Schema
# =============================================================================

EXTRACT_FACTS_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_facts",
        "description": "Record structured facts extracted from an article",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "description": "List of facts extracted from the article",
                    "items": {
                        "type": "object",
                        "properties": {
                            "statement": {
                                "type": "string",
                                "description": "A factual claim extracted from the article",
                            },
                            "extraction_confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "Confidence that this fact was accurately extracted",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "A direct quote from the article supporting this fact",
                            },
                        },
                        "required": ["statement", "extraction_confidence", "evidence"],
                    },
                }
            },
            "required": ["facts"],
        },
    },
}


class ExtractFactsTool(BaseTool[List[ArticleContent], List[ExtractedFact]]):
    """
    Tool that extracts structured facts from article content using an LLM.

    Processes each article individually using a tool-call to guarantee
    structured JSON output. Skips failed articles and continues with the rest.
    """

    def __init__(self, llm_client: GroqLLMClient) -> None:
        """
        Initialize the fact extraction tool.

        Args:
            llm_client: The GroqLLMClient instance to use for LLM calls.
                       The model is already configured in the client.
        """
        super().__init__(
            name="extract_facts",
            description="Extract structured facts from article content for verification",
        )
        self.llm_client = llm_client

    async def execute(self, input_data: List[ArticleContent]) -> List[ExtractedFact]:
        """
        Extract facts from a list of articles.

        Processes each article individually. Skips failed articles and continues.

        Args:
            input_data: List of ArticleContent objects to extract facts from.

        Returns:
            List[ExtractedFact]: All facts extracted from all articles.

        Raises:
            InputValidationError: If input_data is not a list of ArticleContent.
        """
        if not isinstance(input_data, list):
            raise InputValidationError(
                message="Input must be a list of ArticleContent objects",
                tool_name=self.name,
                input_snippet=str(input_data)[:100],
            )

        if not input_data:
            return []

        all_facts: List[ExtractedFact] = []

        for article in input_data:
            try:
                facts = await self._extract_from_article(article)
                all_facts.extend(facts)
                logger.debug(f"Extracted {len(facts)} facts from {article.url}")

            except MalformedResponseError as e:
                logger.warning(
                    f"Skipping article {article.url}: malformed response - {e}"
                )
                continue

            except ContextWindowExceededError as e:
                logger.warning(
                    f"Skipping article {article.url}: context window exceeded - {e}"
                )
                continue

            except (ExternalAPITimeoutError, ExternalAPIRateLimitError) as e:
                logger.warning(f"Skipping article {article.url}: API error - {e}")
                continue

            except UnexpectedError as e:
                logger.error(f"Unexpected error for {article.url}: {e}", exc_info=True)
                continue

            except Exception as e:
                logger.error(f"Unhandled error for {article.url}: {e}", exc_info=True)
                continue

        logger.info(
            f"Extracted {len(all_facts)} total facts from {len(input_data)} articles"
        )
        return all_facts

    async def _extract_from_article(
        self, article: ArticleContent
    ) -> List[ExtractedFact]:
        """
        Extract facts from a single article.

        Args:
            article: The ArticleContent to extract facts from.

        Returns:
            List[ExtractedFact]: Facts extracted from the article, or empty list if none found.

        Raises:
            MalformedResponseError: If the LLM response cannot be parsed.
            ContextWindowExceededError: If the article exceeds the context window.
            ExternalAPITimeoutError: If the LLM request times out.
            ExternalAPIRateLimitError: If the rate limit is exceeded.
        """
        # Validate article content
        if not article.content or len(article.content.strip()) < 100:
            logger.warning(f"Article content too short for extraction: {article.url}")
            return []

        # Prepare messages
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": EXTRACTION_USER_PROMPT_TEMPLATE.format(
                    url=article.url,
                    title=article.title,
                    content=article.content,
                ),
            },
        ]

        try:
            # Call the LLM with forced tool calling
            response: LLMResponse = await self.llm_client.complete(
                messages=messages,
                tools=[EXTRACT_FACTS_TOOL_SCHEMA],
                tool_choice="required",
            )

            # Parse the response
            raw_facts = await self._parse_extraction_response(response)

            # Convert raw facts to ExtractedFact objects
            extracted_facts = []
            for raw_fact in raw_facts:
                extracted_facts.append(
                    ExtractedFact(
                        id=uuid4(),
                        statement=raw_fact["statement"],
                        extraction_confidence=raw_fact["extraction_confidence"],
                        source_urls=[article.url],
                        evidence=raw_fact.get("evidence"),
                    )
                )

            return extracted_facts

        except MalformedResponseError:
            raise

        except ContextWindowExceededError:
            raise

        except (ExternalAPITimeoutError, ExternalAPIRateLimitError):
            raise

        except Exception as e:
            raise UnexpectedError(
                message=f"Unexpected error extracting facts from {article.url}: {str(e)}",
                tool_name=self.name,
                input_snippet=article.url,
            ) from e

    async def _parse_extraction_response(
        self, response: LLMResponse
    ) -> List[Dict[str, Any]]:
        """
        Parse the tool-call response into a list of raw fact dictionaries.

        Args:
            response: The LLMResponse from the client. Should contain tool_calls.

        Returns:
            List[Dict[str, Any]]: Raw fact dictionaries from the tool call.

        Raises:
            MalformedResponseError: If the response cannot be parsed.
        """
        if not response.tool_calls:
            raise MalformedResponseError(
                message="LLM did not call the extract_facts tool despite tool_choice='required'",
                tool_name=self.name,
                input_snippet=str(response)[:200],
            )

        for tool_call in response.tool_calls:
            if tool_call.get("function", {}).get("name") == "extract_facts":
                try:
                    args = tool_call["function"]["arguments"]
                    if isinstance(args, str):
                        args = json.loads(args)
                    facts = args.get("facts", [])
                    if not isinstance(facts, list):
                        raise MalformedResponseError(
                            message="Tool call 'facts' field is not a list",
                            tool_name=self.name,
                            input_snippet=json.dumps(args)[:200],
                        )
                    return facts
                except json.JSONDecodeError as e:
                    raise MalformedResponseError(
                        message=f"Failed to parse tool call arguments: {e}",
                        tool_name=self.name,
                        input_snippet=str(args)[:200],
                    ) from e

        # The tool_calls list didn't contain the expected tool
        raise MalformedResponseError(
            message=f"Expected 'extract_facts' tool, got: {response.tool_calls}",
            tool_name=self.name,
            input_snippet=str(response.tool_calls)[:200],
        )
