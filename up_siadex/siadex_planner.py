import asyncio
import os
import re
import subprocess
import sys
import tempfile
from asyncio.subprocess import PIPE
from datetime import datetime
from fractions import Fraction
from typing import IO, Callable, List, Optional, Union

import pkg_resources
import unified_planning as up
from unified_planning.engines import Credits, PDDLPlanner
from unified_planning.engines.pddl_planner import (
    run_command_asyncio,
    run_command_posix_select,
)
from unified_planning.engines.results import (
    LogLevel,
    LogMessage,
    PlanGenerationResult,
    PlanGenerationResultStatus,
)
from unified_planning.exceptions import UPException
from unified_planning.io.hpdl.hpdl_writer import HPDLWriter
from unified_planning.model import ProblemKind
from unified_planning.model.htn.hierarchical_problem import HierarchicalProblem

from up_siadex import SIADEXDebugger
from up_siadex.dt_parser import DecompositionTreeParser

USE_ASYNCIO_ON_UNIX = False
ENV_USE_ASYNCIO = os.environ.get("UP_USE_ASYNCIO_PDDL_PLANNER")
if ENV_USE_ASYNCIO is not None:
    USE_ASYNCIO_ON_UNIX = ENV_USE_ASYNCIO.lower() in ["true", "1"]


credits = Credits(
    "SIADEX",
    "UGR SIADEX Team",
    "faro@decsai.ugr.es, jorgesoler@ugr.es, ignaciovellido@ugr.es",
    "https://ugr.es",
    "",
    "SIADEX ENGINE",
    "SIADEX HTN PLANNING ENGINE",
)


