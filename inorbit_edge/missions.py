# This module provides mission execution capabilities
#
# TODO(mike) implement pause/resume
# TODO(mike) report errors to cloud
# TODO(mike) report executor state
# TODO(mike) implement timeouts
# TODO(mike) use constants
#
import json
import logging
import threading
import time
from inorbit_edge.types import Pose, SpatialTolerance
from inorbit_edge.commands import (
    COMMAND_NAV_GOAL,
    COMMAND_CUSTOM_COMMAND,
    COMMAND_MESSAGE,
)

# Commands handled by this module
COMMAND_PAUSE = "inorbit_pause"
COMMAND_RESUME = "inorbit_resume"
COMMAND_RUN_MISSION = "inorbit_run_mission"
COMMAND_CANCEL_MISSION = "inorbit_cancel_mission"
COMMAND_EVENT = "inorbit_event"

# Mission states
MISSION_STATE_STARTING = "Starting"
MISSION_STATE_EXECUTING = "Executing"
MISSION_STATE_ABORTED = "Aborted"
MISSION_STATE_COMPLETED = "Completed"
MISSION_STATE_CANCELED = "Canceled"

# Mission status
MISSION_STATUS_OK = "OK"
MISSION_STATUS_ERROR = "Error"


class MissionsModule:
    """
    MissionsModule acts as the interface between the robot session and the
    MissionExecutor. Its main responsibility is handling commands from the robot
    session, parsing them and passing them to the executor.
    """

    def __init__(self, robot_session):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.robot_session = robot_session
        self.robot_session.register_command_callback(self.command_callback)
        self.executor = MissionExecutor(self.robot_session)

    def command_callback(self, command_name, args, options):
        if command_name != COMMAND_MESSAGE:
            return

        msg = args[0]
        cmd = msg.split(" ")[0]
        cmd_args = " ".join(msg.split(" ")[1:])

        # handle pause/resume
        if cmd == COMMAND_PAUSE:
            return self.handle_pause()
        elif cmd == COMMAND_RESUME:
            return self.handle_resume()

        # handle events
        if cmd == COMMAND_EVENT:
            return self.handle_event(cmd_args)

        # handle run/cancel mission
        if cmd == COMMAND_RUN_MISSION:
            return self.handle_run_mission(cmd_args)
        if cmd == COMMAND_CANCEL_MISSION:
            return self.handle_cancel_mission(cmd_args)

    def handle_pause(self):
        self.executor.pause()

    def handle_resume(self):
        self.executor.resume()

    def handle_event(self, args):
        self.executor.handle_event(args)

    def handle_run_mission(self, args):
        args = args.split(" ")
        if len(args) < 2:
            self.logger.error(
                f"Error: {COMMAND_RUN_MISSION} expects 2 arguments {str(args)}"
            )
            return
        mission_id = args[0]
        mission_program_json = " ".join(args[1:])
        try:
            mission_program = json.loads(mission_program_json)
            if mission_id == "null":
                mission_id = str(int(time.time() * 1000))
            mission = Mission(mission_id, mission_program, self.robot_session)
        except Exception:
            self.logger.error("Error parsing program", exc_info=True)
            return
        self.executor.run_mission(mission)

    def handle_cancel_mission(self, args):
        args = args.split(" ")
        if len(args) != 1:
            self.logger.error(
                f"Error: {COMMAND_CANCEL_MISSION} expects 1 argument {str(args)}"
            )
            return
        self.executor.cancel_mission(args[0])


