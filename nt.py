from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, ListView
from textual.containers import VerticalGroup, HorizontalGroup, VerticalScroll
from textual.message import Message
import ax25 

import pyham_kiss.kiss as kiss
from net import Net, LogFrame
from views import View, ViewList
from commands import CommandInput, CommandMessage


class NetTerm(App):
    """A TUI Python Terminal for TNCs"""

    CSS_PATH = "nt.tcss"

    def debug(self, msg: str) -> None:
        self.view.write("debug", msg)

    async def on_log_frame(self, lf: LogFrame) -> None:
        frame = lf.frame
        # make a list of views this frame will be written to, creating as needed

        # each call should have their own view
        view_list = {
            (f"call-{frame.src}", f"Traffic to/from {frame.src}", f"{frame.src}"),
            (f"call-{frame.dst}", f"Traffic to/from {frame.dst}", f"{frame.dst}"),
        }
        for (view_id, view_name, list_name) in view_list:
            if not self.view.exists(view_id):
                await self.append_view(view_id, view_name, list_name) 

        # the conversation should have a view, either src-dst or dst-src
        src_first = (
            f"call-{frame.src}-call-{frame.dst}",
            f"Traffic between {frame.src} and {frame.dst}",
            f"{frame.src} {frame.dst}",
        )
        dst_first = (
            f"call-{frame.dst}-call-{frame.src}",
            f"Traffic between {frame.dst} and {frame.src}",
            f"{frame.dst} {frame.src}",
        )
        if self.view.exists(src_first[0]):
            view_list.add(src_first)
        else:
            if self.view.exists(dst_first[0]):
                view_list.add(dst_first)
            else:
                await self.append_view(src_first[0], src_first[1], src_first[2])
                view_list.add(src_first)

        # create the TNC 2 style message we print
        # https://raw.githubusercontent.com/wb2osz/aprsspec/main/Understanding-APRS-Packets.pdf
        # https://wiki.oarc.uk/packet:reading_traces

        # src, dst, and repeaters
        msg = f"{frame.src}>{frame.dst}"
        if frame.via:
            for repeater in frame.via:
                msg += f",{repeater}"

        # control information
        control = frame.control
        if control.frame_type == ax25.FrameType.RR:
            frame_type = "RR"
        elif control.frame_type == ax25.FrameType.RNR:
            frame_type = "RNR"
        elif control.frame_type == ax25.FrameType.REJ:
            frame_type = "REJ"
        elif control.frame_type == ax25.FrameType.SREJ:
            frame_type = "SREJ"
        elif control.frame_type == ax25.FrameType.TEST:
            frame_type = "TEST"
        elif control.frame_type == ax25.FrameType.UI:
            frame_type = "UI"
        else:
            frame_type = ""
        poll_final = "P" if control.poll_final else "F"
        msg += f" <{frame_type} {poll_final}>"

        # the data
        msg += f":{frame.data.decode('utf-8', errors='replace')}"

        # send the msg to every applicable view
        for view_id, view_name, list_name in view_list:
            self.view.write(view_id, msg)
        self.view.write("all", msg)

    async def append_view(self, view_id: str, view_name: str, list_name: str):
        await self.view.append(view_id, view_name)
        self.view_list.append(view_id, list_name)

    async def on_ready(self) -> None:
        # store the instances of widgets we will use
        self.view = self.query_one("View")
        self.view_list = self.query_one("ViewList")

        # setup default views
        await self.append_view("all", "All Traffic", "All")
        await self.append_view("debug", "Debug Output", "Debug")
        self.view.switch("all")
        self.view_list.index = 0

        # set up the Net class
        self.net = Net(app, "N2BP")

    async def on_command_message(self, msg: CommandMessage):
        if msg.command == CommandInput.AUTO:

            # send a test packet
            # expect a response
            pass
        elif msg.command == CommandInput.MODE:
            self.net.set_hw_mode(msg.args[0])
        elif msg.command == CommandInput.QUIT:
            await self.app.action_quit()
        elif msg.command == CommandInput.RMODE:
            self.net.send_rmode_command(msg.args[0], msg.args[1])
        elif msg.command == CommandInput.TEST:
            self.net.send_test_command(msg.args[0], "Testing from NetTerm")

    def on_list_view_highlighted(self, event: ListView.Highlighted):
        self.view.switch(event.item._id)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""

        yield Header()
        yield Footer()
        yield VerticalGroup(
            HorizontalGroup(
                ViewList(),
                View(),
            ),
            CommandInput(),
        )


if __name__ == "__main__":
    app = NetTerm()
    app.run()
