"""Actions and observations for ShiftDesk.

An action is one tool call: {"tool": "<name>", "args": {...}}. The tools
(list_files, read_file, write_file, bash, run_python, submit) are listed in the reset observation.
"""
from typing import Any

from openenv.core.env_server.types import Action, Observation
from pydantic import ConfigDict, Field


class DeskAction(Action):
    model_config = ConfigDict(extra="ignore")

    tool: str = Field(default="", description="Tool name: list_files, read_file, write_file, bash, run_python or submit.")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments for that tool, e.g. {\"path\": \"data.csv\"}, {\"command\": \"ls\"} or {\"answer\": ...}.")


class DeskObservation(Observation):
    task_id: str = Field(default="", description="Task being played")
    output: str = Field(default="", description="Task text at reset, then the result of the last call")
    ok: bool = Field(default=True, description="False when the last call was invalid")
    calls_left: int = Field(default=0, description="Tool calls left, the final answer included")
