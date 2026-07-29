from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class ForgetPlanError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ForgetOperation:
    path: Path
    content: bytes | None | Callable[[], bytes]
    category: str
