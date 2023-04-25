# TODO(mike) implement pause/resume
# TODO(mike) implement events
# TODO(mike) report errors to cloud
# TODO(mike) report executor state
import json
import logging
import threading
import time

# Commands handled by this module
COMMAND_PAUSE = "inorbit_pause"
COMMAND_RESUME = "inorbit_resume"
COMMAND_RUN_MISSION = "inorbit_run_mission"
COMMAND_CANCEL_MISSION = "inorbit_cancel_mission"
COMMAND_EVENT = "inorbit_event"

class MissionsModule:
    """
    MissionsModule acts as the interface between the robot session and the
    MissionExecutor. Its main responsibility is handling commands from the robot
    session, parsing them and passing them to the executor.
    """
    def __init__(self, robot_session):
        self.logger = logging.getLogger(__class__.__name__)
        self.robot_session = robot_session
        self.robot_session.register_command_callback(self.command_callback)
        self.executor = MissionExecutor(self.robot_session)

    def command_callback(self, command_name, args, options):
        if command_name != "message":
            return
        
        msg = args
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
        pass

    def handle_resume(self):
        pass

    def handle_event(self, args):
        pass

    def handle_run_mission(self, args):
        args = args.split(" ")
        if len(args) < 2:
            self.logger.error(f"Error: {COMMAND_RUN_MISSION} expects 2 arguments {str(args)}")
            return
        mission_id = args[0]
        mission_program_json = " ".join(args[1:])
        try:
            mission_program = json.loads(mission_program_json)
            mission = Mission(mission_id, mission_program, self.robot_session)
        except Exception as e:
            self.logger.error(f"Error parsing program", exc_info=True)
            return
        self.executor.run_mission(mission)

    def handle_cancel_mission(self, args):
        if len(args) != 1:
            self.logger.error(f"Error: {COMMAND_CANCEL_MISSION} expects 1 argument {str(args)}")
            return
        self.executor.cancel_mission(args[0])


class Mission:
    def __init__(self, id, program, robot_session):
        self.id = id
        self.robot_session = robot_session
        self.defaultStepTimeoutMs = -1
        self.steps = self._build_steps(program)
        self.state = ""
        self.current_step = None

    def execute(self):
        for step in self.steps:
            self.current_step = step
            self.current_step.execute(self.robot_session)

    def cancel(self):
        pass

    def _build_steps(self, program):
        if "steps" not in program:
            return []
        steps = [self._build_step(s) for s in program["steps"]]
        return steps

    def _build_step(self, step_def):
        if step_def["type"] == "Action" and step_def["action"]["type"] == "PublishToTopic":
            return MissionStepPublishToTopic.build_from_def(step_def, self.defaultStepTimeoutMs)
        if step_def["type"] == "Action" and step_def["action"]["type"] == "RunScript":
            return MissionStepRunScript.build_from_def(step_def, self.defaultStepTimeoutMs)
        raise Exception(f"Error build mission step {str(step_def)}")
                

class Step:
    def __init__(self, label, timeoutMs=-1):
        self.label = label
        self.timeoutMs = timeoutMs

    def execute(self):
        pass

    def success(self):
        return True

    def cancel(self):
        pass


class MissionStepPublishToTopic(Step):
    def __init__(self, label, timeoutMs, message):
        super().__init__(label, timeoutMs)
        self.message = message

    def execute(self, robot_session):
        robot_session.dispatch_command("message", self.message)

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepPublishToTopic(
            step_def["label"],
            step_def.get("timeoutMs", defaultTimeoutMs),
            step_def["action"]["message"]
        )

class MissionStepRunScript(Step):
    def __init__(self, label, fileName, args, timeoutMs):
        super().__init__(label, timeoutMs)
        self.fileName = fileName
        self.args = args

    def execute(self, robot_session):
        robot_session.dispatch_command("customCommand", [self.fileName, self.args])

    def build_from_def(step_def, defaultTimeoutMs):
        return MissionStepRunScript(
            step_def["label"],
            step_def["action"]["fileName"],
            step_def["action"]["args"],
            step_def.get("timeoutMs", defaultTimeoutMs),
        )


class MissionExecutor:
    """
    MissionExecutor handles missions execution and enforces execution rules, like:
     - Can only run a mission if no mission is running
     - Can only cancel the current mission
    """
    def __init__(self, robot_session):
        self.logger = logging.getLogger(__class__.__name__)
        self.robot_session = robot_session
        self.mission = None
        self.state = "idle"
        self.mutex = threading.Lock()
        self.is_idle = threading.Event()
        self.is_idle.set()

    def run_mission(self, mission):
        with self.mutex:
            if self.mission is not None:
                self.logger.warning(f"Can't start mission {mission.id} while other mission {self.mission.id} is running")
                return
            self.is_idle.clear()
            threading.Thread(target=self._run_mission_thread, args=(mission,), daemon=True).start()

    def _run_mission_thread(self, mission):
        mission.execute()
        self.is_idle.set()

    def wait_until_idle(self, timeout=None):
        """
        Waits until the executor is idle.
        This method is mostly a helper for tests to wait for mission completion.
        """
        self.is_idle.wait(timeout)

    def cancel_mission(self, mission_id):
        with self.mutex:
            if self.mission is None:
                self.logger.warning(f"Can't cancel mission when no mission is running")
            elif self.mission.id != mission_id:
                self.logger.warning(f"Can't cancel mission {mission_id} because the id does not match running mission {self.mission.id}")
            self.mission.cancel()
            self.mission = None
            self.is_idle.set()