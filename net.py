import threading
from textual.message import Message
from textual.app import App
import ax25

import pyham_kiss.kiss as kiss
from commands import CommandInput

UNPROTO_PID = 0xF0

DEFAULT_MODE = '1200-AFSK-AX.25'
MODE_TIMEOUT = 30

class LogFrame(Message):
    """Message for logging a sent/received frame"""

    def __init__(self, frame: ax25.Frame) -> None:
        self.frame = frame
        super().__init__()

class Log():
    """
    Stack action that sends LogFrame messages for every frame that comes
    in and then passes the unchanged frame out. Runs forever.
    """

    def __init__(self, app):
        self.app = app

    def frame_received(self, frame: ax25.Frame) -> bool:
        self.app.post_message(LogFrame(frame))
        return True

    def second_passed(self) -> bool:
        return True

    def __str__(self):
        return f"Log()"

class TestReply():
    """
    Stack action that replies to TEST commands and does not pass on the
    frame. Runs forever.
    """

    def __init__(self, app, net, our_call):
        self.app = app
        self.net = net
        self.our_call = our_call

    def frame_received(self, frame: ax25.Frame) -> bool:
        control = frame.control
        frame_type = control.frame_type
        poll_final = control.poll_final
        dst = frame.dst
        if frame_type == ax25.FrameType.TEST and poll_final and str(dst) == self.our_call:
            self.app.debug(f"{self} sending reponse to TEST frame")
            self.net.send_test_response(frame)
        return True

    def second_passed(self) -> bool:
        return True

    def __str__(self):
        return f"TestReply()"

class Mode():
    """
    Stack action that temporarily changes the mode
    """

    def __init__(self, app, net, mode_id, seconds):
        self.app = app
        self.net = net
        self.mode_id = mode_id
        self.seconds = seconds
        self.seconds_left = seconds

        self.net.set_hw_mode(mode_id)

    def frame_received(self, frame: ax25.Frame) -> bool:
        self.seconds_left = self.seconds
        return True

    def second_passed(self) -> bool:
        self.seconds_left -= 1
        if self.seconds_left > 0:
            return True
        self.app.debug("Mode timed out")
        self.net.set_hw_mode(DEFAULT_MODE)
        return False

    def __str__(self) -> str:
        return f"Mode({self.mode_id}, {self.seconds}, {self.seconds_left})"

