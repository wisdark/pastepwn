import logging
import sys
from queue import Queue
from signal import SIGABRT, SIGINT, SIGTERM, signal
from threading import Event
from time import sleep

from pastepwn.actions import DatabaseAction
from pastepwn.analyzers import AlwaysTrueAnalyzer
from pastepwn.core import ActionHandler, PasteDispatcher, ScrapingHandler
from pastepwn.scraping.pastebin import PastebinScraper
from pastepwn.util import Request, enforce_ip_version


class PastePwn:
    """Represents an instance of the pastepwn core module"""

    def __init__(self, database=None, proxies=None, store_all_pastes=True, ip_version=None):
        """
        Basic PastePwn object handling the connection to pastebin and all the analyzers and actions
        :param database: Database object extending AbstractDB
        :param proxies: Dict of proxies as defined in the requests documentation
        :param store_all_pastes: Bool to decide if all pastes should be stored into the db
        :param ip_version: The IP version pastepwn should use (4|6)
        """
        self.logger = logging.getLogger(__name__)
        self.is_idle = False
        self.database = database
        self.paste_queue = Queue()
        self.action_queue = Queue()
        self.error_handlers = []
        self.onstart_handlers = []
        self.__exception_event = Event()
        self.__request = Request(proxies)  # initialize singleton

        # We are trying to enforce a certain version of the Internet Protocol
        enforce_ip_version(ip_version)

        # Usage of ipify to get the IP - Uses the X-Forwarded-For Header which might
        # lead to issues with proxies
        try:
            ip = self.__request.get("https://api.ipify.org")
        except Exception as e:
            ip = None
            self.logger.warning(f"Could not fetch public IP via ipify: {e}")

        if ip:
            self.logger.info(f"Your public IP is {ip}")

        self.scraping_handler = ScrapingHandler(paste_queue=self.paste_queue, exception_event=self.__exception_event)
        self.paste_dispatcher = PasteDispatcher(paste_queue=self.paste_queue, action_queue=self.action_queue, exception_event=self.__exception_event)
        self.action_handler = ActionHandler(action_queue=self.action_queue, exception_event=self.__exception_event)

        if self.database is not None and store_all_pastes:
            # Save every paste to the database with the AlwaysTrueAnalyzer
            self.logger.info("Database provided! Storing pastes in there.")
            database_action = DatabaseAction(self.database)
            always_true = AlwaysTrueAnalyzer(database_action)
            self.add_analyzer(always_true)
        elif store_all_pastes:
            self.logger.info("No database provided!")
        else:
            self.logger.info("Not storing all pastes!")

    def add_scraper(self, scraper, restart_scraping=False):
        """Adds a scraper to the list of scrapers. Scraping handler must be restarted for this to take effect.
        :param scraper: Instance of a BasicScraper
        :param restart_scraping: Indicates if the scraping handler should be restarted. Not setting this option results in your scraper not being started.
        :return: None
        """
        scraper.init_exception_event(self.__exception_event)
        self.scraping_handler.add_scraper(scraper, restart_scraping)

    def add_analyzer(self, analyzer):
        """Adds a new analyzer to the list of analyzers
        :param analyzer: Instance of a BasicAnalyzer
        :return: None
        """
        self.paste_dispatcher.add_analyzer(analyzer)

    def add_error_handler(self, error_handler):
        """
        Adds an error handler which will be called when an error happens
        :param error_handler: Callable to be called when an error happens
        :return: None
        """
        if not callable(error_handler):
            self.logger.error("The error handler you passed is not a function!")
            return

        self.error_handlers.append(error_handler)

    def add_onstart_handler(self, onstart_handler):
        """Add a function as onstart_handler"""
        if not callable(onstart_handler):
            self.logger.error("The onstart handler you passed is not a function!")
            return

        self.onstart_handlers.append(onstart_handler)

    def start(self):
        """Starts the pastepwn instance"""
        if self.__exception_event.is_set():
            self.logger.error("An exception occured. Aborting the start of PastePwn!")
            sys.exit(1)
        if not self.scraping_handler.scrapers:
            pastebinscraper = PastebinScraper()
            self.add_scraper(pastebinscraper, restart_scraping=True)
        self.scraping_handler.start()
        self.paste_dispatcher.start()
        self.action_handler.start()

        for onstart_handler in self.onstart_handlers:
            try:
                onstart_handler()
            except Exception:
                self.logger.exception("Onstart handler %s failed. Pastepwn is still running.", onstart_handler.__name__)

    def stop(self):
        """Stops the pastepwn instance"""
        self.scraping_handler.stop()
        self.paste_dispatcher.stop()
        self.action_handler.stop()
        self.is_idle = False

    def signal_handler(self, signum, frame):
        """Handler method to handle signals"""
        self.is_idle = False
        self.logger.info(f"Received signal {signum}, stopping...")
        self.stop()

    def idle(self, stop_signals=(SIGINT, SIGTERM, SIGABRT)):
        """Blocks until one of the signals are received and stops the updater.
        Thanks to the python-telegram-bot developers - https://github.com/python-telegram-bot/python-telegram-bot/blob/2cde878d1e5e0bb552aaf41d5ab5df695ec4addb/telegram/ext/updater.py#L514-L529
        :param stop_signals: The signals to which the code reacts to
        """
        self.is_idle = True
        self.logger.info("In Idle!")

        for sig in stop_signals:
            signal(sig, self.signal_handler)

        while self.is_idle:
            if self.__exception_event.is_set():
                self.logger.warning("An exception occurred. Calling exception handlers and going down!")
                for handler in self.error_handlers:
                    # call the error handlers in case of an exception
                    handler()
                self.is_idle = False
                self.stop()
                return

            sleep(1)
