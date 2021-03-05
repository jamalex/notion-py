import hashlib
import json
import re
import uuid

from requests import Session, HTTPError
from requests.cookies import cookiejar_from_dict
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from getpass import getpass

from .block import Block, BLOCK_TYPES
from .collection import (
    Collection,
    CollectionView,
    CollectionRowBlock,
    COLLECTION_VIEW_TYPES,
    TemplateBlock,
)
from .logger import logger
from .monitor import Monitor
from .operations import operation_update_last_edited, build_operation
from .settings import API_BASE_URL
from .space import Space
from .store import RecordStore
from .user import User
from .utils import extract_id, now


def create_session(client_specified_retry=None):
    """
    retry on 502
    """
    session = Session()
    if client_specified_retry:
        retry = client_specified_retry
    else:
        retry = Retry(
            5,
            backoff_factor=0.3,
            status_forcelist=(502, 503, 504),
            # CAUTION: adding 'POST' to this list which is not technically idempotent
            method_whitelist=(
                "POST",
                "HEAD",
                "TRACE",
                "GET",
                "PUT",
                "OPTIONS",
                "DELETE",
            ),
        )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


class NotionClient(object):
    """
    This is the entry point to using the API. Create an instance of this class, passing it the value of the
    "token_v2" cookie from a logged-in browser session on Notion.so. Most of the methods on here are primarily
    for internal use -- the main one you'll likely want to use is `get_block`.
    """

    def __init__(
        self,
        token_v2=None,
        monitor=False,
        start_monitoring=False,
        enable_caching=False,
        cache_key=None,
        email=None,
        password=None,
        client_specified_retry=None,
    ):
        self.session = create_session(client_specified_retry)
        if token_v2:
            self.session.cookies = cookiejar_from_dict({"token_v2": token_v2})
        else:
            self._set_token(email=email, password=password)

        if enable_caching:
            cache_key = cache_key or hashlib.sha256(token_v2.encode()).hexdigest()
            self._store = RecordStore(self, cache_key=cache_key)
        else:
            self._store = RecordStore(self)
        if monitor:
            self._monitor = Monitor(self)
            if start_monitoring:
                self.start_monitoring()
        else:
            self._monitor = None

        self._update_user_info()

    def start_monitoring(self):
        self._monitor.poll_async()
    
    def _fetch_guest_space_data(self, records):
        """
        guest users have an empty `space` dict, so get the space_id from the `space_view` dict instead,
        and fetch the space data from the getPublicSpaceData endpoint.

        Note: This mutates the records dict
        """
        space_id = list(records["space_view"].values())[0]["value"]["space_id"]

        space_data = self.post(
            "getPublicSpaceData", {"type": "space-ids", "spaceIds": [space_id]}
        ).json()

        records["space"] = {
            space["id"]: {"value": space} for space in space_data["results"]
        }


    def _set_token(self, email=None, password=None):
        if not email:
            email = input("Enter your Notion email address:\n")
        if not password:
            password = getpass("Enter your Notion password:\n")
        self.post("loginWithEmail", {"email": email, "password": password}).json()

    def _update_user_info(self):
        records = self.post("loadUserContent", {}).json()["recordMap"]
        if not records["space"]:
            self._fetch_guest_space_data(records)

        self._store.store_recordmap(records)
        self.current_user = self.get_user(list(records["notion_user"].keys())[0])
        self.current_space = self.get_space(list(records["space"].keys())[0])
        return records

    def get_email_uid(self):
        response = self.post("getSpaces", {}).json()
        return {
            response[uid]["notion_user"][uid]["value"]["email"]: uid
            for uid in response.keys()
        }

    def set_user_by_uid(self, user_id):
        self.session.headers.update({"x-notion-active-user-header": user_id})
        self._update_user_info()

    def set_user_by_email(self, email):
        email_uid_dict = self.get_email_uid()
        uid = email_uid_dict.get(email)
        if not uid:
            raise Exception(
                "Requested email address {email} not found; available addresses: {available}".format(
                    email=email, available=list(email_uid_dict)
                )
            )
        self.set_user_by_uid(uid)

    def get_top_level_pages(self):
        records = self._update_user_info()
        return [self.get_block(bid) for bid in records["block"].keys()]

    def get_record_data(self, table, id, force_refresh=False):
        return self._store.get(table, id, force_refresh=force_refresh)

    def get_block(self, url_or_id, force_refresh=False):
        """
        Retrieve an instance of a subclass of Block that maps to the block/page identified by the URL or ID passed in.
        """
        block_id = extract_id(url_or_id)
        block = self.get_record_data("block", block_id, force_refresh=force_refresh)
        if not block:
            return None
        if block.get("parent_table") == "collection":
            if block.get("is_template"):
                block_class = TemplateBlock
            else:
                block_class = CollectionRowBlock
        else:
            block_class = BLOCK_TYPES.get(block.get("type", ""), Block)
        return block_class(self, block_id)

    def get_collection(self, collection_id, force_refresh=False):
        """
        Retrieve an instance of Collection that maps to the collection identified by the ID passed in.
        """
        coll = self.get_record_data(
            "collection", collection_id, force_refresh=force_refresh
        )
        return Collection(self, collection_id) if coll else None

    def get_user(self, user_id, force_refresh=False):
        """
        Retrieve an instance of User that maps to the notion_user identified by the ID passed in.
        """
        user = self.get_record_data("notion_user", user_id, force_refresh=force_refresh)
        return User(self, user_id) if user else None

    def get_space(self, space_id, force_refresh=False):
        """
        Retrieve an instance of Space that maps to the space identified by the ID passed in.
        """
        space = self.get_record_data("space", space_id, force_refresh=force_refresh)
        return Space(self, space_id) if space else None

    def get_collection_view(self, url_or_id, collection=None, force_refresh=False):
        """
        Retrieve an instance of a subclass of CollectionView that maps to the appropriate type.
        The `url_or_id` argument can either be the URL for a database page, or the ID of a collection_view (in which case
        you must also pass the collection)
        """
        # if it's a URL for a database page, try extracting the collection and view IDs
        if url_or_id.startswith("http"):
            match = re.search("([a-f0-9]{32})\?v=([a-f0-9]{32})", url_or_id)
            if not match:
                raise Exception("Invalid collection view URL")
            block_id, view_id = match.groups()
            collection = self.get_block(
                block_id, force_refresh=force_refresh
            ).collection
        else:
            view_id = url_or_id
            assert (
                collection is not None
            ), "If 'url_or_id' is an ID (not a URL), you must also pass the 'collection'"

        view = self.get_record_data(
            "collection_view", view_id, force_refresh=force_refresh
        )

        return (
            COLLECTION_VIEW_TYPES.get(view.get("type", ""), CollectionView)(
                self, view_id, collection=collection
            )
            if view
            else None
        )

    def refresh_records(self, **kwargs):
        """
        The keyword arguments map table names into lists of (or singular) record IDs to load for that table.
        Use `True` instead of a list to refresh all known records for that table.
        """
        self._store.call_get_record_values(**kwargs)

    def refresh_collection_rows(self, collection_id):
        row_ids = [row.id for row in self.get_collection(collection_id).get_rows()]
        self._store.set_collection_rows(collection_id, row_ids)

    def post(self, endpoint, data):
        """
        All API requests on Notion.so are done as POSTs (except the websocket communications).
        """
        url = urljoin(API_BASE_URL, endpoint)
        response = self.session.post(url, json=data)
        if response.status_code == 400:
            logger.error(
                "Got 400 error attempting to POST to {}, with data: {}".format(
                    endpoint, json.dumps(data, indent=2)
                )
            )
            raise HTTPError(
                response.json().get(
                    "message", "There was an error (400) submitting the request."
                )
            )
        response.raise_for_status()
        return response

    def submit_transaction(self, operations, update_last_edited=True):

        if not operations:
            return

        if isinstance(operations, dict):
            operations = [operations]

        if update_last_edited:
            updated_blocks = set(
                [op["id"] for op in operations if op["table"] == "block"]
            )
            operations += [
                operation_update_last_edited(self.current_user.id, block_id)
                for block_id in updated_blocks
            ]

        # if we're in a transaction, just add these operations to the list; otherwise, execute them right away
        if self.in_transaction():
            self._transaction_operations += operations
        else:
            data = {"operations": operations}
            self.post("submitTransaction", data)
            self._store.run_local_operations(operations)

    def query_collection(self, *args, **kwargs):
        return self._store.call_query_collection(*args, **kwargs)

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

    def search_pages_with_parent(self, parent_id, search=""):
        data = {
            "query": search,
            "parentId": parent_id,
            "limit": 10000,
            "spaceId": self.current_space.id,
        }
        response = self.post("searchPagesWithParent", data).json()
        self._store.store_recordmap(response["recordMap"])
        return response["results"]

    def search_blocks(self, search, limit=25):
        return self.search(query=search, limit=limit)

    def search(
        self,
        query="",
        search_type="BlocksInSpace",
        limit=100,
        sort="Relevance",
        source="quick_find",
        isDeletedOnly=False,
        excludeTemplates=False,
        isNavigableOnly=False,
        requireEditPermissions=False,
        ancestors=[],
        createdBy=[],
        editedBy=[],
        lastEditedTime={},
        createdTime={},
    ):
        data = {
            "type": search_type,
            "query": query,
            "spaceId": self.current_space.id,
            "limit": limit,
            "filters": {
                "isDeletedOnly": isDeletedOnly,
                "excludeTemplates": excludeTemplates,
                "isNavigableOnly": isNavigableOnly,
                "requireEditPermissions": requireEditPermissions,
                "ancestors": ancestors,
                "createdBy": createdBy,
                "editedBy": editedBy,
                "lastEditedTime": lastEditedTime,
                "createdTime": createdTime,
            },
            "sort": sort,
            "source": source,
        }
        response = self.post("search", data).json()
        self._store.store_recordmap(response["recordMap"])
        return [self.get_block(result["id"]) for result in response["results"]]

    def create_record(self, table, parent, **kwargs):

        # make up a new UUID; apparently we get to choose our own!
        record_id = str(uuid.uuid4())

        child_list_key = kwargs.get("child_list_key") or parent.child_list_key

        args = {
            "id": record_id,
            "version": 1,
            "alive": True,
            "created_by_id": self.current_user.id,
            "created_by_table": "notion_user",
            "created_time": now(),
            "parent_id": parent.id,
            "parent_table": parent._table,
        }

        args.update(kwargs)

        with self.as_atomic_transaction():

            # create the new record
            self.submit_transaction(
                build_operation(
                    args=args, command="set", id=record_id, path=[], table=table
                )
            )

            # add the record to the content list of the parent, if needed
            if child_list_key:
                self.submit_transaction(
                    build_operation(
                        id=parent.id,
                        path=[child_list_key],
                        args={"id": record_id},
                        command="listAfter",
                        table=parent._table,
                    )
                )

        return record_id


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
