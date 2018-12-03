from .utils import extract_id
from .operations import build_operation


class Record(object):

    # if a subclass has a list of ids that should be update when child records are removed, it should specify the key here
    child_list_key = None

    def __init__(self, client, id, *args, **kwargs):
        self._client = client
        self._id = extract_id(id)

    @property
    def id(self):
        return self._id

    def _str_fields(self):
        """
        Determines the list of fields to include in the __str__ representation. Override and extend this in subclasses.
        """
        return ["id"]

    def __str__(self):
        return ", ".join(["{}={}".format(field, repr(getattr(self, field))) for field in self._str_fields() if getattr(self, field, "")])

    def __repr__(self):
        return "<{} ({})>".format(self.__class__.__name__, self)

    def refresh(self):
        """
        Update the cached data for this record from the server (data for other records may be updated as a side effect).
        """
        self._get_record_data(force_refresh=True)

    def _get_record_data(self, force_refresh=False):
        return self._client.get_record_data(self._table, self.id, force_refresh=force_refresh)

    def get(self, path=[], default=None, force_refresh=False):
        """
        Retrieve cached data for this block. The `path` is a list (or dot-delimited string) the specifies the field
        to retrieve the value for. If no path is supplied, return the entire cached data structure for this block.
        If `force_refresh` is set to True, we force_refresh the data cache from the server before reading the values.
        """

        if isinstance(path, str):
            path = path.split(".")

        value = self._get_record_data(force_refresh=force_refresh)

        # try to traverse down the sequence of keys defined in the path, to get the target value if it exists
        try:
            for key in path:
                value = value[key]
        except KeyError:
            value = default

        return value

    def set(self, path, value, refresh=True):
        """
        Set a specific `value` (under the specific `path`) on the block's data structure on the server.
        If `refresh` is set to True, we refresh the data cache from the server after sending the update.
        """
        self._client.submit_transaction(build_operation(id=self.id, path=path, args=value, table=self._table))
        if refresh:
            self.refresh()

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return self.id != other.id

    def __hash__(self):
        return hash(self.id)