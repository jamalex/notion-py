from cached_property import cached_property
from copy import deepcopy
from datetime import datetime, date
from tzlocal import get_localzone

from .block import Block, PageBlock, Children
from .logger import logger
from .maps import property_map, field_map
from .markdown import markdown_to_notion, notion_to_markdown
from .operations import build_operation
from .records import Record
from .utils import add_signed_prefix_as_needed, remove_signed_prefix_as_needed, slugify


class NotionDate(object):

    start = None
    end = None
    timezone = None

    def __init__(self, start, end=None, timezone=None):
        self.start = start
        self.end = end
        self.timezone = timezone

    @classmethod
    def from_notion(cls, obj):
        if isinstance(obj, dict):
            data = obj
        elif isinstance(obj, list):
            data = obj[0][1][0][1]
        else:
            return None
        start = cls._parse_datetime(data.get("start_date"), data.get("start_time"))
        end = cls._parse_datetime(data.get("end_date"), data.get("end_time"))
        timezone = data.get("timezone")
        return cls(start, end=end, timezone=timezone)

    @classmethod
    def _parse_datetime(cls, date_str, time_str):
        if not date_str:
            return None
        if time_str:
            return datetime.strptime(date_str + " " + time_str, '%Y-%m-%d %H:%M')
        else:
            return datetime.strptime(date_str, '%Y-%m-%d').date()

    def _format_datetime(self, date_or_datetime):
        if not date_or_datetime:
            return None, None
        if isinstance(date_or_datetime, datetime):
            return date_or_datetime.strftime("%Y-%m-%d"), date_or_datetime.strftime("%H:%M")
        else:
            return date_or_datetime.strftime("%Y-%m-%d"), None

    def type(self):
        name = "date"
        if isinstance(self.start, datetime):
            name += "time"
        if self.end:
            name += "range"
        return name

    def to_notion(self):

        if self.end:
            self.start, self.end = sorted([self.start, self.end])

        start_date, start_time = self._format_datetime(self.start)
        end_date, end_time = self._format_datetime(self.end)

        if not start_date:
            return []

        data = {
            "type": self.type(),
            "start_date": start_date,
        }

        if end_date:
            data["end_date"] = end_date

        if "time" in data["type"]:
            data["time_zone"] = str(self.timezone or get_localzone())
            data["start_time"] = start_time or "00:00"
            if end_date:
                data["end_time"] = end_time or "00:00"

        return [["‣", [["d", data]]]]

class Collection(Record):
    """
    A "collection" corresponds to what's sometimes called a "database" in the Notion UI.
    """

    _table = "collection"

    name = field_map("name", api_to_python=notion_to_markdown, python_to_api=markdown_to_notion)
    description = field_map("description", api_to_python=notion_to_markdown, python_to_api=markdown_to_notion)
    cover = field_map("cover")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client.refresh_collection_rows(self.id)

    @property
    def templates(self):
        if not hasattr(self, "_templates"):
            template_ids = self.get("template_pages", [])
            self._client.refresh_records(block=template_ids)
            self._templates = Templates(parent=self)
        return self._templates

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
            if identifier == "title" and prop["type"] == "title":
                return prop
        return None

    def add_row(self, **kwargs):
        """
        Create a new empty CollectionRowBlock under this collection, and return the instance.
        """

        row_id = self._client.create_record("block", self, type="page")
        row = CollectionRowBlock(self._client, row_id)

        with self._client.as_atomic_transaction():
            for key, val in kwargs.items():
                setattr(row, key, val)

        return row

    def get_rows(self):
        rows = []
        for row_id in self._client._store.get_collection_rows(self.id):
            row = self._client.get_block(row_id)
            row.__dict__['collection'] = self
            rows.append(row)
        return rows

    def _convert_diff_to_changelist(self, difference, old_val, new_val):

        changes = []
        remaining = []

        for operation, path, values in difference:

            if path == "rows":
                changes.append((operation, path, values))
            else:
                remaining.append((operation, path, values))

        return changes + super()._convert_diff_to_changelist(remaining, old_val, new_val)


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

    def build_query(self, **kwargs):
        calendar_by = self._client.get_record_data("collection_view", self._id)['query']['calendar_by']
        return super().build_query(calendar_by=calendar_by, **kwargs)


