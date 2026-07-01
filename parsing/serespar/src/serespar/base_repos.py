import abc
from typing import TypeVar

from pydantic import BaseModel

# Pydantic BaseModel variant type
SeresT = TypeVar('SeresT', bound=BaseModel)

class AbstractBaseRepository[SeresT](abc.ABC):
    @abc.abstractmethod
    def add(self, seres: SeresT) -> None:
        pass

    @abc.abstractmethod
    # Create your own ABC if your id is not int
    def get(self, seres_id: int) -> SeresT | None:
        pass
