import mimetypes
import os
import requests

from requests import Session
from requests.cookies import cookiejar_from_dict
from urllib.parse import urljoin

from utils import extract_id
from blocks import Block, BLOCK_TYPES
from settings import API_BASE_URL
from operations import operation_update_last_edited, build_operation

class NotionClient(object):
    """
    This is the entry point to using the API. Create an instance of this class, passing it the value of the
    "token_v2" cookie from a logged-in browser session on Notion.so. Most of the methods on here are primarily
    for internal use -- the main one you'll likely want to use is `get_block`.
    """

    def __init__(self, token_v2):
        self.session = Session()
        self.session.cookies = cookiejar_from_dict({"token_v2": token_v2})
        self.block_cache = {}
        self.user_cache = {}
        self.user_id = self.post("getUserAnalyticsSettings", {"platform": "web"}).json()["user_id"]

    def get_block(self, url_or_id):
        """
        Retrieve a subclass of Block that maps to the block/page identified by the URL or ID passed in.
        """
        block_id = extract_id(url_or_id)
        if block_id not in self.block_cache:
            self.update_block_cache(block_id)
        try:
            block = self.block_cache[block_id]["value"]
        except KeyError:
            return None
        block_class = BLOCK_TYPES.get(block.get("type", ""), Block)
        return block_class(self, block_id)

    def post(self, endpoint, data):
        """
        All API requests on Notion.so are done as POSTs (except the websocket communications).
        """
        url = urljoin(API_BASE_URL, endpoint)
        response = self.session.post(url, json=data)
        response.raise_for_status()
        return response

    def get_user_info(self, user_ids):
        singleton = isinstance(user_ids, str)
        if singleton:
            user_ids = [user_ids]
        requestlist = [{"table": "notion_user", "id": extract_id(id)} for id in user_ids]
        results = [result.get("value") for result in self.post("getRecordValues", {"requests": requestlist}).json()["results"]]
        return results[0] if singleton else results

    def submit_transaction(self, operations, update_last_edited=True):

        if isinstance(operations, dict):
            operations = [operations]

        if update_last_edited:
            updated_blocks = set([op["id"] for op in operations if op["table"] == "block"])
            operations += [operation_update_last_edited(self.user_id, block_id) for block_id in updated_blocks]

        # if we're in a transaction, just add these operations to the list; otherwise, execute them right away
        if self.in_transaction():
            self._transaction_operations += operations
        else:
            data = {
                "operations": operations
            }
            return self.post("submitTransaction", data).json()

    def update_block_cache(self, block_id):
        """
        We maintain an internal cache of all block values; this command updates the state through the API for a specific
        block and for its parent/children whose data is returned alongside it.
        """
        if self.in_transaction():
            self._pages_to_refresh.append(block_id)
            return

        data = {"pageId": block_id, "limit": 1000, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False}
        blocks = self.post("loadPageChunk", data).json()["recordMap"].get("block", {})
        self.block_cache.update(blocks)

    def bulk_update_block_cache(self, block_ids=None):
        """
        We maintain an internal cache of all block values; this command updates the state in bulk through the API for
        the given list of block IDs. If no list is provided, we bulk update all blocks we know about.
        """
        if block_ids is None:
            block_ids = list(self.block_cache.keys())
        if not block_ids:
            return

        if self.in_transaction():
            self._blocks_to_refresh += block_ids
            return

        requestlist = [{"table": "block", "id": extract_id(id)} for id in block_ids]
        results = self.post("getRecordValues", {"requests": requestlist}).json()["results"]
        for result in results:
            if "value" in result:
                self.block_cache[result["value"]["id"]] = result

    def as_atomic_transaction(self):
        """
        Returns a context manager that buffers up all calls to `submit_transaction` and sends them as one big transaction
        when the context manager exits.
        """
        return Transaction(client=self)

    def in_transaction(self):
        return hasattr(self, "_transaction_operations")

    def upload_file(self, path):
        mimetype = mimetypes.guess_type(path)[0] or "text/plain"
        filename = os.path.split(path)[-1]

        data = self.post("getUploadFileUrl", {"bucket": "secure", "name": filename, "contentType": mimetype}).json()

        put_url = data["signedPutUrl"]
        url = data["url"]

        with open(path, 'rb') as f:
            response = requests.put(put_url, data=f, headers={"Content-type": mimetype})
            response.raise_for_status()

        return url


class Transaction(object):

    is_dummy_nested_transaction = False

    def __init__(self, client):
        self.client = client

    def __enter__(self):

        if hasattr(self.client, "_transaction_operations"):
            # client is already in a transaction, so we'll just make this one a nullop and let the outer one handle it
            self.is_dummy_nested_transaction = True
            return

        self.client._transaction_operations = []
        self.client._pages_to_refresh = []
        self.client._blocks_to_refresh = []

    def __exit__(self, exc_type, exc_value, traceback):

        if self.is_dummy_nested_transaction:
            return

        operations = self.client._transaction_operations
        del self.client._transaction_operations

        # only actually submit the transaction if there was no exception
        if not exc_type:
            self.client.submit_transaction(operations)

        for block_id in self.client._pages_to_refresh:
            self.client.update_block_cache(block_id=block_id)
        del self.client._pages_to_refresh

        self.client.bulk_update_block_cache(block_ids=self.client._blocks_to_refresh)
        del self.client._blocks_to_refresh

