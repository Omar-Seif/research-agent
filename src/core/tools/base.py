# src/core/tools/base.py

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class BaseTool(ABC, Generic[InputT, OutputT]):
    """
    Abstract base class for all research pipeline tools.

    Enforces a consistent execute() contract across tools with heterogeneous
    input/output types, using generics for type safety.

    Args:
        name: The name of the tool (e.g., "web_search", "fetch_articles").
        description: A human-readable description of what the tool does.
    """

    def __init__(self, name: str, description: str) -> None:
        if not name or not name.strip():
            raise ValueError("Tool name must be a non-empty string")
        if not description or not description.strip():
            raise ValueError("Tool description must be a non-empty string")

        self.name = name.strip()
        self.description = description.strip()

    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """
        Execute the tool with the given input.

        Args:
            input_data: The input to the tool (type varies by tool).

        Returns:
            The tool's output (type varies by tool).

        Raises:
            InputValidationError: If input_data is invalid.
            Tool-specific exceptions: DeadLinkError, MalformedResponseError, etc.
        """
        pass

    def __repr__(self) -> str:
        """Return a clean representation for logging and debugging."""
        return f"<{self.name}({self.__class__.__name__})>"

    def __str__(self) -> str:
        """Return the tool name as a string representation."""
        return self.name
