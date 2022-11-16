import asyncio
import os
import re
import subprocess
import sys
import tempfile
import time
from asyncio.subprocess import PIPE
from tokenize import String
from typing import IO, Any, Callable, List, Optional, Tuple, cast

import pkg_resources
import unified_planning as up
from unified_planning.engines import Credits, PDDLPlanner
from unified_planning.engines.pddl_planner import Credits, LogMessage, PDDLPlanner
from unified_planning.engines.results import (
    LogLevel,
    PlanGenerationResult,
    PlanGenerationResultStatus,
)
from unified_planning.exceptions import UPException
from unified_planning.io.pddl_writer import PDDLWriter
from unified_planning.model import ProblemKind

credits = Credits(
    "SIADEX",
    "UGR SIADEX Team",
    "jorgesoler@ugr.es",
    "ignaciovellido@ugr.es",
    "faro@decsai.ugr.es",
    "https://ugr.es",
    "<license>",
)


class SIADEXEngine(PDDLPlanner):
    def __init__(self):
        super().__init__(needs_requirements=False)

    @staticmethod
    def name() -> str:
        return "SIADEX"

    def _get_cmd(
        self, domain_filename: str, problem_filename: str, plan_filename: str
    ) -> List[str]:
        base_command = [
            pkg_resources.resource_filename(__name__, "bin/planner"),
            "-d",
            domain_filename,
            "-p",
            problem_filename,
            "-o",
            plan_filename,
        ]
        return base_command

    # @staticmethod
    # def supported_kind() -> "ProblemKind":
    #     supported_kind = ProblemKind()
    #     supported_kind.set_problem_class("ACTION_BASED")  # type: ignore
    #     supported_kind.set_numbers("CONTINUOUS_NUMBERS")  # type: ignore
    #     supported_kind.set_problem_type("SIMPLE_NUMERIC_PLANNING")  # type: ignore
    #     supported_kind.set_typing("FLAT_TYPING")  # type: ignore
    #     supported_kind.set_typing("HIERARCHICAL_TYPING")  # type: ignore
    #     supported_kind.set_fluents_type("NUMERIC_FLUENTS")  # type: ignore
    #     supported_kind.set_conditions_kind("EQUALITY")  # type: ignore
    #     supported_kind.set_numbers("DISCRETE_NUMBERS")  # type: ignore
    #     supported_kind.set_effects_kind("INCREASE_EFFECTS")  # type: ignore
    #     supported_kind.set_effects_kind("DECREASE_EFFECTS")
    #     supported_kind.set_time("CONTINUOUS_TIME")  # type: ignore
    #     supported_kind.set_expression_duration("STATIC_FLUENTS_IN_DURATION")  # type: ignore
    #     return supported_kind

    @staticmethod
    def supports(problem_kind: "ProblemKind") -> bool:
        return problem_kind <= SIADEXEngine.supported_kind()

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return credits
