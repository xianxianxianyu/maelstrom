from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar('T')


class BaseService(ABC, Generic[T]):
    """Abstract base for all service classes"""

    @abstractmethod
    async def process(self, input_data: T) -> T:
        """Process input and return output"""
        pass

    def _validate_input(self, data: T) -> None:
        """Hook for subclasses to add validation"""
        pass
