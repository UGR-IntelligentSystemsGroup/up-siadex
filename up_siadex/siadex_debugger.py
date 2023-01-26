import os
import re
import subprocess
import tempfile
import threading
import time
from abc import ABC
from dataclasses import dataclass
from queue import Empty, Queue
from typing import List, Tuple, Union

import pkg_resources
import unified_planning as up
from unified_planning.io.hpdl.hpdl_writer import (
    ConverterToPDDLString,
    HPDLWriter,
    _get_pddl_name,
)
from unified_planning.model.htn.hierarchical_problem import HierarchicalProblem
from unified_planning.model.htn.task import Subtask, Task
from unified_planning.model.state import UPCOWState
from unified_planning.plans import ActionInstance, SequentialPlan
from unified_planning.shortcuts import *


def find_task_action(
    problem: "up.model.AbstractProblem", name: str
) -> Union[Task, Action]:
    """Returns the task or action by its name"""
    if name[-1] == "_":
        name = name[:-1]
    name = name.replace("_", "-")

    if problem.has_task(name):
        return problem.get_task(name)
    if problem.has_action(name):
        return problem.action(name)
    raise Exception(f"Not found Task or Action: {name}")


def find_depth(line: str) -> Tuple[int, str]:
    """Finds the depth in the message, returns the line clean"""
    if line.startswith("(***"):
        last = line.find("***)")
        depth = int(line[4:last])
        return depth, line[last + 4 :]

    return -1, line


def find_obj(problem: "up.model.AbstractProblem", name: str) -> "up.model.FNode":
    """Returns an object from the problem"""
    return problem.object(name.replace("_", "-"))


def find_fluent(problem: "up.model.AbstractProblem", name: str) -> "up.model.Fluent":
    """Returns a fluent from the problem"""
    if name[-1] == "_":
        name = name[:-1]
    return problem.fluent(name.replace("_", "-"))


class ICommand(ABC):
    """Abstract command"""

    name = None
    cmd = None

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        raise NotImplementedError()


class STRCommand(ABC):
    """Run a string command"""

    name = None
    cmd = None

    def __init__(self, cmd: str) -> None:
        super().__init__()
        self.cmd = cmd

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        [print(msg, end="") for msg in std]
        print("_" * 50)
        [print(msg, end="") for msg in err]


class StateCommand(ICommand):
    """Returns a list of parametrized fluents that represents the actual state"""

    name = "state"
    cmd = "print state"

    def parse(
        self,
        problem: "up.model.AbstractProblem",
        std: List[str],
        err: List[str],
    ) -> List[FNode]:
        err = [er for er in err if not er.startswith("(***")]
        err = [er for er in err if not er.startswith("\n")]
        result = []
        for pre in err:
            pre = pre.replace("(", "").replace(")", "").replace("\n", "").split(" ")
            fluent = find_fluent(problem, pre[0])
            parameters = []
            for obj in pre[1:]:
                parameters.append(find_obj(problem, obj))
            result.append(fluent(*parameters))

        # state = UPCOWState({f: True for f in result})
        return result


class EvalCommand(ICommand):

    cmd = "eval"
    name = "eval"
    parameters = None

    def __init__(self, precondition: str, parameters: List[Parameter] = None) -> None:
        super().__init__()
        self.cmd = f"eval {precondition}"
        self.parameters = parameters

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        unifications = []
        if err[-1].startswith("No unification"):
            return []

        """
        debug:> eval (and (at_ ?v - vehicle ?l1 - location) (road ?l1 - location ?l2 - location))
        __________________________________________________
        Evaluating: (and
        (at_ ?v ?l1)
        (road ?l1 ?l2)
        )

        ?l2 <- city_loc_0
        ?l1 <- city_loc_1
        ?v <- truck_0
        3 variable subtition(s).

        ?l2 <- city_loc_2
        ?l1 <- city_loc_1
        ?v <- truck_0
        3 variable subtition(s).
        """
        # Lets parse it reversed
        next_line = len(err) - 2
        while next_line > -1:
            # Is a new unification?
            line = err[next_line].removesuffix("\n")
            if line.startswith("("):
                break
            num = 0
            if line.endswith("variable subtition(s)."):
                # 3 variable subtition(s).
                # Get the number
                num = int(line.split(" ")[0])
                batch = {}
                for i in range(1, num + 1):
                    line = err[next_line - i].removesuffix("\n")
                    line = line.split(" <- ")
                    parameter = line[0].removeprefix("?")
                    if self.parameters:
                        for p in self.parameters:
                            if p.name == parameter:
                                parameter = p
                                break
                    obj = line[1]
                    batch[parameter] = find_obj(problem, obj)
                unifications.append(batch)

            next_line = next_line - num - 1

        return unifications


