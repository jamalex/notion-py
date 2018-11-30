from requests import Session, HTTPError
from requests.cookies import cookiejar_from_dict
from urllib.parse import urljoin

from utils import extract_id
from blocks import Block, BLOCK_TYPES
from settings import API_BASE_URL
from operations import operation_update_last_edited, build_operation
from store import RecordStore


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
        self._store = RecordStore(self)

    def get_record_data(self, table, id, force_refresh=False):
        return self._store.get(table, id, force_refresh=force_refresh)

    def get_block(self, url_or_id, force_refresh=False):
        """
        Retrieve a subclass of Block that maps to the block/page identified by the URL or ID passed in.
        """
        block_id = extract_id(url_or_id)
        block = self.get_record_data("block", block_id, force_refresh=force_refresh)
        if block is None:
            return None
        block_class = BLOCK_TYPES.get(block.get("type", ""), Block)
        return block_class(self, block_id)

    def refresh_records(self, **kwargs):
        """
        The keyword arguments map table names into lists of (or singular) record IDs to load for that table.
        Use True to refresh all known records for that table.
        """
        self._store.call_get_record_values(**kwargs)

    def post(self, endpoint, data):
        """
        All API requests on Notion.so are done as POSTs (except the websocket communications).
        """
        url = urljoin(API_BASE_URL, endpoint)
        response = self.session.post(url, json=data)
        if response.status_code == 400:
            raise HTTPError(response.json().get("message", "There was an error (400) submitting the request."))
        response.raise_for_status()
        return response

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
            # import json
            # print(json.dumps(operations, indent=2))
            return self.post("submitTransaction", data).json()

    def as_atomic_transaction(self):
        """
        Returns a context manager that buffers up all calls to `submit_transaction` and sends them as one big transaction
        when the context manager exits.
        """
        return Transaction(client=self)

    def in_transaction(self):
        """
        Returns True if we're currently in a transaction, otherwise False.
        """
        return hasattr(self, "_transaction_operations")


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

        self.client._store.handle_post_transaction_refreshing()

