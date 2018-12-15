import json
import re
import threading
import uuid

from collections import defaultdict
from inspect import signature
from requests import HTTPError

from .records import Record

class Monitor(object):

    thread = None

    def __init__(self, client, root_url="https://msgstore.www.notion.so/primus/", verbose=False):
        self.client = client
        self.session_id = str(uuid.uuid4())
        self.root_url = root_url
        self._subscriptions = set()
        self.verbose = verbose
        self.initialize()

    def _decode_numbered_json_thing(self, thing):
        results = []
        for blob in re.findall("\d+:\d+(\{.*?\})(?=\d|$)", thing.decode().strip()):
            results.append(json.loads(blob))
        if thing and not results:
            if self.verbose:
                print("Could not parse:", thing.decode())
        return results

    def _encode_numbered_json_thing(self, data):
        assert isinstance(data, list)
        results = ""
        for obj in data:
            msg = str(len(obj)) + json.dumps(obj, separators=(',', ':'))
            msg = "{}:{}".format(len(msg), msg)
            results += msg
        return results.encode()

    def initialize(self):

        response = self.client.session.get("{}?sessionId={}&EIO=3&transport=polling".format(self.root_url, self.session_id))

        self.sid = self._decode_numbered_json_thing(response.content)[0]["sid"]

        # resubscribe to any existing subscriptions if we're reconnecting
        old_subscriptions, self._subscriptions = self._subscriptions, set()
        self.subscribe(old_subscriptions)

    def subscribe(self, records):

        if isinstance(records, set):
            records = list(records)

        if not isinstance(records, list):
            records = [records]

        sub_data = []

        for record in records:

            if record not in self._subscriptions:
                # add the record to the list of records to restore if we're disconnected
                self._subscriptions.add(record)
                sub_data.append({
                    "type": "/api/v1/registerSubscription",
                    "requestId": str(uuid.uuid4()),
                    "key": "versions/{}:{}".format(record.id, record._table),
                    "version": record.get("version"),
                })

        data = self._encode_numbered_json_thing(sub_data)

        self.client.session.post("{}?sessionId={}&transport=polling&sid={}".format(self.root_url, self.session_id, self.sid), data=data)

    def poll(self, retries=10):
        
        try:
            response = self.client.session.get("{}?sessionId={}&EIO=3&transport=polling&sid={}".format(self.root_url, self.session_id, self.sid))
            response.raise_for_status()
        except HTTPError:
            if retries <= 0:
                raise
            self.initialize()
            self.poll(retries=retries-1)
        
        self._refresh_updated_records(self._decode_numbered_json_thing(response.content))

    def _refresh_updated_records(self, events):
        
        records_to_refresh = defaultdict(list)

        for event in events:

            if not isinstance(event, dict):
                continue

            if event.get("type", "") == "notification":

                match = re.match("versions/([^\:]+):(.+)", event.get("key"))
                if not match:
                    continue

                record_id, record_table = match.groups()

                local_version = self.client._store.get_current_version(record_table, record_id)
                if event["value"] > local_version:
                    records_to_refresh[record_table].append(record_id)
                else:
                    if self.verbose:
                        print("Record already up-to-date, not updating:", record_table, record_id, event["value"], local_version)

        self.client.refresh_records(**records_to_refresh)

    def poll_async(self):
        if self.thread:
            raise Exeption("Already polling async")
        self.thread = threading.Thread(target=self.poll_forever, daemon=True)
        self.thread.start()

    def poll_forever(self):
        while True:
            self.poll()

    def poll_forever_websocket(self):
        """
        An alternative implementation of the watch behavior using websockets. Doesn't seem to be particularly faster.
        Note: requires installation of the "asyncio" and "websockets" packages.
        """

        import asyncio
        import websockets

        async def hello():

            while True:
                try:

                    self.initialize()

                    headers = [("Cookie", "AWSALB={};".format(self.client.session.cookies.get("AWSALB")))]

                    url = "wss://msgstore.www.notion.so/primus/?sessionId={}&EIO=3&transport=websocket&sid={}".format(self.session_id, self.sid)
                    
                    async with websockets.connect(url, extra_headers=headers) as websocket:
                        await websocket.send("2probe")
                        await websocket.recv()
                        await websocket.send("5")
                        while True:
                            event = json.loads(re.match("\d+(.*)", await websocket.recv()).groups()[0])
                            self._refresh_updated_records([event])

                except websockets.ConnectionClosed:
                    pass

        asyncio.get_event_loop().run_until_complete(hello())