class EffectCommand(ICommand):
    cmd = "apply"
    name = "apply"

    def __init__(self, effect: str) -> None:
        super().__init__()
        self.cmd = f"apply {effect}"

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        pass
        # return STRCommand("").parse(problem, std, err)


@dataclass
class AgendaLine:
    """Represents one line of the agenda command"""

    identifier: int
    status: str
    expanded: str
    subtask: Subtask
    succesors: List[int]

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"""{self.identifier}: ({self.subtask.task.name if self.subtask else "root"} {self.subtask.parameters if self.subtask else ""}) 
                status: {self.status}, expanded: {self.expanded}, 
                succesors: {self.succesors}"""


class AgendaCommand(ICommand):
    """Print agenda command"""

    name = "agenda"
    cmd = "print agenda"

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        """
        __________________________________________________
        Succesors:
        [0] 2 3
        [1] 0
        [2] 0
        [3] 4
        [4] 5
        [5] 6
        [6] 0
        Task list:
        [1] (closed)     :unexpanded (deliver package_0 city_loc_0)
        [2] (agenda)     :unexpanded (deliver package_1 city_loc_2)
        [3] (agenda)     :unexpanded (get_to ?v ?l1)
        [4] (pending)    :unexpanded (load ?v ?l1 package_0)
        [5] (pending)    :unexpanded (get_to ?v ?l2)
        [6] (pending)    :unexpanded (unload ?v ?l2 package_0)
        ===========
        """
        tree = []

        # __________SUCCESSORS_____________
        # Find "Task list:" position
        for i, e in enumerate(err):
            if e.startswith("Task list:"):
                task_position = i
            if e.startswith("==========="):
                end_position = i

        # for i, e in enumerate(err):
        #     if e.startswith("==========="):
        #         end_position = i
        #         break

        successors = {}
        # From [0] to ...[n]
        for succ in err[1:task_position]:
            # [0] 2 3
            numbers = succ.removesuffix("\n").split(" ")
            if "0" in numbers[1:-1]:
                continue
            successors[int(numbers[0][1:-1])] = [int(n) for n in numbers[1:-1]]
        # __________TASKS_____________
        tasks = {}
        tasks[0] = AgendaLine(0, "root", "root", None, successors[0])

        rex = re.compile(r"\s+")  # remove multiple whitespace
        for task in err[task_position + 1 : end_position]:
            task = rex.sub(" ", task)
            line = (
                task.strip()
                .replace("(", "")
                .replace(")", "")
                .removesuffix("\n")
                .split(" ")
            )
            number = int(line[0][1:-1])  # [1]
            status = line[1]  # (agenda)
            expanded = line[2][1:]  # :unexpanded
            # subtask = line[3:]  # (deliver package_0 city_loc_0)
            action = find_task_action(problem, line[3])
            params = []
            for i, p in enumerate(line[4:]):
                # is a parameter?
                if p.startswith("?"):
                    params.append(action.parameters[i])
                else:
                    params.append(find_obj(problem, p))

            subtask = Subtask(action, params)
            tasks[number] = AgendaLine(
                identifier=number,
                status=status,
                expanded=expanded,
                subtask=subtask,
                succesors=successors.get(number, []),
            )

        return tasks


class PlanCommand(ICommand):
    """Returns the actual plan"""

    name = "plan"
    cmd = "print plan"

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ) -> SequentialPlan:
        actions = []
        for line in err:
            try:
                line = (
                    line.replace("(", "").replace(")", "").removesuffix("\n").split(" ")
                )
                action_name = line[1]
                params = [find_obj(problem, p) for p in line[2:]]
                action = find_task_action(problem, action_name)
                actions.append(ActionInstance(action, tuple(params)))
            except Exception as ex:
                ...

        return SequentialPlan(actions)


class NexpCommand(ICommand):
    name = "nexp"
    cmd = "nexp"

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        depth, line = find_depth(err[0])
        try:
            is_action = line.index("Solving action:")
            print("Solving action")
            """
            (*** 7 ***) Solving action:
            (:action drive
            :parameters ( truck_0 ?l1 - location ?l2 - location)
             """
            action_name = err[1].split(" ")[1].strip()
            action = find_task_action(problem, action_name)
            vars = (
                err[3]
                .removeprefix(":parameters")
                .replace("(", "")
                .replace(")", "")
                .replace("- ", "-")
                .strip()
                .split(" ")
            )

            print(vars)
            params = []
            for v in vars:
                if v.startswith("-"):
                    continue
                if v.startswith("?"):
                    continue

                params.append(find_obj(problem, v))

            return action, params
        except ValueError as error:
            ...

        print(depth)


