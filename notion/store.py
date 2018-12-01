from collections import defaultdict
from utils import extract_id
from tzlocal import get_localzone


class Missing(object):

    def __bool__(self):
        return False

Missing = Missing()


class RecordStore(object):

    def __init__(self, client):
        self._client = client
        self._data = defaultdict(lambda: defaultdict(dict))
        self._records_to_refresh = {}
        self._pages_to_refresh = []

    def _get(self, table, id):
        return self._data[table].get(id, Missing)

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
                ids = list(self._data.get(table, {}).keys())
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
                if "value" in result:
                    self._data[request["table"]][request["id"]] = result["value"]

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
                self._data[table][id] = record["value"]

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
