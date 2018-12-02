from datetime import datetime

from .block import Block, PageBlock
from .maps import property_map, field_map
from .markdown import markdown_to_notion, notion_to_markdown
from .operations import build_operation
from .records import Record
from .utils import add_signed_prefix_as_needed, remove_signed_prefix_as_needed, slugify


class Collection(Record):
    """
    A "collection" corresponds to what's sometimes called a "database" in the Notion UI.
    """

    _table = "collection"

    name = field_map("name", api_to_python=notion_to_markdown, python_to_api=markdown_to_notion)
    description = field_map("description", api_to_python=notion_to_markdown, python_to_api=markdown_to_notion)
    cover = field_map("cover")

    def get_schema_properties(self):
        """
        Fetch a flattened list of all properties in the collection's schema.
        """
        properties = []
        schema = self.get("schema")
        for id, item in schema.items():
            prop = {"id": id, "slug": slugify(item["name"])}
            prop.update(item)
            properties.append(prop)
        return properties

    def get_schema_property(self, identifier):
        """
        Look up a property in the collection's schema, by "property id" (generally a 4-char string),
        or name (human-readable -- there may be duplicates, so we pick the first match we find).
        """
        for prop in self.get_schema_properties():
            if identifier == prop["id"] or slugify(identifier) == prop["slug"]:
                return prop
        return None

    def add_row(self):
        """
        Create a new empty CollectionRowBlock under this collection, and return the instance.
        """

        row_id = self._client.create_record("block", self)

        return CollectionRowBlock(self._client, row_id)

    def get_rows(self, search=""):

        return self._client.search_pages_with_parent(self.id, search=search)


class CollectionView(Record):
    """
    A "view" is a particular visualization of a collection, with a "type" (board, table, list, etc)
    and filters, sort, etc.
    """

    _table = "collection_view"

    def __init__(self, *args, collection, **kwargs):
        self.collection = collection
        super().__init__(*args, **kwargs)

    def build_query(self, **kwargs):
        return CollectionQuery(collection=self.collection, collection_view=self, **kwargs)

    def default_query(self):
        return self.build_query(**self.get("query", {}))


class BoardView(CollectionView):

    _type = "board"

    group_by = field_map("query.group_by")


class TableView(CollectionView):

    _type = "table"


class ListView(CollectionView):

    _type = "list"


class CalendarView(CollectionView):

    _type = "calendar"


class GalleryView(CollectionView):

    _type = "gallery"


class CollectionQuery(object):

    def __init__(self, collection, collection_view, search="", type="table", aggregate=[], filter=[], filter_operator="and", sort=[], calendar_by=""):
        self.collection = collection
        self.collection_view = collection_view
        self.search = search
        self.type = type
        self.aggregate = aggregate
        self.filter = filter
        self.filter_operator = filter_operator
        self.sort = sort
        self.calendar_by = calendar_by
        self._client = collection._client

    def execute(self):

        result_class = QUERY_RESULT_TYPES.get(self.type, QueryResult)

        return result_class(self.collection, self._client.query_collection(
            collection_id=self.collection.id,
            collection_view_id=self.collection_view.id,
            search=self.search,
            type=self.type,
            aggregate=self.aggregate,
            filter=self.filter,
            filter_operator=self.filter_operator,
            sort=[],
            calendar_by=self.calendar_by,
        ))


