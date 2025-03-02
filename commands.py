import ax25

from textual.message import Message
from textual.widgets import Input
from textual.suggester import SuggestFromList

class CommandMessage(Message):
    """Message for a command"""

    def __init__(self, command: str, args: list) -> None:
        self.command = command
        self.args = args
        super().__init__()

class CommandInput(Input):
    """
    An input element for user commands.
    This element checks the validity of input and posts messages that the
    NetTerm app uses.
    """

    BORDER_TITLE="Command"
    BINDINGS = [ 
        ("up", "up()", "previous command"),
        ("down", "down()", "next command"),
    ]

    # Modes available as of NinoTNC v3.41 ordered from most to least preferred
    # FIXME: should this be in net.py?
    MODES = {
        '19.2K-C4FSK-IL2Pc': 0b0001,
        '9600-C4SK-IL2Pc':   0b0011,
        '9600-GFSK-IL2Pc':   0b0010,
        '9600-GFSK-AX.25':   0b0000,
        '4800-GFSK-IL2Pc':   0b0100,
        '3600-AQPSK-IL2Pc':  0b0101,
        '2400-QPSK-IL2Pc':   0b1011,
        '1200-BPSK-ILP2Pc':  0b1010,
        '1200-AFSK-AX.25':   0b0110,
        '600-QPSK-IL2Pc':    0b1001,
        '300-BPSK-IP2Pc':    0b1000,
        '300-AFSK-IL2Pc':    0b1110,
        '300-AFSK-AX.25':    0b1100,
    }

    AUTO = 'auto'
    MODE = 'mode'
    RMODE = 'rmode'
    QUIT = 'quit'
    TEST = 'test'
    NT_COMMANDS = {
        AUTO: {
            'names': ['auto', 'negotioate'],
            'suggest': "/auto CALL",
            'help': "switches to the best mode for connecting to CALL",
            'args': ['call'],
        },
        MODE: {
            'names': ['mode', 'speed'],
            'suggest': "/mode 1200-AFSK-AX.25",
            'help': "uses SETHW on the local NinoTNC to change the mode to one of:" +
                    ", ".join(MODES.keys()),
            'args': ['mode'],
        },
        QUIT: {
            'names': ['quit', 'exit', 'bye'],
            'suggest': "/quit",
            'help': "exits the program",
            'args': [], 
        },
        RMODE: {
            'names': ['rmode', 'rspeed', 'remote_mode', 'remote_speed'],
            'suggest': "/rmode CALL 1200-AFSK-AX.25",
            'help': "requests that a remote NinoTNC change its mode to one of:" +
                    ", ".join(MODES.keys()),
            'args': ['call', 'mode'],
        },
        TEST: {
            'names': ['test', 'ping'],
            'suggest': "/test CALL",
            'help': "sends a test packet to CALL",
            'args': ['call'],
        },
    }

    def __init__(self):
        # history state
        self.history = []
        self.searching_history = False
        self.history_index = 0
        self.prev_value = ""

        # suggestions
        suggestions = [self.NT_COMMANDS[command_id]['suggest'] for command_id in self.NT_COMMANDS]
        suggester = SuggestFromList(suggestions, case_sensitive=False)

        super().__init__(suggester=suggester)

    def action_up(self) -> None:
        # if we are not searching, but there's a history to search:
        # * start searching
        # * replace the text with the prev command
        # * store the text that we had
        if not self.searching_history and len(self.history) > 0: 
            self.searching_history = True
            self.history_index = len(self.history) - 1
            self.prev_value = self.value
            self.clear()
            self.insert(self.history[self.history_index], 0)
            return
        
        # if we are searching and we are not yet at the top
        # replace the text with the prev command
        if self.searching_history and self.history_index > 0:
            self.history_index -= 1
            self.clear()
            self.insert(self.history[self.history_index], 0)
            return

    def action_down(self) -> None:
        # if we are searching and we are not yet at the bottom
        # replace the text with the next command
        if self.searching_history and self.history_index < (len(self.history) - 1):
            self.history_index += 1
            self.clear()
            self.insert(self.history[self.history_index], 0)
            return

        # if we are searching and we're at the bottom:
        # * stop searching
        # * restore the text
        if self.searching_history and self.history_index >= (len(self.history) - 1):
           self.searching_history = False
           self.value = self.prev_value
           return

    def lookup_id(self, command) -> str | None:
        for command_id, command_dict in self.NT_COMMANDS.items():
            if command in command_dict['names']:
                return command_id
        return None

    def error(self, msg: str):
        self.notify(msg, severity='error')

    def on_input_submitted(self, submission: Input.Submitted) -> None:
        if submission.value == '':
            return

        if submission.value[0] == '/':
            params = submission.value[1:].split()
            command = params[0]

            # check the command
            command_id = self.lookup_id(command)
            if not command_id:
                self.error(f"Unknown command: {command}")
                return
            command_dict = self.NT_COMMANDS[command_id]

            # check the arguments
            args = params[1:] # take the command out of the arguments
            command_args = command_dict['args']

            # do we have enough?
            if len(args) < len(command_args):
                self.error(f"{command} command requires {len(command_args)} argument(s)")
                return

            # strip off any extra arguments
            args = args[:len(command_args)]

            # are the arguments valid?
            for index, arg_type in enumerate(command_args):
                if arg_type == 'call':
                    if not ax25.Address.valid_call(args[index]):
                        self.error(f"{args[index]} is not a valid call sign")
                        return
                elif arg_type == 'mode':
                    if args[index] not in self.MODES:
                        self.error(f"{args[index]} is not a valid mode")
                        return

            # post the message
            self.post_message(CommandMessage(command_id, args))

            # reset that input and add the submission to our history
            self.searching_history = False
            self.history.append(submission.value)
            self.clear()