class MissionExecutor:
    """
    MissionExecutor handles missions execution and enforces execution rules, like:
     - Can only run a mission if no mission is running
     - Can only cancel the current mission
    """

    def __init__(self, robot_session):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.robot_session = robot_session
        self.mission = None
        self.mutex = threading.Lock()
        self.is_idle = threading.Event()
        self.is_idle.set()
        self.paused = False

    def run_mission(self, mission):
        with self.mutex:
            if self.mission is not None:
                self.logger.warning(
                    f"Can't start mission {mission.id} while other mission\
                        {self.mission.id} is running"
                )
                return
            self.is_idle.clear()
            self.mission = mission
            if self.paused:
                # Start the mission paused if the executor is paused
                mission.pause()
            threading.Thread(
                target=self._run_mission_thread, args=(mission,), daemon=True
            ).start()

    def _run_mission_thread(self, mission):
        mission.execute()
        self.mission = None
        self.is_idle.set()

    def wait_until_idle(self, timeout=None):
        """
        Waits until the executor is idle.
        This method is mostly a helper for tests to wait for mission completion.
        """
        self.is_idle.wait(timeout)
        return self.is_idle.is_set()

    def cancel_mission(self, mission_id):
        with self.mutex:
            if self.mission is None:
                self.logger.warning("Can't cancel mission when no mission is running")
                return
            elif self.mission.id != mission_id and mission_id != "*":
                self.logger.warning(
                    f"Can't cancel mission {mission_id} because the id does not match\
                        running mission {self.mission.id}"
                )
            self.mission.cancel()
            self.mission = None
            self.is_idle.set()

    def handle_event(self, event):
        with self.mutex:
            if self.mission is not None:
                self.mission.handle_event(event)

    def pause(self):
        with self.mutex:
            self.paused = True
            if self.mission is not None:
                self.mission.pause()

    def resume(self):
        with self.mutex:
            self.paused = False
            if self.mission is not None:
                self.mission.resume()


class FailedMissionStepExecution(Exception):
    "Raised when mission step fails to execute"
    pass