class NextCommand(ICommand):
    name = "next"
    cmd = "next"

    def _detect_version(self, line: str) -> int:
        return 0

    def _parse_first(self, err: List[str]):
        pass

    def _parse_second(self, err: List[str]):
        pass

    def _parse_third(self, err: List[str]):
        pass

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        """
        1:
        __________________________________________________

        (*** 1 ***) Expanding: [0] (deliver package_0 city_loc_0)

        (*** 1 ***) Selecting a candidate task.
        (*** 1 ***) Found: 1 candidates (left).
            [0] :task (deliver ?p ?l)

        2:
        __________________________________________________
        (*** 1 ***) Selecting a method to expand from compound task.
        :task (deliver ?p ?l)
        (*** 1 ***) Found: 1 methods to expand (left).
            [0]
            (:method m_deliver
                :precondition
            ( )
                :tasks (
                    (get_to ?v ?l1)
                    (load ?v ?l1 ?p)
                    (get_to ?v ?l2)
                    (unload ?v ?l2 ?p)
                )
            )

        3:
        __________________________________________________
        (*** 1 ***) Expanding method: m_deliver
        (*** 1 ***) Working in task:
        (:task deliver
        :parameters ( ?p - package ?l - location)
        (:method m_deliver
            :precondition
            ( )
            :tasks (
                (get_to ?v ?l1)
                (load ?v ?l1 package_0)
                (get_to ?v ?l2)
                (unload ?v ?l2 package_0)
            )
            )
        )

        (*** 1 ***) Using method: m_deliver
        (*** 1 ***) No preconditions.
        Selecting unification:
        (*** 2 ***) Depth: 2
        (*** 2 ***) Selecting task to expand from agenda.
        4:
        __________________________________________________
        *** 3 ***) Solving action:
        (:action drive
        :parameters ( ?v - vehicle ?l1 - location ?l2 - location)
        :precondition
        (and
            (and
                (at_ ?v ?l1)
                (road ?l1 ?l2)
            )

        )

        :effect
        (and
            (not (at_ ?v ?l1))
            (at_ ?v ?l2)
        )

        )
        (*** 3 ***) working in action:
        (:action drive
        :parameters ( ?v - vehicle ?l1 - location ?l2 - location)
        :precondition
        (and
            (and
                (at_ ?v ?l1)
                (road ?l1 ?l2)
            )

        )

        :effect
        (and
            (not (at_ ?v ?l1))
            (at_ ?v ?l2)
        )

        )

        (*** 3 ***) Found: 1 unification(s) (left).
        Unification [0]:
        ?l2 <- city_loc_1
        ?l1 <- city_loc_2
        ?v <- truck_0
        3 variable subtition(s).

        Selecting unification:

        ___________________________________________
        (ccc) Performing unification:
        ?l2 <- city_loc_1
        ?l1 <- city_loc_2
        ?v <- truck_0
        3 variable subtition(s).

        (ccc) Deleted from state: (at_ truck_0 city_loc_2)
        (ccc) Added to state: (at_ truck_0 city_loc_1)
        (*** 4 ***) Depth: 4
        (*** 4 ***) Selecting task to expand from agenda.
        """

        return


class BreakCommand(ICommand):
    name = "break"
    cmd = "break"

    def __init__(self, name: str, params: List[str]) -> None:
        super().__init__()
        params = " ".join(params)
        self.cmd = f"break ({name} {params})"

    def parse(
        self, problem: "up.model.AbstractProblem", std: List[str], err: List[str]
    ):
        return STRCommand("").parse(problem, std, err)


