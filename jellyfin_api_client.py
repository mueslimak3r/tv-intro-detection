'''
Big thanks to the jellyfin/jellyfin-mpv-shim devs for most of the code in this file!
Adapted from:
https://github.com/jellyfin/jellyfin-mpv-shim/blob/ed8a61d6984c79ac81ef9db1f84af940ca036e0f/jellyfin_mpv_shim/clients.py
Main project:
https://github.com/jellyfin/jellyfin-mpv-shim
'''

import sys
import json
import uuid as UUID
import time
import logging
import re
from pathlib import Path

from jellyfin_apiclient_python import JellyfinClient
from jellyfin_apiclient_python.connection_manager import CONNECTION_STATE
from getpass import getpass
from typing import Optional

# server_url = os.environ['JELLYFIN_URL']
# server_username = os.environ['JELLYFIN_USERNAME']
# server_password = os.environ['JELLYFIN_PASSWORD']

jellyfin_client_manager = None
jellyfin_current_client = None


APP_NAME = "tv-intro-detection"
USER_APP_NAME = "TV Intro Detection"
CLIENT_VERSION = "0.0.1"
USER_AGENT = "tv-intro-detection/%s" % CLIENT_VERSION
CAPABILITIES = {
    "PlayableMediaTypes": "",
    "SupportsMediaControl": False,
    "SupportedCommands": (),
}

connect_retry_mins = 0

ignore_ssl_cert = False

credentials_location = Path(Path(__file__).parent.resolve() / 'cred.json')

log = logging.getLogger("clients")
path_regex = re.compile("^(https?://)?([^/:]+)(:[0-9]+)?(/.*)?$")


def expo(max_value: Optional[int] = None):
    n = 0
    while True:
        a = 2 ** n
        if max_value is None or a < max_value:
            yield a
            n += 1
        else:
            yield max_value