class GalleryView(CollectionView):

    _type = "gallery"


def _normalize_property_name(prop_name, collection):
    if not prop_name:
        return ""
    else:
        prop = collection.get_schema_property(prop_name)
        if not prop:
            return ""
        return prop["id"]


def _normalize_query_list(query_list, collection):
    query_list = deepcopy(query_list)
    for item in query_list:
        # convert slugs to property ids
        if "property" in item:
            item["property"] = _normalize_property_name(item["property"], collection)
        # convert any instantiated objects into their ids
        if "value" in item:
            if hasattr(item["value"], "id"):
                item["value"] = item["value"].id
    return query_list


class CollectionQuery(object):

    def __init__(self, collection, collection_view, search="", type="table", aggregate=[], filter=[], filter_operator="and", sort=[], calendar_by="", group_by=""):
        self.collection = collection
        self.collection_view = collection_view
        self.search = search
        self.type = type
        self.aggregate = _normalize_query_list(aggregate, collection)
        self.filter = _normalize_query_list(filter, collection)
        self.filter_operator = filter_operator
        self.sort = _normalize_query_list(sort, collection)
        self.calendar_by = _normalize_property_name(calendar_by, collection)
        self.group_by = _normalize_property_name(group_by, collection)
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
            sort=self.sort,
            calendar_by=self.calendar_by,
            group_by=self.group_by,
        ))


