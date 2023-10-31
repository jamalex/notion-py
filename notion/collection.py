from contextlib import contextmanager
from cached_property import cached_property
from copy import deepcopy
from datetime import datetime, date
from tzlocal import get_localzone
from uuid import uuid1

from .block import Block, PageBlock, Children, CollectionViewBlock
from .logger import logger
from .maps import property_map, field_map
from .markdown import markdown_to_notion, notion_to_markdown
from .operations import build_operation
from .records import Record
from .utils import (
    add_signed_prefix_as_needed,
    extract_id,
    remove_signed_prefix_as_needed,
    slugify,
)


class NotionDate(object):

    start = None
    end = None
    timezone = None
    reminder = None

    def __init__(self, start, end=None, timezone=None, reminder=None):
        self.start = start
        self.end = end
        self.timezone = timezone
        self.reminder = reminder

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
        timezone = data.get("time_zone")
        reminder = data.get("reminder")
        return cls(start, end=end, timezone=timezone, reminder=reminder)

    @classmethod
    def _parse_datetime(cls, date_str, time_str):
        if not date_str:
            return None
        if time_str:
            return datetime.strptime(date_str + " " + time_str, "%Y-%m-%d %H:%M")
        else:
            return datetime.strptime(date_str, "%Y-%m-%d").date()

    def _format_datetime(self, date_or_datetime):
        if not date_or_datetime:
            return None, None
        if isinstance(date_or_datetime, datetime):
            return (
                date_or_datetime.strftime("%Y-%m-%d"),
                date_or_datetime.strftime("%H:%M"),
            )
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
        reminder = self.reminder

        if not start_date:
            return []

        data = {"type": self.type(), "start_date": start_date}

        if end_date:
            data["end_date"] = end_date

        if reminder:
            data["reminder"] = reminder

        if "time" in data["type"]:
            data["time_zone"] = str(self.timezone or get_localzone())
            data["start_time"] = start_time or "00:00"
            if end_date:
                data["end_time"] = end_time or "00:00"

        return [["‣", [["d", data]]]]


class NotionSelect(object):
    valid_colors = [
        "default",
        "gray",
        "brown",
        "orange",
        "yellow",
        "green",
        "blue",
        "purple",
        "pink",
        "red",
    ]
    id = None
    color = "default"
    value = None

    def __init__(self, value, color="default"):
        self.id = str(uuid1())
        self.color = self.set_color(color)
        self.value = value

    def set_color(self, color):
        if color not in self.valid_colors:
            if self.color:
                return self.color
            return "default"
        return color

    def to_dict(self):
        return {"id": self.id, "value": self.value, "color": self.color}


class Collection(Record):
    """
    A "collection" corresponds to what's sometimes called a "database" in the Notion UI.
    """

    _table = "collection"

    name = field_map(
        "name", api_to_python=notion_to_markdown, python_to_api=markdown_to_notion
    )
    description = field_map(
        "description",
        api_to_python=notion_to_markdown,
        python_to_api=markdown_to_notion,
    )
    cover = field_map("cover")

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

    def check_schema_select_options(self, prop, values):
        """
        Check and update the prop dict with new values
        """
        schema_update = False
        current_options = list([p["value"].lower() for p in prop["options"]])
        if not isinstance(values, list):
            values = [values]
        for v in values:
            if v and v.lower() not in current_options:
                schema_update = True
                prop["options"].append(NotionSelect(v).to_dict())
        return schema_update, prop

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

    def add_row(self, update_views=True, **kwargs):
        """
        Create a new empty CollectionRowBlock under this collection, and return the instance.
        """

        row_id = self._client.create_record("block", self, type="page")
        row = CollectionRowBlock(self._client, row_id)

        with self._client.as_atomic_transaction():
            for key, val in kwargs.items():
                setattr(row, key, val)

            if update_views:
                # make sure the new record is inserted at the end of each view
                for view in self.parent.views:
                    if view is None or isinstance(view, CalendarView):
                        continue
                    view.set("page_sort", view.get("page_sort", []) + [row_id])

        return row

    @property
    def parent(self):
        assert self.get("parent_table") == "block"
        return self._client.get_block(self.get("parent_id"))

    def _get_a_collection_view(self):
        """
        Get an arbitrary collection view for this collection, to allow querying.
        """
        parent = self.parent
        assert isinstance(parent, CollectionViewBlock)
        assert len(parent.views) > 0
        return parent.views[0]

    def query(self, **kwargs):
        return CollectionQuery(self, self._get_a_collection_view(), **kwargs).execute()

    def get_rows(self, **kwargs):
        return self.query(**kwargs)

    def _convert_diff_to_changelist(self, difference, old_val, new_val):

        changes = []
        remaining = []

        for operation, path, values in difference:

            if path == "rows":
                changes.append((operation, path, values))
            else:
                remaining.append((operation, path, values))

        return changes + super()._convert_diff_to_changelist(
            remaining, old_val, new_val
        )



