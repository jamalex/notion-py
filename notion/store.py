from collections import defaultdict
from utils import extract_id

class Missing(object):
    pass

Missing = Missing()


class RecordStore(object):

    def __init__(self, client):
        self._client = client
        self._data = defaultdict(lambda: defaultdict(dict))
        self._blocks_to_refresh = {}
        self._pages_to_refresh = []

    def _get(self, table, id):
        return self._data[table].get(id, Missing)

    def get(self, table, id, force_refresh=False):
        # look up the record in the current local dataset
        result = self._get(table, id)
        # if it's not found, try refreshing the record from the server
        if result is Missing or force_refresh:
            if "table" == "block":
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
                self._blocks_to_refresh[table] = list(set(self._blocks_to_refresh.get(table, []) + ids))
                continue

            requestlist += [{"table": table, "id": extract_id(id)} for id in ids]

        if requestlist:
            results = self._client.post("getRecordValues", {"requests": requestlist}).json()["results"]
            for request, result in zip(requestlist, results):
                if "value" in result:
                    self._data[request["table"]][request["id"]] = result["value"]

    def call_load_page_chunk(self, page_id):
        
        if self.in_transaction():
            self._pages_to_refresh.append(page_id)
            return

        data = {"pageId": page_id, "limit": 100000, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": False}

        recordmap = self.post("loadPageChunk", data).json()["recordMap"]

        for table, records in recordmap.items():
            self._data[table].update(records)

    def handle_post_transaction_refreshing(self):

        for block_id in self._pages_to_refresh:
            self.call_load_page_chunk(block_id)
        self._pages_to_refresh = []

        self.call_get_record_values(**self._blocks_to_refresh)
        self._blocks_to_refresh = {}
