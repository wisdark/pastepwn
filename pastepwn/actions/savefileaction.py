# -*- coding: utf-8 -*-
import os

from pastepwn.util import TemplatingEngine
from .basicaction import BasicAction


class SaveFileAction(BasicAction):
    """Action to save each paste as a file named '<pasteID>.txt'"""
    name = "SaveFileAction"

    def __init__(self, path, file_ending=".txt", template=None):
        """
        Action to save each paste as a file named '<pasteID>.txt'
        If you want to store metadata within the file, use template strings
        > https://github.com/d-Rickyy-b/pastepwn/wiki/Templating-in-actions
        :param path: The directory in which the file(s) should be stored
        :param template: A template string describing how the paste variables should be filled in
        """
        super().__init__()
        self.path = path
        self.file_ending = file_ending
        self.template = template or "${body}"

    def perform(self, paste, analyzer_name=None, matches=None):
        """
        Stores the paste as a file
        :param paste: The paste passed by the ActionHandler
        :param analyzer_name: The name of the analyzer which matched the paste
        :param matches: List of matches returned by the analyzer
        :return: None
        """
        if not os.path.exists(self.path):
            os.makedirs(self.path)

        if self.file_ending.startswith("."):
            file_name = "{0}{1}".format(paste.key, self.file_ending)
        elif self.file_ending == "":
            file_name = str(paste.key)
        else:
            file_name = "{0}.{1}".format(paste.key, self.file_ending)

        content = TemplatingEngine.fill_template(paste, analyzer_name, template_string=self.template, matches=matches)
        with open(os.path.join(self.path, file_name), "w", encoding="utf-8") as file:
            file.write(content)
