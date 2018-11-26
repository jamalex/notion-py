from requests import Session
from requests.cookies import cookiejar_from_dict
from urllib.parse import urljoin

from utils import extract_id
from blocks import Block, BLOCK_TYPES
from settings import API_BASE_URL
from operations import operation_update_last_edited


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
        block = self.block_cache[block_id]["value"]
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

        data = {
            "operations": operations
        }

        return self.post("submitTransaction", data).json()

    def update_block_cache(self, block_id):
        """
        We maintain an internal cache of all block values; this command updates the state through the API for a specific
        block and for its parent/children whose data is returned alongside it.
        """
        data = {"pageId": block_id, "limit": 1000, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False}
        blocks = self.post("loadPageChunk", data).json()["recordMap"]["block"] 
        self.block_cache.update(blocks)

    def bulk_update_block_cache(self, block_ids):
        """
        We maintain an internal cache of all block values; this command updates the state in bulk through the API for
        the given list of block IDs.
        """
        if not block_ids:
            return
        requestlist = [{"table": "block", "id": extract_id(id)} for id in block_ids]
        results = self.post("getRecordValues", {"requests": requestlist}).json()["results"]
        for result in results:
            self.block_cache[result["value"]["id"]] = result
