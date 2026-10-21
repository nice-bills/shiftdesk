"""What a family builds for one episode."""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Built:
    question: str
    files: dict[str, str]
    check: Callable[[Any], float]
    answer: Any  # a reference answer, used only by tests
    answer_hint: str  # how to give the answer, shown to the policy
    budget: int = 12
    wrong: list = field(default_factory=list)  # plausible wrong answers, for tests
    # File-deliverable tasks: the path (relative to the working directory) the policy must write.
    # check() then receives that file's text (None when missing); answer is the reference file text.
    deliverable: str = ""
