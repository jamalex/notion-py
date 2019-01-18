import json
import re
import requests
import threading
import time
import uuid

from collections import defaultdict
from inspect import signature
from requests import HTTPError

from .collection import Collection
from .logger import logger
from .records import Record


class Monitor(object):

    thread = None

    def __init__(self, client, root_url="https://msgstore.www.notion.so/primus/"):
        self.client = client
        self.session_id = str(uuid.uuid4())
        self.root_url = root_url
        self._subscriptions = set()
        self.initialize()

    def _decode_numbered_json_thing(self, thing):

        thing = thing.decode().strip()

        for ping in re.findall('\d+:\d+"primus::ping::\d+"', thing):
            logger.debug("Received ping: {}".format(ping))
            self.post_data(ping.replace("::ping::", "::pong::"))

        results = []
        for blob in re.findall("\d+:\d+(\{.*?\})(?=\d|$)", thing):
            results.append(json.loads(blob))
        if thing and not results and "::ping::" not in thing:
            logger.debug("Could not parse monitoring response: {}".format(thing))
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

        logger.debug("Initializing new monitoring session.")

        response = self.client.session.get("{}?sessionId={}&EIO=3&transport=polling".format(self.root_url, self.session_id))

        self.sid = self._decode_numbered_json_thing(response.content)[0]["sid"]

        logger.debug("New monitoring session ID is: {}".format(self.sid))

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

                logger.debug("Subscribing new record to the monitoring watchlist: {}/{}".format(record._table, record.id))

                # add the record to the list of records to restore if we're disconnected
                self._subscriptions.add(record)

                # subscribe to changes to the record itself
                sub_data.append({
                    "type": "/api/v1/registerSubscription",
                    "requestId": str(uuid.uuid4()),
                    "key": "versions/{}:{}".format(record.id, record._table),
                    "version": record.get("version", -1),
                })

                # if it's a collection, subscribe to changes to its children too
                if isinstance(record, Collection):
                    sub_data.append({
                        "type": "/api/v1/registerSubscription",
                        "requestId": str(uuid.uuid4()),
                        "key": "collection/{}".format(record.id),
                        "version": -1,
                    })


        data = self._encode_numbered_json_thing(sub_data)

        self.post_data(data)

    def post_data(self, data):

        if not data:
            return

        logger.debug("Posting monitoring data: {}".format(data))

        self.client.session.post("{}?sessionId={}&transport=polling&sid={}".format(self.root_url, self.session_id, self.sid), data=data)

    def poll(self, retries=10):
        logger.debug("Starting new long-poll request")
        try:
            response = self.client.session.get("{}?sessionId={}&EIO=3&transport=polling&sid={}".format(self.root_url, self.session_id, self.sid))
            response.raise_for_status()
        except HTTPError as e:
            try:
                message = "{} / {}".format(response.content, e)
            except:
                message = "{}".format(e)
            logger.warn("Problem with submitting polling request: {} (will retry {} more times)".format(message, retries))
            time.sleep(0.1)
            if retries <= 0:
                raise
            if retries <= 5:
                logger.error("Persistent error submitting polling request: {} (will retry {} more times)".format(message, retries))
                # if we're close to giving up, also try reinitializing the session
                self.initialize()
            self.poll(retries=retries-1)

        self._refresh_updated_records(self._decode_numbered_json_thing(response.content))

    def _refresh_updated_records(self, events):

        records_to_refresh = defaultdict(list)

        for event in events:

            logger.debug("Received the following event from the remote server: {}".format(event))

            if not isinstance(event, dict):
                continue

            if event.get("type", "") == "notification":

                key = event.get("key")

                if key.startswith("versions/"):

                    match = re.match("versions/([^\:]+):(.+)", key)
                    if not match:
                        continue

                    record_id, record_table = match.groups()

                    local_version = self.client._store.get_current_version(record_table, record_id)
                    if event["value"] > local_version:
                        logger.debug("Record {}/{} has changed; refreshing to update from version {} to version {}".format(record_table, record_id, local_version, event["value"]))
                        records_to_refresh[record_table].append(record_id)
                    else:
                        logger.debug("Record {}/{} already at version {}, not trying to update to version {}".format(record_table, record_id, local_version, event["value"]))

                if key.startswith("collection/"):

                    match = re.match("collection/(.+)", key)
                    if not match:
                        continue

                    collection_id = match.groups()[0]

                    self.client.refresh_collection_rows(collection_id)
                    row_ids = self.client._store.get_collection_rows(collection_id)

                    logger.debug("Something inside collection {} has changed; refreshing all {} rows inside it".format(collection_id, len(row_ids)))

                    records_to_refresh["block"] += row_ids

        self.client.refresh_records(**records_to_refresh)

    def poll_async(self):
        if self.thread:
            # Already polling async; no need to have two threads
            return
        self.thread = threading.Thread(target=self.poll_forever, daemon=True)
        self.thread.start()

    def poll_forever(self):
        while True:
            try:
                self.poll()
            except Exception as e:
                logger.error("Encountered error during polling!")
                logger.error(e, exc_info=True)
                time.sleep(1)
