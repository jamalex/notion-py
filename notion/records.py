from .utils import extract_id
from .operations import build_operation


class Record(object):

    # if a subclass has a list of ids that should be update when child records are removed, it should specify the key here
    child_list_key = None

    def __init__(self, client, id, *args, **kwargs):
        self._client = client
        self._id = extract_id(id)
        self._callbacks = []
        if hasattr(self._client, "_monitor"):
            self._client._monitor.subscribe(self)

    @property
    def id(self):
        return self._id

    @property
    def role(self):
        return self._client._store.get_role(self._table, self.id)

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

    def add_callback(self, callback, callback_id=None, extra_kwargs={}):
        callback_obj = self._client._store.add_callback(self, callback, callback_id=callback_id, extra_kwargs=extra_kwargs)
        self._callbacks.append(callback_obj)
        return callback_obj

    def remove_callbacks(self, callback_or_callback_id_prefix=None):
        if callback_or_callback_id_prefix is None:
            for callback_obj in list(self._callbacks):
                self._client._store.remove_callbacks(self._table, self.id, callback_or_callback_id_prefix=callback_obj)
            self._callbacks = []
        else:
            self._client._store.remove_callbacks(self._table, self.id, callback_or_callback_id_prefix=callback_or_callback_id_prefix)
            if callback_or_callback_id_prefix in self._callbacks:
                self._callbacks.remove(callback_or_callback_id_prefix)

    def _get_record_data(self, force_refresh=False):
        return self._client.get_record_data(self._table, self.id, force_refresh=force_refresh)

    def get(self, path=[], default=None, force_refresh=False):
        """
        Retrieve cached data for this record. The `path` is a list (or dot-delimited string) the specifies the field
        to retrieve the value for. If no path is supplied, return the entire cached data structure for this record.
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

    def set(self, path, value):
        """
        Set a specific `value` (under the specific `path`) on the record's data structure on the server.
        """
        self._client.submit_transaction(build_operation(id=self.id, path=path, args=value, table=self._table))

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return self.id != other.id

    def __hash__(self):
        return hash(self.id)