class CollectionRowBlock(PageBlock):

    @property
    def is_template(self):
        return self.get("is_template")

    @cached_property
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
        elif hasattr(self, attname):
            super().__setattr__(attname, value)
        else:
            raise AttributeError("Unknown property: '{}'".format(attname))

    def _get_property_slugs(self):
        slugs = [prop["slug"] for prop in self.schema]
        if "title" not in slugs:
            slugs.append("title")
        return slugs

    def __dir__(self):
        return self._get_property_slugs() + super().__dir__()

    def get_property(self, identifier):

        prop = self.collection.get_schema_property(identifier)
        if prop is None:
            raise AttributeError("Object does not have property '{}'".format(identifier))

        val = self.get(["properties", prop["id"]])

        return self._convert_notion_to_python(val, prop)

    def _convert_diff_to_changelist(self, difference, old_val, new_val):

        changed_props = set()
        changes = []
        remaining = []

        for d in difference:
            operation, path, values = d
            path = path.split(".") if isinstance(path, str) else path
            if path and path[0] == "properties":
                if len(path) > 1:
                    changed_props.add(path[1])
                else:
                    for item in values:
                        changed_props.add(item[0])
            else:
                remaining.append(d)

        for prop_id in changed_props:
            prop = self.collection.get_schema_property(prop_id)
            old = self._convert_notion_to_python(old_val.get("properties", {}).get(prop_id), prop)
            new = self._convert_notion_to_python(new_val.get("properties", {}).get(prop_id), prop)
            changes.append(("prop_changed", prop["slug"], (old, new)))

        return changes + super()._convert_diff_to_changelist(remaining, old_val, new_val)

    def _convert_notion_to_python(self, val, prop):

        if prop["type"] in ["title", "text"]:
            val = notion_to_markdown(val) if val else ""
        if prop["type"] in ["number"]:
            if val is not None:
                val = val[0][0]
                if "." in val:
                    val = float(val)
                else:
                    val = int(val)
        if prop["type"] in ["select"]:
            val = val[0][0] if val else None
        if prop["type"] in ["multi_select"]:
            val = [v.strip() for v in val[0][0].split(",")] if val else []
        if prop["type"] in ["person"]:
            val = [self._client.get_user(item[1][0][1]) for item in val if item[0] == "‣"] if val else []
        if prop["type"] in ["email", "phone_number", "url"]:
            val = val[0][0] if val else ""
        if prop["type"] in ["date"]:
            val = NotionDate.from_notion(val)
        if prop["type"] in ["file"]:
            val = [add_signed_prefix_as_needed(item[1][0][1], client=self._client) for item in val if item[0] != ","] if val else []
        if prop["type"] in ["checkbox"]:
            val = val[0][0] == "Yes" if val else False
        if prop["type"] in ["relation"]:
            val = [self._client.get_block(item[1][0][1]) for item in val if item[0] == "‣"] if val else []
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
            propid = slugify(prop["name"])
            allprops[propid] = self.get_property(propid)
        return allprops

    def set_property(self, identifier, val):

        prop = self.collection.get_schema_property(identifier)
        if prop is None:
            raise AttributeError("Object does not have property '{}'".format(identifier))

        path, val = self._convert_python_to_notion(val, prop, identifier=identifier)

        self.set(path, val)

    def _convert_python_to_notion(self, val, prop, identifier="<unknown>"):

        if prop["type"] in ["title", "text"]:
            if not val:
                val = ""
            if not isinstance(val, str):
                raise TypeError("Value passed to property '{}' must be a string.".format(identifier))
            val = markdown_to_notion(val)
        if prop["type"] in ["number"]:
            if val is not None:
                if not isinstance(val, float) and not isinstance(val, int):
                    raise TypeError("Value passed to property '{}' must be an int or float.".format(identifier))
                val = [[str(val)]]
        if prop["type"] in ["select"]:
            if not val:
                val = None
            else:
                valid_options = [p["value"].lower() for p in prop["options"]]
                val = val.split(",")[0]
                if val.lower() not in valid_options:
                    raise ValueError("Value '{}' not acceptable for property '{}' (valid options: {})"
                                     .format(val, identifier, valid_options))
                val = [[val]]
        if prop["type"] in ["multi_select"]:
            if not val:
                val = []
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
            if isinstance(val, date) or isinstance(val, datetime):
                val = NotionDate(val)
            if isinstance(val, NotionDate):
                val = val.to_notion()
            else:
                val = []
        if prop["type"] in ["file"]:
            filelist = []
            if not isinstance(val, list):
                val = [val]
            for url in val:
                url = remove_signed_prefix_as_needed(url)
                filename = url.split("/")[-1]
                filelist += [[filename, [['a', url]]], [',']]
            val = filelist[:-1]
        if prop["type"] in ["checkbox"]:
            if not isinstance(val, bool):
                raise TypeError("Value passed to property '{}' must be a bool.".format(identifier))
            val = [["Yes" if val else "No"]]
        if prop["type"] in ["relation"]:
            pagelist = []
            if not isinstance(val, list):
                val = [val]
            for page in val:
                if isinstance(page, str):
                    page = self._client.get_block(page)
                pagelist += [['‣', [['p', page.id]]], [',']]
            val = pagelist[:-1]
        if prop["type"] in ["created_time", "last_edited_time"]:
            val = int(val.timestamp() * 1000)
            return prop["type"], val
        if prop["type"] in ["created_by", "last_edited_by"]:
            val = val if isinstance(val, str) else val.id
            return prop["type"], val

        return ["properties", prop["id"]], val

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


class TemplateBlock(CollectionRowBlock):

    @property
    def is_template(self):
        return self.get("is_template")

    @is_template.setter
    def is_template(self, val):
        assert val is True, "Templates must have 'is_template' set to True."
        self.set("is_template", True)


class Templates(Children):

    child_list_key = "template_pages"

    def _content_list(self):
        return self._parent.get(self.child_list_key) or []

    def add_new(self, **kwargs):

        kwargs["block_type"] = "page"
        kwargs["child_list_key"] = self.child_list_key
        kwargs["is_template"] = True

        return super().add_new(**kwargs)


class QueryResult(object):

    def __init__(self, collection, result):
        self.collection = collection
        self._client = collection._client
        self._block_ids = self._get_block_ids(result)
        self.aggregates = result.get("aggregationResults", [])

    def _get_block_ids(self, result):
        return result["blockIds"]

    def _get_block(self, id):
        block = CollectionRowBlock(self._client, id)
        block.__dict__['collection'] = self.collection
        return block

    def get_aggregate(self, id):
        for agg in self.aggregates:
            if id == agg["id"]:
                return agg["value"]
        return None

    def __repr__(self):
        if not len(self):
            return "[]"
        rep = "[\n"
        for child in self:
            rep += "  {},\n".format(repr(child))
        rep += "]"
        return rep

    def __len__(self):
        return len(self._block_ids)

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
