from datetime import datetime

from textual.widgets import ContentSwitcher, ListView, ListItem, RichLog, Label
from textual.await_complete import AwaitComplete
from textual.css.query import NoMatches


class View(ContentSwitcher):
    """The main view"""

    def switch(self, view_id):
        """Switch to a different view based on the view_id"""

        self.border_title = self.query_one(f"#{view_id}").name
        self.current = view_id

    def append(self, view_id: str, view_name: str) -> AwaitComplete:
        new_view = RichLog(markup=True, wrap=True, id=view_id, name=view_name)
        return self.add_content(new_view)

    def write(self, view_id: str, msg: str) -> None:
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[green]{time}[/] {msg}"
        self.query_one(f"#{view_id}").write(msg)

    def exists(self, view_id: str) -> bool:
        """Returns true if a view exists"""
        try:
            self.query_one(f"#{view_id}")
        except NoMatches:
            return False
        return True
    
class ViewList(ListView):
    """A listing of views available"""

    BORDER_TITLE = "Views"

    def append(self, view_id: str, name: str | None = None) -> None:
        if not name:
            name = view_id
        super().append(ListItem(Label(name), id=view_id))