class SIADEXDebugger:
    std_q = Queue()
    err_q = Queue()
    problem: "up.model.AbstractProblem" = None
    env: "up.model.Environment" = None
    converter: ConverterToPDDLString = None
    thread_std: threading.Thread = None
    thread_err: threading.Thread = None

    temp_dir = None
    process = None
    lock = False
    started = False

    def _get_cmd(self, domain_filename: str, problem_filename: str) -> List[str]:
        base_command = [
            pkg_resources.resource_filename(__name__, "bin/planner"),
            "-d",
            domain_filename,
            "-p",
            problem_filename,
            "-g",
        ]
        return base_command

    def _capture_output(self, queue: Queue):
        """This methods capture the output from a thread."""
        self.lock = True
        result = []
        while True:
            try:
                # Capture msgs
                line = queue.get(block=False)
                result.append(line)
                # print(line, end='')
            except Empty:
                # No more messages so...
                # # Free the lock
                # # return the result
                self.lock = False
                return result

    def _capture_std(self):
        """This methods captures the output of STD from the thread."""
        return self._capture_output(self.std_q)

    def _capture_error(self):
        """This methods captures the output of err from the thread."""
        return self._capture_output(self.err_q)

    def __del__(self):
        return self.stop()

    def debug(self, problem: "up.model.AbstractProblem"):
        """Initialize the debug process for a problem"""
        self.problem = problem
        assert isinstance(problem, HierarchicalProblem)
        self.env = problem.env
        self.converter = ConverterToPDDLString(problem.env, _get_pddl_name)
        writer = HPDLWriter(problem, True)
        self.temp_dir = tempfile.TemporaryDirectory()
        domain_filename = os.path.join(self.temp_dir.name, "domain.hpdl")
        problem_filename = os.path.join(self.temp_dir.name, "problem.hpdl")
        writer.write_domain(domain_filename)
        writer.write_problem(problem_filename)
        cmd = self._get_cmd(domain_filename, problem_filename)

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def output_reader(proc, outq):
            for line in iter(proc.stdout.readline, b""):
                outq.put(line.decode("utf-8"))

        def error_reader(proc, outq):
            for line in iter(proc.stderr.readline, b""):
                outq.put(line.decode("utf-8"))

        self.thread_std = threading.Thread(
            target=output_reader, args=(self.process, self.std_q)
        )
        self.thread_err = threading.Thread(
            target=error_reader, args=(self.process, self.err_q)
        )
        self.thread_std.start()
        self.thread_err.start()
        self.started = True

    def _run_command(self, command: str, parser=None):
        """Run a command in the debugger"""

        if not self.started:
            raise Exception("Please start the debugger first: debugger.debug(problem)")

        # If the process is locked running previous commands, lets wait until it has finnished
        while self.lock:
            time.sleep(0.5)
        try:
            # Lock the process
            self.lock = True

            # Write the command in the input
            self.process.stdin.write(f"{command}\n".encode())
            self.process.stdin.flush()
            # Time to wait for the response
            time.sleep(0.3)

            std = self._capture_std()
            err = self._capture_error()
            if parser:
                return parser(self.problem, std, err)
            else:
                [print(msg, end="") for msg in std]
                print("_" * 50)
                [print(msg, end="") for msg in err]
        except BrokenPipeError as error:
            print("Error: ", error)
            self.started = False

    def run(self, command: ICommand):
        """Run a command"""
        return self._run_command(command.cmd, command.parse)

    def force_run(self, command: str):
        """Runs a string command"""
        return self.run(STRCommand(command))

    def eval_preconditions(
        self,
        node: Union[
            "up.model.Action",
            "up.model.fnode.FNode",
            "up.model.fluent.Fluent",
            "up.model.parameter.Parameter",
            bool,
        ],
    ) -> List[Dict[Union[Parameter, str], FNode]]:
        """
        Evaluates a precondition on the actual state
        """
        parameters = None
        if isinstance(node, Action):
            precondition = node.preconditions[0]
            parameters = node.parameters
            command = self.converter.convert(precondition)
        elif isinstance(node, Fluent):
            args = ""
            for s in node.signature:
                args += f"?{s.name} "
            command = f"({node.name} {args})"
        else:
            precondition = node
            command = self.converter.convert(precondition)
        # print(precondition_exp)
        return self.run(EvalCommand(command, parameters))

    def apply_effect(self, effect: FNode):
        """Apply an effect"""
        command = self.converter.convert(effect)
        self.run(EffectCommand(command))
        return self.run(StateCommand())

    def list_break(self):
        """List all breakpoints"""
        return self.run(STRCommand("break"))

    def add_break(self, node: Union[FNode, Fluent, InstantaneousAction, Task]):
        """Set a breakpoint"""
        if isinstance(node, FNode) and node.is_fluent_exp():
            name = node.fluent().name
            params = [str(p).replace("-", "_") for p in node.args]
        elif isinstance(node, Fluent):
            name = node.name
            params = [f"?{p.name}" for p in node.signature]
        elif isinstance(node, Action) or isinstance(node, Task):
            name = node.name
            params = [f"?{p.name}" for p in node.parameters]

        return self.run(BreakCommand(name, params))

    def state(self) -> UPCOWState:
        """Returns a list of parametrized fluents that represents the actual state"""
        return self.run(StateCommand())

    def agenda(self) -> Dict[int, AgendaLine]:
        """Returns the actual agenda"""
        return self.run(AgendaCommand())

    def nexp(self):
        """Advance one step in the debug process."""
        return self.run(NexpCommand())

    def next(self):
        """Advance one step in the debug process."""
        return self.run(STRCommand("next"))

    def plan(self) -> SequentialPlan:
        """Returns the actual plan"""
        return self.run(PlanCommand())

    def stop(self):
        """Stops the debug process"""
        self.started = False
        if self.process:
            self.process.terminate()

        if self.thread_err.is_alive():
            self.thread_err.join()

        if self.thread_std.is_alive():
            self.thread_std.join()

        if self.temp_dir:
            self.temp_dir.cleanup()
        print("Debugger stopped")