class Mission:
    """
    Provides execution and tracking of a mission
    """

    def __init__(self, id, program, robot_session):
        """
        Initializes the mission from a mission program
        """
        self.id = id
        self.label = program["label"]
        self.start_ts = int(time.time()) * 1000
        self.end_ts = None
        self.robot_session = robot_session
        self.defaultStepTimeoutMs = None
        self.steps = self._build_steps(program)
        self.state = MISSION_STATE_STARTING
        self.status = MISSION_STATUS_OK
        self.current_step_idx = -1
        self.current_step = None
        self.data = {}
        # mutex for state, status and current step and reporting
        self.mutex = threading.Lock()
        self.enabled = threading.Event()
        self.enabled.set()

    def set_data(self, data: dict):
        """
        Adds data to this mission's data
        """
        self.data.update(data)

    def execute(self):
        """
        Runs this mission's steps
        """
        with self.mutex:
            if self.state == MISSION_STATE_STARTING:
                self.state = MISSION_STATE_EXECUTING
        for step_idx in range(0, len(self.steps)):
            with self.mutex:
                if self.state != MISSION_STATE_EXECUTING:
                    # Mission was aborted
                    break
                self.current_step_idx = step_idx
                self.current_step = self.steps[step_idx]
                self.report()
            # Wait if the mission is paused
            self.enabled.wait()
            # HACK(mike) sending two reports without waiting can cause issues
            # in the backend
            time.sleep(5)
            try:
                self.current_step.execute(self)
                if not self.current_step.success():
                    raise FailedMissionStepExecution()
            except Exception:
                with self.mutex:
                    if self.state == MISSION_STATE_EXECUTING:
                        self.state = MISSION_STATE_ABORTED
                    self.status = MISSION_STATUS_ERROR
                break
        with self.mutex:
            if self.state == MISSION_STATE_EXECUTING:
                self.state = MISSION_STATE_COMPLETED
                self.current_step_idx += 1
                self.current_step = None
            self.end_ts = int(time.time()) * 1000
            self.report()

    def build_report(self):
        """
        Builds a mission tracking report based on the mission state and progress
        """
        report = {
            "missionId": self.id,
            "inProgress": self.state == MISSION_STATE_EXECUTING,
            "state": self.state,
            "label": self.label,
            "startTs": self.start_ts,
            "data": self.data,
            "status": self.status,
        }
        if self.state == MISSION_STATE_EXECUTING:
            report["currentTaskId"] = str(self.current_step_idx)
        report["tasks"] = [
            {"taskId": str(i), "label": s.label} for i, s in enumerate(self.steps)
        ]

        if self.end_ts is not None:
            report["endTs"] = self.end_ts

        if self.current_step_idx is not None:
            report["completedPercent"] = self.current_step_idx / len(self.steps)
        else:
            report["completedPercent"] = 0
        return report

    def report(self):
        """
        Publishes the mission report
        """
        self.robot_session.publish_key_values(
            key_values={"mission_tracking": self.build_report()}, is_event=True
        )

    def handle_event(self, event):
        """
        Handles an external event
        """
        step = self.current_step
        if step is not None:
            step.handle_event(event)

    def cancel(self):
        """
        Cancels the execution of the mission
        """
        with self.mutex:
            if self.current_step is not None:
                self.current_step.cancel()
            self.state = MISSION_STATE_CANCELED
            self.status = MISSION_STATUS_OK
        # Resume to finish processing of cancellation
        self.resume()

    def pause(self):
        """
        Pauses mission execution. The current step is paused and no new steps are
        executed until the mission is resumed.
        """
        with self.mutex:
            self.enabled.clear()
            if self.current_step is not None:
                self.current_step.pause()

    def resume(self):
        """
        Resumes mission execution
        """
        with self.mutex:
            self.enabled.set()
            if self.current_step is not None:
                self.current_step.resume()

    def _build_steps(self, program):
        """
        Builds the list of mission step objects from a mission program
        """
        if "steps" not in program:
            return []
        steps = [self._build_step(s) for s in program["steps"]]
        return steps

    def _build_step(self, step_def):
        """
        Builds a mission step object from its definition
        """
        if (
            step_def["type"] == "Action"
            and step_def["action"]["type"] == "PublishToTopic"
        ):
            return MissionStepPublishToTopic.build_from_def(
                step_def, self.defaultStepTimeoutMs
            )
        if step_def["type"] == "Action" and step_def["action"]["type"] == "RunScript":
            return MissionStepRunScript.build_from_def(
                step_def, self.defaultStepTimeoutMs
            )
        if step_def["type"] == "Action" and step_def["action"]["type"] == "NavigateTo":
            return MissionStepNavigateTo.build_from_def(
                step_def, self.defaultStepTimeoutMs
            )
        if step_def["type"] == "WaitSeconds":
            return MissionStepWaitSeconds.build_from_def(step_def)
        if step_def["type"] == "SetData":
            return MissionStepSetData.build_from_def(
                step_def, self.defaultStepTimeoutMs
            )
        if step_def["type"] == "WaitEvent":
            return MissionStepWaitEvent.build_from_def(
                step_def, self.defaultStepTimeoutMs
            )
        raise Exception(f"Error build mission step {str(step_def)}")


class Step:
    """
    Base class for all mission steps. Steps can be executed and canceled.
    """

    def __init__(self, label, timeoutMs=None):
        self.label = label
        self.timeoutMs = timeoutMs

    def execute(self):
        pass

    def success(self):
        return True

    def cancel(self):
        pass

    def handle_event(self, event):
        pass

    def pause(self):
        """
        Stops the execution of this step. Note that only steps that make the robot
        move implement this method.
        """
        pass

    def resume(self):
        pass


class MissionStepPublishToTopic(Step):
    """
    Mission step that executes a publish message action
    """

    def __init__(self, label, message, timeoutMs):
        super().__init__(label, timeoutMs)
        self.message = message

    def execute(self, mission):
        mission.robot_session.dispatch_command(COMMAND_MESSAGE, [self.message])

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepPublishToTopic(
            step_def["label"],
            step_def["action"]["message"],
            step_def.get("timeoutMs", defaultTimeoutMs),
        )