class SIADEXEngine(PDDLPlanner):
    def __init__(self, decomposition_tree: bool = False):
        super().__init__(needs_requirements=True)
        self.decomposition_tree = decomposition_tree

    # def _check_requisites(self):
    #     lib = subprocess.call(["which", "libreadline-dev"])
    #     py = subprocess.call(["which", "python2.7-dev"])
    #     if lib != 0 or py != 0:
    #         raise UPException("Package neededs on system: libreadline-dev, python2.7-dev")

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
        if self.decomposition_tree:
            base_command.append("-t")

        return base_command

    @staticmethod
    def debugger():
        return SIADEXDebugger()

    def _solve(
        self,
        problem: "up.model.AbstractProblem",
        callback: Optional[
            Callable[["up.engines.results.PlanGenerationResult"], None]
        ] = None,
        timeout: Optional[float] = None,
        output_stream: Optional[IO[str]] = None,
    ) -> "up.engines.results.PlanGenerationResult":
        # self._check_requisites()
        assert isinstance(problem, HierarchicalProblem)
        w = HPDLWriter(problem, self._needs_requirements)
        plan = None
        logs: List["up.engines.results.LogMessage"] = []
        with tempfile.TemporaryDirectory() as tempdir:
            domain_filename = os.path.join(tempdir, "domain.hpdl")
            problem_filename = os.path.join(tempdir, "problem.hpdl")
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
                plan, original_plan = self._plan_from_file(problem, plan_filename)
            if timeout_occurred and retval != 0:
                return PlanGenerationResult(
                    PlanGenerationResultStatus.TIMEOUT,
                    plan=plan,
                    log_messages=logs,
                    engine_name=self.name,
                )

        # Parse decomposition tree
        if self.decomposition_tree:
            dt_parser = DecompositionTreeParser()
            dt = dt_parser.parse(problem, proc_err[0], original_plan)
        else:
            dt = None

        status: PlanGenerationResultStatus = self._result_status(problem, plan, retval)
        return PlanGenerationResult(
            status,
            plan,
            decomposition_tree=dt,
            log_messages=logs,
            engine_name=self.name,
        )

    @staticmethod
    def supported_kind() -> "ProblemKind":
        # pylint: disable=no-member
        hpdl_kind = ProblemKind()
        hpdl_kind.set_problem_class("HIERARCHICAL")
        hpdl_kind.set_typing("HIERARCHICAL_TYPING")
        hpdl_kind.set_fluents_type("PYTHON_FLUENTS")
        hpdl_kind.set_conditions_kind("NEGATIVE_CONDITIONS")
        hpdl_kind.set_conditions_kind("DISJUNCTIVE_CONDITIONS")
        hpdl_kind.set_conditions_kind("EQUALITY")
        hpdl_kind.set_conditions_kind("EXISTENTIAL_CONDITIONS")
        hpdl_kind.set_conditions_kind("UNIVERSAL_CONDITIONS")
        hpdl_kind.set_effects_kind("CONDITIONAL_EFFECTS")
        hpdl_kind.set_numbers("DISCRETE_NUMBERS")
        hpdl_kind.set_numbers("CONTINUOUS_NUMBERS")
        hpdl_kind.set_fluents_type("NUMERIC_FLUENTS")
        hpdl_kind.set_effects_kind("INCREASE_EFFECTS")
        hpdl_kind.set_effects_kind("DECREASE_EFFECTS")
        hpdl_kind.set_time("TIMED_EFFECT")
        hpdl_kind.set_time("DURATION_INEQUALITIES")
        hpdl_kind.set_expression_duration("STATIC_FLUENTS_IN_DURATION")
        return hpdl_kind

    def _plan_from_file(
        self,
        problem: "up.model.Problem",
        plan_filename: str,
    ) -> "up.plans.Plan":
        """
        Takes a problem, a filename and a map of renaming and returns the plan parsed from the file.

        :param problem: The up.model.problem.Problem instance for which the plan is generated.
        :param plan_filename: The path of the file in which the plan is written.
        :param get_item_named: A function that takes a name and returns the original up.model element instance
            linked to that renaming.
        :return: The up.plans.Plan corresponding to the parsed plan from the file
        """
        actions: List = []

        def get_action_named(action_name, problem):
            try:
                action = problem.action(action_name)
                return action
            except Exception as e:
                action_name = action_name.replace("_", "-")
                action = problem.action(action_name)
                return action

        def get_object_named(obj_name, problem):
            try:
                obj = problem.object(obj_name)
                return obj
            except Exception as e:
                obj_name = obj_name.replace("_", "-")
                obj = problem.object(obj_name)
                return obj

        with open(plan_filename) as plan:
            is_tt = False
            original_plan = ""
            for line in plan.readlines():
                original_plan += line
                if re.match(r"^\s*(;.*)?$", line):
                    continue
                # line = line.lower()
                s_ai = re.match(
                    r"^:action\s*\(\s*([\w?-_]+)((\s+[\w?-_]+)*)\s*\)\s*$", line
                )
                t_ai = re.match(
                    r"^:action\s*\(\s*([\w?-_]+)((\s+[\w?-_]+)*)\s*\)\s*(start:\s*(.*)\s+end:\s*(.*)\s*)?$",
                    line,
                )
                if s_ai:
                    assert is_tt == False
                    name = s_ai.group(1)
                    params_name = s_ai.group(2).split()
                elif t_ai:
                    is_tt = True
                    name = t_ai.group(1)
                    params_name = t_ai.group(2).split()
                    dur = None
                    if t_ai.group(5) is not None:
                        beginning_time = datetime.strptime(
                            "05/06/2007 08:00:00", "%d/%m/%Y %H:%M:%S"
                        )
                        start_time = datetime.strptime(
                            t_ai.group(5), "%d/%m/%Y %H:%M:%S"
                        )
                        start = start_time - beginning_time
                        start = int(start.total_seconds() / 60)
                        end_time = datetime.strptime(t_ai.group(6), "%d/%m/%Y %H:%M:%S")
                        dur = end_time - start_time
                        dur = int(dur.total_seconds() / 60)  # Convert to minutes
                else:
                    raise UPException(
                        "Error parsing plan generated by "
                        + self.__class__.__name__
                        + "action:"
                        + line
                    )

                action = get_action_named(name, problem)
                assert isinstance(action, up.model.Action), "Wrong plan or renaming."
                parameters = []
                for p in params_name:
                    try:
                        obj = get_object_named(p, problem)
                    except:
                        obj = p
                    # assert isinstance(obj, up.model.Object), "Wrong plan or renaming."
                    if isinstance(obj, up.model.Object):
                        obj = problem.env.expression_manager.ObjectExp(obj)
                    parameters.append(obj)
                act_instance = up.plans.ActionInstance(action, tuple(parameters))
                if is_tt:
                    actions.append((start, act_instance, dur))
                else:
                    actions.append(act_instance)
        if is_tt:
            return up.plans.TimeTriggeredPlan(actions), original_plan
        else:
            return up.plans.SequentialPlan(actions), original_plan

    def _result_status(
        self,
        problem: "up.model.Problem",
        plan: Optional["up.plan.Plan"],
        retval: int = 0,
        log_messages: Optional[List["LogMessage"]] = None,
    ) -> "PlanGenerationResultStatus":
        if retval != 0:
            return PlanGenerationResultStatus.INTERNAL_ERROR
        elif plan is None:
            return PlanGenerationResultStatus.UNSOLVABLE_PROVEN
        else:
            return PlanGenerationResultStatus.SOLVED_SATISFICING

    @staticmethod
    def supports(problem_kind: "ProblemKind") -> bool:
        return problem_kind <= SIADEXEngine.supported_kind()

    @staticmethod
    def get_credits(**kwargs) -> Optional["Credits"]:
        return credits