class CollectionView(Record):
    """
    A "view" is a particular visualization of a collection, with a "type" (board, table, list, etc)
    and filters, sort, etc.
    """

    _table = "collection_view"

    name = field_map("name")
    type = field_map("type")

    @property
    def parent(self):
        assert self.get("parent_table", "block")
        return self._client.get_block(self.get("parent_id"))

    def __init__(self, *args, collection, **kwargs):
        self.collection = collection
        super().__init__(*args, **kwargs)

    def build_query(self, **kwargs):
        return CollectionQuery(
            collection=self.collection, collection_view=self, **kwargs
        )

    def default_query(self):
        return self.build_query(**self.get("query", {}))

    def update_view_sort(self, sort_list):
        """
            sort:list - [["property", "direction],...]
        """

        with self._update_query2() as query2_content:
            sort_query = []
            for sort in sort_list:
                assert type(sort) is list, "sort_list has invalid format. Expected [[\"property\", \"direction\"],...] "
                property_id = self.collection.get_schema_property(sort[0])["id"]
                sort_query.append({"property":property_id, "direction":sort[1]})
            query2_content["sort"] = sort_query


    def update_view_filter(self, filters):
        with self._update_query2() as query2_content:

            result_query = self.generate_view_filter_query(filters)
            query2_content["filter"] = result_query

    def update_view_aggregation(self, aggregations):
        with self._update_query2() as query2_content:

            result_query = self.generate_aggregation_query(aggregations)
            query2_content["aggregations"] = result_query


    def _submit_view_transaction(self, args, path=None):
        path = [] if path is None else path
        self._client.submit_transaction(
            build_operation(
                id=self.id, path=path, args=args, command="update", table="collection_view"
            ), generate_update_last_edited=False, updated_blocks=[self.parent.id]
        )

    def generate_aggregation_query(self, aggregations):
        """
            aggregations: list - [["property", "aggregator"],...]
        """

        result_query = {}
        aggregation_list = []
        for aggregation in aggregations:
            assert type(aggregation) is list,  "Aggregation {} must be list".format(str(aggregation))
            property_id = self.collection.get_schema_property(aggregation[0])["id"]
            aggregation_list.append({"property":property_id,"aggregator":aggregation[1]})

        result_query = aggregation_list
        return result_query

    def generate_view_filter_query(self, filters):
        """
            filters: list - [
                                { "group operator" : [[slugfied property, operator, type, value],...]},
                                { "group operator" : [[slugfied property, operator, type, value],...]}
                            ]
        """
        #TODO - Currently helper cannot process chained Filter Groups
        assert type(filters) is list

        filter_group_list = []
        for filter_dict in filters:
            assert type(filter_dict) is dict
            for group_operator, filter_group in filter_dict.items():
                filters_dict = {"operator" : group_operator}
                filters_list = []

                for filter in filter_group:
                    assert type(filter) is list, "Filter {} must be list".format(str(filter))
                    assert len(filter) == 4, "Filter {} must contain [slugfied property, operator, type, value]".format(str(filter))
                    property_id = self.collection.get_schema_property(filter[0])["id"]
                    filters_list.append({"property": property_id, "filter": {"operator": filter[1], "value": {"type": filter[2], "value":filter[3]}}})

                if len(filter_group) > 1:
                    filters_dict["filters"] = filters_list
                else:
                    filters_dict = [group_operator, filters_list]

                filter_group_list.append(filters_dict)

        if len(filter_group_list) == 0:
            return None

        main_filter = filter_group_list[0]
        main_operator = main_filter[0] if type(main_filter) is list else main_filter["operator"]
        result_query = {"filters":[], "operator":main_operator}
        for filter_group in filter_group_list:
            #if filter is not a filter_group
            if type(filter_group) is list:
                result_query["filters"].append(filter_group[1][0])
            else:
                result_query["filters"].append(filter_group)

        return result_query

    @contextmanager
    def _update_query2(self):
        try:
            self._client.refresh_records(collection_view=self.id, block=self.collection.id)
            query2_content = self.get("query2")
            query2_content = query2_content if query2_content is not None else {}
            yield query2_content
        finally:
            query2 = {"query2": query2_content}
            self._submit_view_transaction(query2)

    @contextmanager
    def _update_format(self):
        try:
            self._client.refresh_records(collection_view=self.id, block=self.collection.id)
            format_content = self.get("format")
            format_content = format_content if format_content is not None else {}
            yield format_content
        finally:
            format_content = {"format": format_content}
            self._submit_view_transaction(format_content)

    def refresh_view(self):
        self._client.refresh_records(collection_view=self.id, block=self.collection.id)