class ClientManager(object):
    def __init__(self):
        self.callback = lambda client, event_name, data: None
        self.credentials = []
        self.clients = {}
        self.usernames = {}
        self.is_stopping = False

    def cli_connect(self):
        is_logged_in = self.try_connect()
        add_another = False

        if "add" in sys.argv:
            add_another = True

        while not is_logged_in or add_another:
            server = input(_("Server URL: "))
            username = input(_("Username: "))
            password = getpass(_("Password: "))

            is_logged_in = self.login(server, username, password)

            if is_logged_in:
                log.info(_("Successfully added server."))
                add_another = input(_("Add another server?") + " [y/N] ")
                add_another = add_another in ("y", "Y", "yes", "Yes")
            else:
                log.warning(_("Adding server failed."))

    @staticmethod
    def client_factory():
        client = JellyfinClient(allow_multiple_clients=True)
        client.config.data["app.default"] = True
        client.config.app(
            USER_APP_NAME, CLIENT_VERSION, USER_APP_NAME, str(UUID.uuid4())
        )
        client.config.data["http.user_agent"] = USER_AGENT
        client.config.data["auth.ssl"] = not ignore_ssl_cert
        return client

    def _connect_all(self):
        is_logged_in = False
        for server in self.credentials:
            if self.connect_client(server):
                is_logged_in = True
        return is_logged_in

    def try_connect(self):
        if credentials_location.exists():
            with credentials_location.open('r') as cf:
                self.credentials = json.load(cf)

        if "Servers" in self.credentials:
            credentials_old = self.credentials
            self.credentials = []
            for server in credentials_old["Servers"]:
                server["uuid"] = str(UUID.uuid4())
                server["username"] = ""
                self.credentials.append(server)

        is_logged_in = self._connect_all()
        if connect_retry_mins and not is_logged_in:
            log.warning(
                "Connection failed. Will retry for {0} minutes.".format(
                    connect_retry_mins
                )
            )
            for attempt in range(connect_retry_mins * 2):
                time.sleep(30)
                is_logged_in = self._connect_all()
                if is_logged_in:
                    break

        return is_logged_in

    def save_credentials(self):
        if credentials_location.exists():
            with credentials_location.open('w') as cf:
                json.dump(self.credentials, cf)

    def login(
        self, server: str, username: str, password: str, force_unique: bool = False
    ):
        if server.endswith("/"):
            server = server[:-1]
        
        protocol, host, port, path = path_regex.match(server).groups()

        if not protocol:
            log.warning("Adding http:// because it was not provided.")
            protocol = "http://"

        if protocol == "http://" and not port:
            log.warning("Adding port 8096 for insecure local http connection.")
            log.warning(
                "If you want to connect to standard http port 80, use :80 in the url."
            )
            port = ":8096"

        server = "".join(filter(bool, (protocol, host, port, path)))

        client = self.client_factory()
        client.auth.connect_to_address(server)
        result = client.auth.login(server, username, password)
        if "AccessToken" in result:
            credentials = client.auth.credentials.get_credentials()
            server = credentials["Servers"][0]
            if force_unique:
                server["uuid"] = server["Id"]
            else:
                server["uuid"] = str(UUID.uuid4())
            server["username"] = username
            if force_unique and server["Id"] in self.clients:
                return client
            self.connect_client(server)
            self.credentials.append(server)
            self.save_credentials()
            return client
        return None

    def setup_client(self, client: "JellyfinClient", server):
        def event(event_name, data):
            if event_name == "WebSocketDisconnect":
                timeout_gen = expo(100)
                if server["uuid"] in self.clients:
                    while not self.is_stopping:
                        timeout = next(timeout_gen)
                        log.info(
                            "No connection to server. Next try in {0} second(s)".format(
                                timeout
                            )
                        )
                        self._disconnect_client(server=server)
                        time.sleep(timeout)
                        if self.connect_client(server):
                            break
            else:
                self.callback(client, event_name, data)

        client.callback = event
        client.callback_ws = event
        client.start(websocket=True)

        client.jellyfin.post_capabilities(CAPABILITIES)

    def remove_client(self, uuid: str):
        self.credentials = [
            server for server in self.credentials if server["uuid"] != uuid
        ]
        self.save_credentials()
        self._disconnect_client(uuid=uuid)

    def connect_client(self, server):
        if self.is_stopping:
            return False

        is_logged_in = False
        client = self.client_factory()
        state = client.authenticate({"Servers": [server]}, discover=False)
        server["connected"] = state["State"] == CONNECTION_STATE["SignedIn"]
        if server["connected"]:
            is_logged_in = True
            self.clients[server["uuid"]] = client
            self.setup_client(client, server)
            if server.get("username"):
                self.usernames[server["uuid"]] = server["username"]

        return is_logged_in

    def _disconnect_client(self, uuid: Optional[str] = None, server=None):
        if uuid is None and server is not None:
            uuid = server["uuid"]

        if uuid not in self.clients:
            return

        if server is not None:
            server["connected"] = False

        client = self.clients[uuid]
        del self.clients[uuid]
        client.stop()

    def remove_all_clients(self):
        self.stop_all_clients()
        self.credentials = []
        self.save_credentials()

    def stop_all_clients(self):
        for key, client in list(self.clients.items()):
            del self.clients[key]
            client.stop()

    def stop(self):
        self.is_stopping = True
        for client in self.clients.values():
            client.stop()

    def get_username_from_client(self, client):
        # This is kind of convoluted. It may fail if a server
        # was added before we started saving usernames.
        for uuid, client2 in self.clients.items():
            if client2 is client:
                if uuid in self.usernames:
                    return self.usernames[uuid]
                for server in self.credentials:
                    if server["uuid"] == uuid:
                        return server.get("username", "Unknown")
                break

        return "Unknown"


def initialize_jellyfin_api_client():
    global jellyfin_client_manager
    jellyfin_client_manager = ClientManager()


def jellyfin_login(server_url, server_username, server_password):
    global jellyfin_client_manager
    global jellyfin_current_client
    if jellyfin_client_manager is not None:
        jellyfin_logout()
    initialize_jellyfin_api_client()
    jellyfin_current_client = jellyfin_client_manager.login(server_url, server_username, server_password)
    return jellyfin_current_client


def jellyfin_logout():
    global jellyfin_client_manager
    if jellyfin_client_manager is not None:
        jellyfin_client_manager.stop()
    jellyfin_client_manager = None


def jellyfin_client():
    global jellyfin_current_client

    if jellyfin_current_client is None:
        jellyfin_login()
    return jellyfin_current_client