class ModeAdjust():
    """
    Stack action that adjusts the mode in response to RMODE commands. Runs
    indefinitely.
    """

    def __init__(self, app, net, our_call):
        self.app = app
        self.net = net
        self.our_call = our_call

    def frame_received(self, frame: ax25.Frame) -> bool:
        control = frame.control
        frame_type = control.frame_type
        poll_final = control.poll_final
        dst = frame.dst
        data = frame.data.decode('utf-8', errors='replace')
        if (frame_type == ax25.FrameType.UI and poll_final and
            str(dst) == self.our_call and data[:6] == "RMODE "):

            mode_id = data[6:]
            self.app.debug(f"Received RMODE {mode_id} command")
            if mode_id not in CommandInput.MODES:
                self.app.debug("Invalid mode ID")
            else:
                # Remove any other Modes in our stack
                # TODO: When connections are implemented don't switch mode if
                # there's a connection in the stack
                for stack_action in list(self.net.stack):
                    if type(stack_action) == Mode:
                        self.net.stack.remove(stack_action)
                # Put a Mode (which is temporary) on the stack
                self.net.stack.append(Mode(self.app, self.net, mode_id, MODE_TIMEOUT))
        return True

    def second_passed(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"ModeAdjust()"

class ConnectReply():
    """
    Stack action that waits for connection requests and starts connections
    if possible
    """

    def __init__(self, app: App, net: Net, our_call: str):
        self.app = app
        self.net = net
        self.our_call = our_call

    def frame_received(self, frame: ax25.Frame):
        control = frame.control
        frame_type = control.frame_type
        poll_final = control.poll_final
        dst = frame.dst
        if (frame_type == ax25.FrameType.SABM and poll_final and
            str(dst) == self.our_call):
            self.app.debug("Responding to connection request")
            ua_control = ax25.Control(ax25.FrameType.UA, poll_final=False)
            frame = ax25.Frame(dst, self.our_call, control=control)
            self.net.send(frame)

    def second_passed(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"ConnectReply()"


class Net():
    """Additional AX.25 networking for NetTerm"""

    def __init__(self, app, our_call):
        self.our_call = our_call
        self.app = app

        def data_received(kiss_port, data):
            """
            This WILL run in another thread. Use messages to communicate
            with the app.
            """

            #TODO: catch ax25 exceptions
            frame = ax25.Frame.unpack(data)
            self.frame_received(frame)

        self.connection = kiss.Connection(data_received)
        #net.connection.connect_to_serial()
        self.connection.connect_to_server("127.0.0.1", 8001)
        app.debug("Connected to TNC")

        # setup the initial stack
        self.stack = [
            Log(app),
            TestReply(app, self, our_call),
            ModeAdjust(app, self, our_call),
            ConnectReply(app, self, our_call),
        ]

        # start the timer
        t = threading.Timer(1.0, self.second_passed)
        t.daemon = True
        t.start()

    def second_passed(self):
        """
        Every second runs second_passed() for each stack action in the stack,
        removing stack actions that do not return True.
        """

        # NOTE: We're working on a COPY of the stack so we can remove things
        #       as we iterate.
        for stack_action in list(self.stack):
            if not stack_action.second_passed():
                self.stack.remove(stack_action)

        # schedule yourself to run in another second (yes, this will drift)
        t = threading.Timer(1.0, self.second_passed)
        t.daemon = True
        t.start()

    def frame_received(self, frame):
        """
        Runs the frame_recieved() in each stack action and remove it if it
        doesn't return True.
        """
       
        # NOTE: We're working on a COPY of the stack so we can remove things
        #       as we iterate.
        for stack_action in list(self.stack):
            self.app.debug(f"Passing frame to {stack_action}")
            result = stack_action.frame_received(frame)
            if not result:
                self.stack.remove(stack_action)
                break

    def send(self, frame: ax25.Frame) -> None:
        """Logs and sends a frame"""

        # log the frame
        self.app.post_message(LogFrame(frame))

        # if the frame is addressed to ourselves, cut out the TNC
        if str(frame.dst) == self.our_call:
            self.frame_received(frame)
            return

        # otherwise send it out via the TNC
        self.connection.send_data(frame.pack())

    def send_test_command(self, dst_call: str, data: str) -> None:
        """Sends out a test command"""

        control = ax25.Control(ax25.FrameType.TEST, poll_final=True)
        frame = ax25.Frame(dst_call, self.our_call, control=control,
                           pid=UNPROTO_PID, data=data.encode('utf-8'))
        self.send(frame)

    def send_test_response(self, command_frame: ax25.Frame) -> None:
        """Sends out a test response with the data in the command_frame"""

        control = ax25.Control(ax25.FrameType.TEST, poll_final=False)
        response_frame = ax25.Frame(command_frame.src, self.our_call,
                                    control=control, pid=UNPROTO_PID,
                                    data=command_frame.data)
        self.send(response_frame)

    def send_rmode_command(self, dst_call: str, mode_id: str) -> None:
        """
        Sends a command to a remote station asking them to change their mode
        """

        control = ax25.Control(ax25.FrameType.UI, poll_final=True)
        frame = ax25.Frame(dst_call, self.our_call, control=control,
                           pid=UNPROTO_PID,
                           data=f"RMODE {mode_id}".encode('utf-8'))
        self.send(frame)

    def set_hw_mode(self, mode_id: str) -> None:
        """
        Uses the SETHW command to temporarily change the mode on a NinoTNC
        """

        # FIXME: could we have threading issues with this app access?
        hw = CommandInput.MODES[mode_id] + 16 # set it temporarily
        self.app.debug(f"Setting mode to {mode_id}")
        self.connection.set_hardware(int(hw).to_bytes(1,'big'))
        self.app.sub_title = mode_id