class BoardView(CollectionView):

    _type = "board"

    group_by = field_map("query2.group_by")
    board_cover = field_map("format.board_cover")
    board_cover_size = field_map("format.board_cover_size")
    board_cover_aspect = field_map("format.board_cover_aspect")

    def update_group_by(self, group_property):

        with self._update_query2() as query2_content:
            query2_content["group_by"] = self.collection.get_schema_property(group_property)["id"]

    def format_properties(self, properties_visibility, column_values_hidden,
                          board_cover=None, board_cover_size=None, board_cover_aspect=None):
        """
               Format TableView properties.
               properties_visibility: dict - {"property" : visible}
               column_values_hidden: list - group_by property {"default | value" : hidden}
               board_cover: str - page_content or page_cover
               board_cover_size: str - large, medium or small
               board_cover_aspect: str - cover or contain
        """
        properties_visibility = {slugify(key):v for key, v in properties_visibility.items()}
        """
            Proprerties Width can be set, however no behavior is currently observed on the interface. 
            properties_width: dict - {"properties" : width}
        """
        with self._update_format() as format_content:
            find_idx = lambda prop: [True if x["property"] == prop else False for x in
                                     format_content["board_properties"]].index(True)

            if "board_properties" not in format_content:
                format_content["board_properties"] = []

            for property in self.collection.get_schema_properties():
                property_id = property["id"]
                try:
                    idx = find_idx(property_id)
                except:
                    format_content["board_properties"].append({"property": property_id, "visible": True, "width": 200})
                    idx = len(format_content["board_properties"])-1

                if property["slug"] in properties_visibility:
                    format_content["board_properties"][idx]["visible"] = properties_visibility[property["slug"]]

                """
                if property["slug"] in properties_width:
                    format_content["board_properties"][idx]["width"] = properties_width[property["slug"]]
                """

                if property["id"] == self.group_by:
                    board_groups = []
                    if "default" in column_values_hidden:
                        board_groups.append({"property":property["id"], "value":{"type":property["type"]}, "hidden":column_values_hidden["default"]})
                    for option in property["options"]:
                        option_value = option["value"]
                        if option_value in column_values_hidden:
                            board_groups.append({"property": property["id"], "value": {"type": property["type"],
                                                                                        "value":option_value},
                                                  "hidden": column_values_hidden[option_value]})

            if board_cover is not None:
                is_property = self.collection.get_schema_property(board_cover)
                if is_property is not None:
                    format_content["board_cover"] = {"type": "property", "property": is_property["id"]}
                else:
                    format_content["board_cover"] = {"type": board_cover}

            format_content["board_cover_size"] = board_cover_size if board_cover_size is not None else format_content["board_cover_size"]
            format_content["board_cover_aspect"] = board_cover_aspect if board_cover_aspect is not None else format_content["board_cover_aspect"]
            format_content["board_groups2"] = board_groups if board_groups is not None else format_content["board_groups2"]


