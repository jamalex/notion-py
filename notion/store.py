import uuid

from collections import defaultdict
from copy import deepcopy
from dictdiffer import diff
from inspect import signature
from tzlocal import get_localzone

from .utils import extract_id


class MissingClass(object):

    def __nonzero__(self):
        return False

Missing = MissingClass()


class Callback(object):

    def __init__(self, callback, record, callback_id=None, extra_kwargs={}):
        self.callback = callback
        self.record = record
        self.callback_id = callback_id or str(uuid.uuid4())
        self.extra_kwargs = extra_kwargs

    def __call__(self, difference):
        kwargs = {}
        kwargs.update(self.extra_kwargs)
        kwargs["record"] = self.record
        kwargs["callback_id"] = self.callback_id
        kwargs["difference"] = difference

        params = signature(self.callback).parameters
        for arg in list(kwargs.keys()):
            if arg not in params:
                del kwargs[arg]

        self.callback(**kwargs)

    def __eq__(self, val):
        if isinstance(val, str):
            return self.callback_id.startswith(val)
        elif isinstance(val, Callback):
            return self.callback_id == val.callback_id
        else:
            return False


class RecordStore(object):

    def __init__(self, client):
        self._client = client
        self._values = defaultdict(lambda: defaultdict(dict))
        self._role = defaultdict(lambda: defaultdict(str))
        self._callbacks = defaultdict(lambda: defaultdict(list))
        self._records_to_refresh = {}
        self._pages_to_refresh = []

    def _get(self, table, id):
        return self._values[table].get(id, Missing)

    def add_callback(self, record, callback, callback_id=None, extra_kwargs={}):
        self.remove_callbacks(record._table, record.id, callback_id)
        callback_obj = Callback(callback, record, callback_id=callback_id, extra_kwargs=extra_kwargs)
        self._callbacks[record._table][record.id].append(callback_obj)
        return callback_obj

    def remove_callbacks(self, table, id, callback_or_callback_id_prefix=""):
        """
        Remove all callbacks for the record specified by `table` and `id` that have a callback_id
        starting with the string `callback_or_callback_id_prefix`, or are equal to the provided callback.
        """
        if callback_or_callback_id_prefix is None:
            return
        callbacks = self._callbacks[table][id]
        while callback_or_callback_id_prefix in callbacks:
            callbacks.remove(callback_or_callback_id_prefix)

    def _trigger_callbacks(self, table, id, difference):
        for callback_obj in self._callbacks[table][id]:
            callback_obj(difference)

    def get_role(self, table, id, force_refresh=False):
        self.get(table, id, force_refresh=force_refresh)
        return self._role[table].get(id, None)

    def get(self, table, id, force_refresh=False):
        id = extract_id(id)
        # look up the record in the current local dataset
        result = self._get(table, id)
        # if it's not found, try refreshing the record from the server
        if result is Missing or force_refresh:
            if table == "block":
                self.call_load_page_chunk(id)
            else:
                self.call_get_record_values(**{table: id})
            result = self._get(table, id)
        return result if result is not Missing else None

    def _update_record(self, table, id, value=None, role=None):
        if role:
            self._role[table][id] = role
        if value:
            old_val = self._values[table][id]
            difference = list(diff(old_val, value, ignore=["version", "last_edited_time", "last_edited_by"]))
            self._values[table][id] = value
            if old_val and difference:
                self._trigger_callbacks(table, id, difference)

    def call_get_record_values(self, **kwargs):
        """
        Call the server's getRecordValues endpoint to update the local record store. The keyword arguments map
        table names into lists of (or singular) record IDs to load for that table. Use True to refresh all known
        records for that table.
        """

        requestlist = []

        for table, ids in kwargs.items():

            # ensure "ids" is a proper list
            if ids is True:
                ids = list(self._values.get(table, {}).keys())
            if isinstance(ids, str):
                ids = [ids]

            # if we're in a transaction, add the requested IDs to a queue to refresh when the transaction completes
            if self._client.in_transaction():
                self._records_to_refresh[table] = list(set(self._records_to_refresh.get(table, []) + ids))
                continue

            requestlist += [{"table": table, "id": extract_id(id)} for id in ids]

        if requestlist:
            results = self._client.post("getRecordValues", {"requests": requestlist}).json()["results"]
            for request, result in zip(requestlist, results):
                self._update_record(request["table"], request["id"], value=result.get("value"), role=result.get("role"))

    def get_current_version(self, table, id):
        values = self._get(table, id)
        if values and "version" in values:
            return values["version"]
        else:
            return -1

    def call_load_page_chunk(self, page_id):
        
        if self._client.in_transaction():
            self._pages_to_refresh.append(page_id)
            return

        data = {"pageId": page_id, "limit": 100000, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False}

        recordmap = self._client.post("loadPageChunk", data).json()["recordMap"]

        self.store_recordmap(recordmap)

    def store_recordmap(self, recordmap):
        for table, records in recordmap.items():
            for id, record in records.items():
                self._update_record(table, id, value=record.get("value"), role=record.get("role"))

    def call_query_collection(self, collection_id, collection_view_id, search="", type="table", aggregate=[], filter=[], filter_operator="and", sort=[], calendar_by=""):

        # convert singletons into lists if needed
        if isinstance(aggregate, dict):
            aggregate = [aggregate]
        if isinstance(filter, dict):
            filter = [filter]
        if isinstance(sort, dict):
            sort = [sort]

        data = {
            "collectionId": collection_id,
            "collectionViewId": collection_view_id,
            "loader": {
                "limit": 10000,
                "loadContentCover": True,
                "query": search,
                "userLocale": "en",
                "userTimeZone": str(get_localzone()),
                "type": type,
            },
            "query": {
            "aggregate": aggregate,
            "filter": filter,
            "filter_operator": filter_operator,
            "sort": sort,
            }
        }

        response = self._client.post("queryCollection", data).json()

        self.store_recordmap(response["recordMap"])

        return response["result"]

    def handle_post_transaction_refreshing(self):

        for block_id in self._pages_to_refresh:
            self.call_load_page_chunk(block_id)
        self._pages_to_refresh = []

        self.call_get_record_values(**self._records_to_refresh)
        self._records_to_refresh = {}

    def run_local_operations(self, operations):
        """
        Called to simulate the results of running the operations on the server, to keep the record store in sync
        even when we haven't completed a refresh (or we did a refresh but the database hadn't actually updated yet...)
        """
        for operation in operations:
            self.run_local_operation(**operation)

    def run_local_operation(self, table, id, path, command, args):

        path = deepcopy(path)

        new_val = deepcopy(self._values[table][id])

        ref = new_val

        # loop and descend down the path until it's consumed, or if we're doing a "set", there's one key left
        while (len(path) > 1) or (path and command != "set"):
            comp = path.pop(0)
            if comp not in ref:
                ref[comp] = [] if "list" in command else {}
            ref = ref[comp]

        if command == "update":
            assert isinstance(ref, dict)
            ref.update(args)
        elif command == "set":
            assert isinstance(ref, dict)
            if path:
                ref[path[0]] = args
            else:
                # this is the case of "setting the top level" (i.e. creating a record)
                ref.clear()
                ref.update(args)
        elif command == "listAfter":
            assert isinstance(ref, list)
            if "after" in args:
                ref.insert(ref.index(args["after"]) + 1, args["id"])
            else:
                ref.append(args["id"])
        elif command == "listBefore":
            assert isinstance(ref, list)
            if "before" in args:
                ref.insert(ref.index(args["before"]), args["id"])
            else:
                ref.insert(0, args["id"])
        elif command == "listRemove":
            try:
                ref.remove(args["id"])
            except ValueError:
                pass

        self._update_record(table, id, value=new_val)