from unittest import TestCase

import unified_planning
import unified_planning as up
from unified_planning.engines.results import PlanGenerationResultStatus
from unified_planning.io import PDDLReader
from unified_planning.io.hpdl.hpdl_reader import HPDLReader
from unified_planning.model.htn.hierarchical_problem import HierarchicalProblem, Method
from unified_planning.shortcuts import *

from up_siadex import SIADEXEngine


class SIADEXTest(TestCase):
    def test_siadex_hddl(self):

        reader = PDDLReader()
        problem = reader.parse_problem(
            "./domain.hddl",
            "./problem.hddl",
        )

        env = up.environment.get_env()
        env.factory.add_engine("siadex", __name__, "SIADEXEngine")

        with OneshotPlanner(name="siadex") as planner:
            result = planner.solve(problem)
            if (
                result.status
                == up.engines.PlanGenerationResultStatus.SOLVED_SATISFICING
            ):
                print("SIADEX returned: %s" % result.plan)
            else:
                print("No plan found.")

    def test_siadex_hpdl(self):
        reader = HPDLReader()
        problem = reader.parse_problem(
            "./domain.hpdl",
            "./problem.hpdl",
        )

        env = up.environment.get_env()
        env.factory.add_engine("siadex", __name__, "SIADEXEngine")

        with OneshotPlanner(name="siadex") as planner:
            result = planner.solve(problem)
            if (
                result.status
                == up.engines.PlanGenerationResultStatus.SOLVED_SATISFICING
            ):
                print("SIADEX returned: %s" % result.plan)
            else:
                print("No plan found.")

    def test_siadex_upf(self):
        htn = HierarchicalProblem()

        Location = UserType("Location")

        l1 = htn.add_object("l1", Location)
        l2 = htn.add_object("l2", Location)
        l3 = htn.add_object("l3", Location)
        l4 = htn.add_object("l4", Location)

        loc = Fluent("is_on", l=Location)
        htn.add_fluent(loc, default_initial_value=False)

        connected = Fluent("connected", l1=Location, l2=Location)
        htn.add_fluent(connected, default_initial_value=False)
        htn.set_initial_value(connected(l1, l2), True)
        htn.set_initial_value(connected(l2, l3), True)
        htn.set_initial_value(connected(l3, l4), True)
        htn.set_initial_value(connected(l4, l3), True)
        htn.set_initial_value(connected(l3, l2), True)
        htn.set_initial_value(connected(l2, l1), True)
        htn.set_initial_value(loc(l1), True)

        move = InstantaneousAction("move", l_from=Location, l_to=Location)
        l_from = move.parameter("l_from")
        l_to = move.parameter("l_to")
        move.add_precondition(loc(l_from))
        move.add_precondition(connected(l_from, l_to))
        move.add_effect(loc(l_from), False)
        move.add_effect(loc(l_to), True)
        htn.add_action(move)

        go = htn.add_task("go", target=Location)

        go_noop = Method("go-noop", target=Location)
        go_noop.set_task(go)
        target = go_noop.parameter("target")
        go_noop.add_precondition(loc(target))

        htn.add_method(go_noop)

        go_recursive = Method(
            "go-recursive", source=Location, inter=Location, target=Location
        )

        go_recursive.set_task(go, go_recursive.parameter("target"))
        source = go_recursive.parameter("source")
        inter = go_recursive.parameter("inter")
        target = go_recursive.parameter("target")

        go_recursive.add_precondition(loc(source))
        go_recursive.add_precondition(connected(source, inter))

        t1 = go_recursive.add_subtask(move, source, inter)
        t2 = go_recursive.add_subtask(go, target)
        go_recursive.set_ordered(t1, t2)
        htn.add_method(go_recursive)

        go1 = htn.task_network.add_subtask(go, l4)

        env = up.environment.get_env()
        env.factory.add_engine("siadex", __name__, "SIADEXEngine")

        with OneshotPlanner(name="siadex") as planner:
            result = planner.solve(htn)
            if (
                result.status
                == up.engines.PlanGenerationResultStatus.SOLVED_SATISFICING
            ):
                print("SIADEX returned: %s" % result.plan)
            else:
                print("No plan found.")