class TableView(CollectionView):

    _type = "table"


    def format_set_wrap_cell(self, wrap_cell):
        """
            wrap_cell: bool - Set Wrap Cells format in TableView
        """
        args = {"table_wrap": wrap_cell}
        self._submit_view_transaction(args, ["format"])


    def format_properties(self, properties_visibility, properties_width=None):
        """
               Format TableView properties.
               properties_visibility: dict - {"property" : visible}
               properties_width: dict - {"property" : width}
        """
        properties_visibility = {slugify(key): v for key, v in properties_visibility.items()}
        if properties_width is not None:
            properties_width = {slugify(key): v for key, v in properties_width.items()}

        with self._update_format() as format_content:
            find_idx = lambda prop: [True if x["property"] == prop else False for x in
                                     format_content["table_properties"]].index(True)

            if "table_properties" not in format_content:
                format_content["table_properties"] = []

            for property in self.collection.get_schema_properties():
                property_id = property["id"]
                try:
                    idx = find_idx(property_id)
                except:
                    format_content["table_properties"].append({"property": property_id, "visible": True, "width": 200})
                    idx = len(format_content["table_properties"])-1

                if property["slug"] in properties_visibility:
                    format_content["table_properties"][idx]["visible"] = properties_visibility[property["slug"]]

                if property["slug"] in properties_width:
                    format_content["table_properties"][idx]["width"] = properties_width[property["slug"]]



class ListView(CollectionView):

    _type = "list"

    def format_properties(self, properties_visibility, on_first_load_show=None):
        """
               Format CalendarView properties.
               properties_visibility: dict - {"property" : visible}
        """

        with self._update_format() as format_content:
            find_idx = lambda prop: [True if x["property"] == prop else False for x in format_content["list_properties"]].index(True)

            if "list_properties" not in format_content:
                format_content["list_properties"] = []

            if on_first_load_show is not None:
                format_content["inline_collection_first_load_limit"] = {"type":"load_limit", "limit":on_first_load_show}

            for property in self.collection.get_schema_properties():
                property_id = property["id"]
                try:
                    idx = find_idx(property_id)
                except:
                    format_content["list_properties"].append({"property": property_id, "visible": True})
                    idx = len(format_content["list_properties"])-1

                if property["slug"] in properties_visibility:
                    format_content["list_properties"][idx]["visible"] = properties_visibility[property["slug"]]

class CalendarView(CollectionView):

    _type = "calendar"

    calendar_by = field_map("query2.calendar_by")

    def build_query(self, **kwargs):
        calendar_by = self._client.get_record_data("collection_view", self._id)[
            "query"
        ]["calendar_by"]
        return super().build_query(calendar_by=calendar_by, **kwargs)

    def update_calendar_by(self, date_property):

        with self._update_query2() as query2_content:
            query2_content["calendar_by"] = self.collection.get_schema_property(date_property)["id"]

    def format_properties(self, properties_visibility):
        """
               Format CalendarView properties.
               properties_visibility: dict - {"property" : visible}
        """
        properties_visibility = {slugify(key): v for key, v in properties_visibility.items()}

        with self._update_format() as format_content:
            find_idx = lambda prop: [True if x["property"] == prop else False for x in format_content["calendar_properties"]].index(True)

            if "calendar_properties" not in format_content:
                format_content["calendar_properties"] = []

            for property in self.collection.get_schema_properties():
                property_id = property["id"]
                try:
                    idx = find_idx(property_id)
                except:
                    format_content["calendar_properties"].append({"property": property_id, "visible": True})
                    idx = len(format_content["calendar_properties"])-1

                if property["slug"] in properties_visibility:
                    format_content["calendar_properties"][idx]["visible"] = properties_visibility[property["slug"]]

class GalleryView(CollectionView):

    _type = "gallery"

    gallery_cover = field_map("format.gallery_cover")
    gallery_cover_size = field_map("format.gallery_cover_size")
    gallery_cover_aspect = field_map("format.gallery_cover_aspect")
    on_first_load_show = field_map("format.inline_collection_first_load_limit")


    def format_properties(self, properties_visibility, on_first_load_show=None,
                          gallery_cover=None, gallery_cover_size=None, gallery_cover_aspect=None):
        """
               Format TableView properties.
               properties_visibility: dict - {"property" : visible}
               column_values_hidden: list - group_by property {"default | value" : hidden}
               gallery_cover: str - page_content or page_cover
               gallery_cover_size: str - large, medium or small
               gallery_cover_aspect: str - cover or contain
        """
        properties_visibility = {slugify(key):v for key, v in properties_visibility.items()}

        with self._update_format() as format_content:
            find_idx = lambda prop: [True if x["property"] == prop else False for x in
                                     format_content["gallery_properties"]].index(True)

            if "gallery_properties" not in format_content:
                format_content["gallery_properties"] = []

            if on_first_load_show is not None:
                format_content["inline_collection_first_load_limit"] = {"type": "load_limit",
                                                                        "limit": on_first_load_show}

            for property in self.collection.get_schema_properties():
                property_id = property["id"]
                try:
                    idx = find_idx(property_id)
                except:
                    format_content["gallery_properties"].append({"property": property_id, "visible": True})
                    idx = len(format_content["gallery_properties"])-1

                if property["slug"] in properties_visibility:
                    format_content["gallery_properties"][idx]["visible"] = properties_visibility[property["slug"]]

            if gallery_cover is not None:
                is_property = self.collection.get_schema_property(gallery_cover)
                if is_property is not None:
                    format_content["gallery_cover"] = {"type": "property", "property": is_property["id"]}
                else:
                    format_content["gallery_cover"] = {"type": gallery_cover}

            format_content["gallery_cover_size"] = gallery_cover_size if gallery_cover_size is not None else format_content["gallery_cover_size"]
            format_content["gallery_cover_aspect"] = gallery_cover_aspect if gallery_cover_aspect is not None else format_content["gallery_cover_aspect"]


