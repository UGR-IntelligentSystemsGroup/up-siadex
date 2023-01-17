import os
import subprocess
import tempfile
import threading
import time
from abc import ABC
from queue import Empty, Queue
from typing import List

import pkg_resources
import unified_planning as up
from unified_planning.io.hpdl.hpdl_writer import HPDLWriter
from unified_planning.model.htn.hierarchical_problem import HierarchicalProblem


class ICommand(ABC):
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
        err: List["up.model.Fluent"],
    ):
        err = [er for er in err if not er.startswith("(***")]
        err = [er for er in err if not er.startswith("\n")]
        result = []
        for pre in err:
            pre = pre.replace("(", "").replace(")", "").replace("\n", "").split(" ")
            if pre[0][-1] == "_":
                pre[0] = pre[0][:-1]
            fluent = problem.fluent(pre[0].replace("_", "-"))
            parameters = []
            for obj in pre[1:]:
                obj = obj.replace("_", "-")
                parameters.append(problem.object(obj))
            result.append(fluent(*parameters))
        return result


class SIADEXDebugger:
    std_q = Queue()
    err_q = Queue()
    problem: "up.model.AbstractProblem" = None
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

    def state(self):
        """Returns a list of parametrized fluents that represents the actual state"""
        return self.run(StateCommand())

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
