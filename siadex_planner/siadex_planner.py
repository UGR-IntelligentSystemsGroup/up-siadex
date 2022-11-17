import asyncio
import os
import subprocess
import sys
import tempfile
from asyncio.subprocess import PIPE
from typing import IO, Callable, List, Optional

import pkg_resources
import unified_planning as up
from unified_planning.engines import Credits, PDDLPlanner
from unified_planning.engines.pddl_planner import (
    run_command_asyncio,
    run_command_posix_select,
)
from unified_planning.engines.results import (
    LogLevel,
    PlanGenerationResult,
    PlanGenerationResultStatus,
)
from unified_planning.io.pddl_writer import PDDLWriter
from unified_planning.model import ProblemKind
from unified_planning.model.htn.hierarchical_problem import HierarchicalProblem

USE_ASYNCIO_ON_UNIX = False
ENV_USE_ASYNCIO = os.environ.get("UP_USE_ASYNCIO_PDDL_PLANNER")
if ENV_USE_ASYNCIO is not None:
    USE_ASYNCIO_ON_UNIX = ENV_USE_ASYNCIO.lower() in ["true", "1"]


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

    def _solve(
        self,
        problem: "up.model.AbstractProblem",
        callback: Optional[
            Callable[["up.engines.results.PlanGenerationResult"], None]
        ] = None,
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> "up.engines.results.PlanGenerationResult":
        assert isinstance(problem, HierarchicalProblem)
        # TODO: Replace this with HDPLWriter
        w = PDDLWriter(problem, self._needs_requirements)
        plan = None
        logs: List["up.engines.results.LogMessage"] = []
        with tempfile.TemporaryDirectory() as tempdir:
            domain_filename = os.path.join(tempdir, "domain.pddl")
            problem_filename = os.path.join(tempdir, "problem.pddl")
            plan_filename = os.path.join(tempdir, "plan.txt")
            w.write_domain(domain_filename)
            w.write_problem(problem_filename)
            cmd = self._get_cmd(domain_filename, problem_filename, plan_filename)

            if output_stream is None:
                # If we do not have an output stream to write to, we simply call
                # a subprocess and retrieve the final output and error with communicate
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                timeout_occurred: bool = False
                proc_out: List[str] = []
                proc_err: List[str] = []
                try:
                    out_err_bytes = process.communicate(timeout=timeout)
                    proc_out, proc_err = [[x.decode()] for x in out_err_bytes]
                except subprocess.TimeoutExpired:
                    timeout_occurred = True
                retval = process.returncode
            else:
                if sys.platform == "win32":
                    # On windows we have to use asyncio (does not work inside notebooks)
                    try:
                        loop = asyncio.ProactorEventLoop()
                        exec_res = loop.run_until_complete(
                            run_command_asyncio(
                                cmd, output_stream=output_stream, timeout=timeout
                            )
                        )
                    finally:
                        loop.close()
                else:
                    # On non-windows OSs, we can choose between asyncio and posix
                    # select (see comment on USE_ASYNCIO_ON_UNIX variable for details)
                    if USE_ASYNCIO_ON_UNIX:
                        exec_res = asyncio.run(
                            run_command_asyncio(
                                cmd, output_stream=output_stream, timeout=timeout
                            )
                        )
                    else:
                        exec_res = run_command_posix_select(
                            cmd, output_stream=output_stream, timeout=timeout
                        )
                timeout_occurred, (proc_out, proc_err), retval = exec_res

            logs.append(up.engines.results.LogMessage(LogLevel.INFO, "".join(proc_out)))
            logs.append(
                up.engines.results.LogMessage(LogLevel.ERROR, "".join(proc_err))
            )
            if os.path.isfile(plan_filename):
                plan = self._plan_from_file(problem, plan_filename)
            if timeout_occurred and retval != 0:
                return PlanGenerationResult(
                    PlanGenerationResultStatus.TIMEOUT,
                    plan=plan,
                    log_messages=logs,
                    engine_name=self.name,
                )
        status: PlanGenerationResultStatus = self._result_status(problem, plan)
        return PlanGenerationResult(
            status, plan, log_messages=logs, engine_name=self.name
        )

    @staticmethod
    def supported_kind() -> "ProblemKind":
        # pylint: disable=no-member
        supported_kind = ProblemKind()
        supported_kind.set_problem_class("ACTION_BASED")
        supported_kind.set_typing("FLAT_TYPING")
        supported_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        supported_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        supported_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        supported_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
        supported_kind.set_conditions_kind("EQUALITY")
        supported_kind.set_quality_metrics("ACTIONS_COST")
        supported_kind.set_quality_metrics("PLAN_LENGTH")
        return supported_kind

    @staticmethod
    def supports(problem_kind: "ProblemKind") -> bool:
        return problem_kind <= SIADEXEngine.supported_kind()

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return credits