class CollectionRowBlock(PageBlock):

    @property
    def collection(self):
        return self._client.get_collection(self.get("parent_id"))

    @property
    def schema(self):
        return [prop for prop in self.collection.get_schema_properties() if prop["type"] not in ["formula", "rollup"]]

    def __getattr__(self, attname):
        return self.get_property(attname)

    def __setattr__(self, attname, value):
        if attname.startswith("_"):
            # we only allow setting of new non-property attributes that start with "_"
            super().__setattr__(attname, value)
        elif attname in self._get_property_slugs():
            self.set_property(attname, value)
        else:
            raise AttributeError("Unknown property: '{}'".format(attname))

    def _get_property_slugs(self):
        return [prop["slug"] for prop in self.schema]

    def __dir__(self):
        return self._get_property_slugs() + super().__dir__()

    def get_property(self, identifier):
        
        prop = self.collection.get_schema_property(identifier)
        if prop is None:
            raise AttributeError("Object does not have property '{}'".format(identifier))
        
        val = self.get(["properties", prop["id"]])

        if prop["type"] in ["title", "text"]:
            val = notion_to_markdown(val)
        if prop["type"] in ["number"]:
            val = val[0][0]
            if "." in val:
                val = float(val)
            else:
                val = int(val)
        if prop["type"] in ["select"]:
            val = val[0][0]
        if prop["type"] in ["multi_select"]:
            val = [v.strip() for v in val[0][0].split(",")]
        if prop["type"] in ["person"]:
            val = [self._client.get_user(item[1][0][1]) for item in val if item[0] == "‣"]
        if prop["type"] in ["email", "phone_number", "url"]:
            val = val[0][0]
        if prop["type"] in ["date"]:
            val = val[0][1][0][1]
        if prop["type"] in ["file"]:
            val = [add_signed_prefix_as_needed(item[1][0][1]) for item in val if item[0] != ","]
        if prop["type"] in ["checkbox"]:
            val = val[0][0] == "Yes"
        if prop["type"] in ["relation"]:
            val = [self._client.get_block(item[1][0][1]) for item in val if item[0] == "‣"]
        if prop["type"] in ["created_time", "last_edited_time"]:
            val = self.get(prop["type"])
            val = datetime.utcfromtimestamp(val / 1000)
        if prop["type"] in ["created_by", "last_edited_by"]:
            val = self.get(prop["type"])
            val = self._client.get_user(val)

        return val

    def get_all_properties(self):
        allprops = {}
        for prop in self.schema:
            propid = prop["name"].lower().replace(" ", "_")
            allprops[propid] = self.get_property(propid)
        return allprops

    def set_property(self, identifier, val):

        prop = self.collection.get_schema_property(identifier)
        if prop is None:
            raise AttributeError("Object does not have property '{}'".format(identifier))
        
        if prop["type"] in ["title", "text"]:
            if not isinstance(val, str):
                raise TypeError("Value passed to property '{}' must be a string.".format(identifier))
            val = markdown_to_notion(val)
        if prop["type"] in ["number"]:
            if not isinstance(val, float) and not isinstance(val, int):
                raise TypeError("Value passed to property '{}' must be an int or float.".format(identifier))
            val = [[str(val)]]
        if prop["type"] in ["select"]:
            valid_options = [p["value"].lower() for p in prop["options"]]
            val = val.split(",")[0]
            if val.lower() not in valid_options:
                raise ValueError("Value '{}' not acceptable for property '{}' (valid options: {})"
                                 .format(val, identifier, valid_options))
            val = [[val]]
        if prop["type"] in ["multi_select"]:
            valid_options = [p["value"].lower() for p in prop["options"]]
            if not isinstance(val, list):
                val = [val]
            for v in val:
                if v.lower() not in valid_options:
                    raise ValueError("Value '{}' not acceptable for property '{}' (valid options: {})"
                                     .format(v, identifier, valid_options))
            val = [[",".join(val)]]
        if prop["type"] in ["person"]:
            userlist = []
            if not isinstance(val, list):
                val = [val]
            for user in val:
                user_id = user if isinstance(user, str) else user.id
                userlist += [['‣', [['u', user_id]]], [',']]
            val = userlist[:-1]
        if prop["type"] in ["email", "phone_number", "url"]:
            val = [[val, [["a", val]]]]
        if prop["type"] in ["date"]:
            val = [['‣', [['d', val]]]]
        if prop["type"] in ["file"]:
            filelist = []
            if not isinstance(val, list):
                val = [val]
            for url in val:
                url = remove_signed_prefix_as_needed(url)
                filename = url.split("/")[-1]
                filelist += [filename, [['a', url]], [',']]
            val = filelist[:-1]
        if prop["type"] in ["checkbox"]:
            if not isinstance(val, bool):
                raise TypeError("Value passed to property '{}' must be a bool.".format(identifier))
            val = [["Yes" if val else "No"]]
        if prop["type"] in ["relation"]:
            pagelist = []
            for page in val:
                if isinstance(page, str):
                    page = self._client.get_block(page)
                pagelist += [['‣', [['p', page_id]]], [',']]
            val = pagelist[:-1]
        if prop["type"] in ["created_time", "last_edited_time"]:
            val = int(val.timestamp() * 1000)
            self.set(prop["type"], val)
            return
        if prop["type"] in ["created_by", "last_edited_by"]:
            val = val if isinstance(val, str) else val.id
            self.set(prop["type"], val)
            return

        self.set(["properties", prop["id"]], val)

    def remove(self):
        # Mark the block as inactive
        self._client.submit_transaction(
            build_operation(
                id=self.id,
                path=[],
                args={"alive": False},
                command="update",
            )
        )


class QueryResult(object):

    def __init__(self, collection, result):
        self.collection = collection
        self._client = collection._client
        self._block_ids = self._get_block_ids(result)

    def _get_block_ids(self, result):
        return result["blockIds"]

    def _get_block(self, id):
        return CollectionRowBlock(self._client, id)

    def __repr__(self):
        if not len(self):
            return "[]"
        rep = "[\n"
        for child in self:
            rep += "  {},\n".format(repr(child))
        rep += "]"
        return rep

    def __len__(self):
        return len(self._get_block_ids())

    def __getitem__(self, key):
        return list(iter(self))[key]

    def __iter__(self):
        return iter(self._get_block(id) for id in self._block_ids)

    def __reversed__(self):
        return reversed(iter(self))

    def __contains__(self, item):
        if isinstance(item, str):
            item_id = extract_id(item)
        elif isinstance(item, Block):
            item_id = item.id
        else:
            return False
        return item_id in self._block_ids


class TableQueryResult(QueryResult):

    _type = "table"


class BoardQueryResult(QueryResult):

    _type = "board"


class CalendarQueryResult(QueryResult):

    _type = "calendar"

    def _get_block_ids(self, result):
        block_ids = []
        for week in result["weeks"]:
            block_ids += week["items"]
        return block_ids


class ListQueryResult(QueryResult):

    _type = "list"


class GalleryQueryResult(QueryResult):

    _type = "gallery"


COLLECTION_VIEW_TYPES = {cls._type: cls for cls in locals().values() if type(cls) == type and issubclass(cls, CollectionView) and hasattr(cls, "_type")}

QUERY_RESULT_TYPES = {cls._type: cls for cls in locals().values() if type(cls) == type and issubclass(cls, QueryResult) and hasattr(cls, "_type")}