class MissionStepSetData(Step):
    """
    Mission step that adds some data to the mission
    """

    def __init__(self, label, data: dict, timeoutMs):
        super().__init__(label, timeoutMs)
        self.data = data

    def execute(self, mission):
        mission.set_data(self.data)

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepSetData(
            step_def["label"],
            step_def["data"],
            step_def.get("timeoutMs", defaultTimeoutMs),
        )


class MissionStepRunScript(Step):
    """
    Mission step that executes a custom command action
    """

    def __init__(self, label, fileName, args, timeoutMs):
        super().__init__(label, timeoutMs)
        self.fileName = fileName
        self.args = args

    def execute(self, mission):
        mission.robot_session.dispatch_command(
            COMMAND_CUSTOM_COMMAND, [self.fileName, self.args]
        )

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepRunScript(
            step_def["label"],
            step_def["action"]["fileName"],
            step_def["action"]["args"],
            step_def.get("timeoutMs", defaultTimeoutMs),
        )


class MissionStepWaitSeconds(Step):
    """
    Mission step that waits the specified seconds
    """

    def __init__(self, label, waitTimeSeconds):
        super().__init__(label)
        self.waitTimeSeconds = waitTimeSeconds
        self.event = threading.Event()

    def execute(self, mission):
        self.event.wait(self.waitTimeSeconds)

    def build_from_def(step_def):
        return MissionStepWaitSeconds(
            step_def["label"],
            step_def["seconds"],
        )

    def success(self):
        return not self.event.is_set()

    def cancel(self):
        super().cancel()
        self.event.set()


class MissionStepNavigateTo(Step):
    """
    Mission step that tells the robot to go to a waypoint and waits until the
    waypoint is reached
    """

    def __init__(self, label, waypoint, tolerance, timeoutMs):
        super().__init__(label, timeoutMs)
        self.waypoint = Pose(
            x=waypoint["x"],
            y=waypoint["y"],
            theta=waypoint["theta"],
            frame_id=waypoint["frameId"],
        )
        self.tolerance = SpatialTolerance(
            positionMeters=tolerance["positionMeters"],
            angularRadians=tolerance["angularRadians"],
        )
        self.mission = None
        self.canceled = False

    def _go_to_waypoint(self):
        if self.mission is None:
            # Can't go to the waypoint before knowing the mission
            return
        self.mission.robot_session.dispatch_command(
            command_name=COMMAND_NAV_GOAL,
            args=[
                {
                    "x": self.waypoint.x,
                    "y": self.waypoint.y,
                    "theta": self.waypoint.theta,
                    "frameId": self.waypoint.frame_id,
                }
            ],
        )

    def execute(self, mission):
        self.mission = mission
        self._go_to_waypoint()
        while True:
            if mission.robot_session.reached_waypoint(self.waypoint, self.tolerance):
                return
            if self.canceled:
                return
            time.sleep(1)

    def pause(self):
        # It's up to the integrator to handle pause to avoid the robot from moving
        pass

    def resume(self):
        self._go_to_waypoint()

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepNavigateTo(
            step_def["label"],
            step_def["action"]["waypoint"],
            step_def["tolerance"],
            step_def.get("timeoutMs", defaultTimeoutMs),
        )

    def cancel(self):
        self.canceled = True
        super().cancel()

    def success(self):
        return not self.canceled


class MissionStepWaitEvent(Step):
    """
    Mission step that waits for an external event
    """

    def __init__(self, label, event, timeoutMs):
        super().__init__(label)
        self.awaited_event = event
        self.timeoutS = timeoutMs * 1000 if timeoutMs is not None else None
        self.event = threading.Event()
        self.canceled = False

    def execute(self, mission):
        self.event.wait(self.timeoutS)

    def success(self):
        return self.event.is_set() and not self.canceled

    def handle_event(self, event):
        if self.awaited_event == event:
            self.event.set()

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepWaitEvent(
            step_def["label"],
            step_def["event"],
            step_def.get("timeoutMs", defaultTimeoutMs),
        )

    def cancel(self):
        super().cancel()
        self.canceled = True
        self.event.set()