class TimelineView(CollectionView):

    _type = "timeline"

    timeline_by_end = field_map("query2.timeline_by_end")
    timeline_by = field_map("query2.timeline_by")
    on_first_load_show = field_map("format.inline_collection_first_load_limit")

    def update_timeline_by(self, date_property_start, date_property_end=None):

        with self._update_query2() as query2_content:
            query2_content["timeline_by"] = self.collection.get_schema_property(date_property_start)["id"]

            if date_property_end is not None:
                query2_content["timeline_by_end"] = self.collection.get_schema_property(date_property_end)["id"]


    def format_properties(self, timeline_properties_visibility, timeline_table_properties_visibility,
                          timeline_table_properties_width, timeline_preference=None,
                          timeline_show_table=None, on_first_load_show=None):
        """
               Format TimelineView properties.
               timeline_properties_visibility: dict - {"property": visible }
               timeline_table_properties_visibility: dict - {"property" : visible}
                timeline_table_properties_width: {"property" : width}
               timeline_preference: list - [zoomLevel, centerTimestamp:NotionDate]
               timeline_show_table: bool
               on_first_load_show: int - # of records to load on first show
        """

        timeline_table_properties_visibility = {slugify(key):v for key, v in timeline_table_properties_visibility.items()}
        timeline_properties_visibility = {slugify(key): v for key, v in timeline_properties_visibility.items()}
        timeline_table_properties_width = {slugify(key): v for key, v in timeline_table_properties_width.items()}

        with self._update_format() as format_content:
            find_idx = lambda prop: [True if x["property"] == prop else False for x in
                                     format_content["timeline_properties"]].index(True)

            find_idx_table = lambda prop: [True if x["property"] == prop else False for x in
                                     format_content["timeline_table_properties"]].index(True)

            if "timeline_properties" not in format_content:
                format_content["timeline_properties"] = []

            if "timeline_table_properties" not in format_content:
                format_content["timeline_table_properties"] = []

            if on_first_load_show is not None:
                format_content["inline_collection_first_load_limit"] = {"type": "load_limit",
                                                                        "limit": on_first_load_show}
            if timeline_show_table is not None:
                format_content["timeline_show_table"] = timeline_show_table

            if timeline_preference is not None:
                format_content["timeline_preference"] = {"zoomLevel":timeline_preference[0], "centerTimestamp":timeline_preference[1].timestamp()}

            for property in self.collection.get_schema_properties():
                property_id = property["id"]
                try:
                    idx = find_idx(property_id)
                except:
                    format_content["timeline_properties"].append({"property": property_id, "visible": True})
                    idx = len(format_content["timeline_properties"])-1

                if property["slug"] in timeline_properties_visibility:
                    format_content["timeline_properties"][idx]["visible"] = timeline_properties_visibility[property["slug"]]

                try:
                    idx = find_idx_table(property_id)
                except:
                    format_content["timeline_table_properties"].append({"property": property_id, "visible": True, "width":200})
                    idx = len(format_content["timeline_table_properties"])-1

                if property["slug"] in timeline_table_properties_visibility:
                    format_content["timeline_table_properties"][idx]["visible"] = timeline_table_properties_visibility[property["slug"]]

                if property["slug"] in timeline_table_properties_width:
                    format_content["timeline_table_properties"][idx]["width"] = timeline_table_properties_width[property["slug"]]





