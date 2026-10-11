"""Actions and observations for ShiftDesk.

An action is one tool call: {"tool": "<name>", "args": {...}}. The tool names
and argument names change from episode to episode and are listed in the reset
observation, so the policy has to read them instead of memorizing them.
"""
from typing import Any

from openenv.core.env_server.types import Action, Observation
from pydantic import ConfigDict, Field


class DeskAction(Action):
    model_config = ConfigDict(extra="ignore")

    tool: str = Field(default="", description="Name of a tool listed in the task.")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments for that tool.")


class DeskObservation(Observation):
    task_id: str = Field(default="", description="Task being played")
    output: str = Field(default="", description="Task text at reset, then the result of the last call")
    ok: bool = Field(default=True, description="False when the last call was invalid")
    calls_left: int = Field(default=0, description="Tool calls left, the final answer included")
