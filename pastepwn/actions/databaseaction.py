from .basicaction import BasicAction


class DatabaseAction(BasicAction):
    """Action to save a paste to a database"""

    name = "DatabaseAction"

    def __init__(self, database):
        super().__init__()
        self.database = database

    def perform(self, paste, analyzer_name=None, matches=None):
        """Store an incoming paste in the database"""
        self.database.store(paste)