def _normalize_property_name(prop_name, collection):
    if not prop_name:
        return ""
    else:
        prop = collection.get_schema_property(prop_name)
        if not prop:
            return ""
        return prop["id"]


def _normalize_query_data(data, collection, recursing=False):
    if not recursing:
        data = deepcopy(data)
    if isinstance(data, list):
        return [
            _normalize_query_data(item, collection, recursing=True) for item in data
        ]
    elif isinstance(data, dict):
        # convert slugs to property ids
        if "property" in data:
            data["property"] = _normalize_property_name(data["property"], collection)
        # convert any instantiated objects into their ids
        if "value" in data:
            if hasattr(data["value"], "id"):
                data["value"] = data["value"].id
        for key in data:
            data[key] = _normalize_query_data(data[key], collection, recursing=True)
    return data


class CollectionQuery(object):
    def __init__(
        self,
        collection,
        collection_view,
        search="",
        type="table",
        aggregate=[],
        aggregations=[],
        filter=[],
        sort=[],
        calendar_by="",
        group_by="",
        limit=100
    ):
        assert not (
            aggregate and aggregations
        ), "Use only one of `aggregate` or `aggregations` (old vs new format)"
        self.collection = collection
        self.collection_view = collection_view
        self.search = search
        self.type = type
        self.aggregate = _normalize_query_data(aggregate, collection)
        self.aggregations = _normalize_query_data(aggregations, collection)
        self.filter = _normalize_query_data(filter, collection)
        self.sort = _normalize_query_data(sort, collection)
        self.calendar_by = _normalize_property_name(calendar_by, collection)
        self.group_by = _normalize_property_name(group_by, collection)
        self.limit = limit
        self._client = collection._client

    def execute(self):

        result_class = QUERY_RESULT_TYPES.get(self.type, QueryResult)

        kwargs = {
            'collection_id':self.collection.id,
            'collection_view_id':self.collection_view.id,
            'search':self.search,
            'type':self.type,
            'aggregate':self.aggregate,
            'aggregations':self.aggregations,
            'filter':self.filter,
            'sort':self.sort,
            'calendar_by':self.calendar_by,
            'group_by':self.group_by,
            'limit':0
        }

        if self.limit == -1:
            # fetch remote total 
            result = self._client.query_collection(
                **kwargs
            )
            self.limit = result.get("total",-1)

        kwargs['limit'] = self.limit

        return result_class(
            self.collection,
            self._client.query_collection(
                **kwargs
            ),
            self,
        )


class CollectionRowBlock(PageBlock):
    @property
    def is_template(self):
        return self.get("is_template")

    @cached_property
    def collection(self):
        return self._client.get_collection(self.get("parent_id"))

    @property
    def schema(self):
        return [
            prop
            for prop in self.collection.get_schema_properties()
            if prop["type"] not in ["formula", "rollup"]
        ]

    def __getattr__(self, attname):
        return self.get_property(attname)

    def __setattr__(self, attname, value):
        if attname.startswith("_"):
            # we only allow setting of new non-property attributes that start with "_"
            super().__setattr__(attname, value)
        elif attname in self._get_property_slugs():
            self.set_property(attname, value)
        elif slugify(attname) in self._get_property_slugs():
            self.set_property(slugify(attname), value)
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
            raise AttributeError(
                "Object does not have property '{}'".format(identifier)
            )

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
            old = self._convert_notion_to_python(
                old_val.get("properties", {}).get(prop_id), prop
            )
            new = self._convert_notion_to_python(
                new_val.get("properties", {}).get(prop_id), prop
            )
            changes.append(("prop_changed", prop["slug"], (old, new)))

        return changes + super()._convert_diff_to_changelist(
            remaining, old_val, new_val
        )

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
            val = (
                [self._client.get_user(item[1][0][1]) for item in val if item[0] == "‣"]
                if val
                else []
            )
        if prop["type"] in ["email", "phone_number", "url"]:
            val = val[0][0] if val else ""
        if prop["type"] in ["date"]:
            val = NotionDate.from_notion(val)
        if prop["type"] in ["file"]:
            val = (
                [
                    add_signed_prefix_as_needed(
                        item[1][0][1], client=self._client, id=self.id
                    )
                    for item in val
                    if item[0] != ","
                ]
                if val
                else []
            )
        if prop["type"] in ["checkbox"]:
            val = val[0][0] == "Yes" if val else False
        if prop["type"] in ["relation"]:
            val = (
                [
                    self._client.get_block(item[1][0][1])
                    for item in val
                    if item[0] == "‣"
                ]
                if val
                else []
            )
        if prop["type"] in ["created_time", "last_edited_time"]:
            val = self.get(prop["type"])
            val = datetime.utcfromtimestamp(val / 1000)
        if prop["type"] in ["created_by", "last_edited_by"]:
            val = self.get(prop["type"] + "_id")
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
            raise AttributeError(
                "Object does not have property '{}'".format(identifier)
            )
        if prop["type"] in ["select"] or prop["type"] in ["multi_select"]:
            schema_update, prop = self.collection.check_schema_select_options(prop, val)
            if schema_update:
                self.collection.set(
                    "schema.{}.options".format(prop["id"]), prop["options"]
                )

        path, val = self._convert_python_to_notion(val, prop, identifier=identifier)

        self.set(path, val)

    def _convert_python_to_notion(self, val, prop, identifier="<unknown>"):

        if prop["type"] in ["title", "text"]:
            if not val:
                val = ""
            if not isinstance(val, str):
                raise TypeError(
                    "Value passed to property '{}' must be a string.".format(identifier)
                )
            val = markdown_to_notion(val)
        if prop["type"] in ["number"]:
            if val is not None:
                if not isinstance(val, float) and not isinstance(val, int):
                    raise TypeError(
                        "Value passed to property '{}' must be an int or float.".format(
                            identifier
                        )
                    )
                val = [[str(val)]]
        if prop["type"] in ["select"]:
            if not val:
                val = None
            else:
                valid_options = [p["value"].lower() for p in prop["options"]]
                val = val.split(",")[0]
                if val.lower() not in valid_options:
                    raise ValueError(
                        "Value '{}' not acceptable for property '{}' (valid options: {})".format(
                            val, identifier, valid_options
                        )
                    )
                val = [[val]]
        if prop["type"] in ["multi_select"]:
            if not val:
                val = []
            valid_options = [p["value"].lower() for p in prop["options"]]
            if not isinstance(val, list):
                val = [val]
            for v in val:
                if v and v.lower() not in valid_options:
                    raise ValueError(
                        "Value '{}' not acceptable for property '{}' (valid options: {})".format(
                            v, identifier, valid_options
                        )
                    )
            val = [[",".join(val)]]
        if prop["type"] in ["person"]:
            userlist = []
            if not isinstance(val, list):
                val = [val]
            for user in val:
                user_id = user if isinstance(user, str) else user.id
                userlist += [["‣", [["u", user_id]]], [","]]
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
                filelist += [[filename, [["a", url]]], [","]]
            val = filelist[:-1]
        if prop["type"] in ["checkbox"]:
            if not isinstance(val, bool):
                raise TypeError(
                    "Value passed to property '{}' must be a bool.".format(identifier)
                )
            val = [["Yes" if val else "No"]]
        if prop["type"] in ["relation"]:
            pagelist = []
            if not isinstance(val, list):
                val = [val]
            for page in val:
                if isinstance(page, str):
                    page = self._client.get_block(page)
                pagelist += [["‣", [["p", page.id]]], [","]]
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
                id=self.id, path=[], args={"alive": False}, command="update"
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
    def __init__(self, collection, result, query):
        self.collection = collection
        self._client = collection._client
        self._block_ids = self._get_block_ids(result)
        self.total = result.get("total", -1)
        self.aggregates = result.get("aggregationResults", [])
        self.aggregate_ids = [
            agg.get("id") for agg in (query.aggregate or query.aggregations)
        ]
        self.query = query

    def _get_block_ids(self, result):
        return result['reducerResults']['collection_group_results']["blockIds"]

    def _get_block(self, id):
        block = CollectionRowBlock(self._client, id)
        block.__dict__["collection"] = self.collection
        return block

    def get_aggregate(self, id):
        for agg_id, agg in zip(self.aggregate_ids, self.aggregates):
            if id == agg_id:
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


COLLECTION_VIEW_TYPES = {
    cls._type: cls
    for cls in locals().values()
    if type(cls) == type and issubclass(cls, CollectionView) and hasattr(cls, "_type")
}

QUERY_RESULT_TYPES = {
    cls._type: cls
    for cls in locals().values()
    if type(cls) == type and issubclass(cls, QueryResult) and hasattr(cls, "_type")
}
