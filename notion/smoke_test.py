from datetime import datetime

from .client import *
from .block import *
from .collection import NotionDate



def run_live_smoke_test(token_v2, parent_page_url_or_id):

    client = NotionClient(token_v2=token_v2)

    parent_page = client.get_block(parent_page_url_or_id)

    page = parent_page.children.add_new(
        PageBlock,
        title="Smoke test at {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )

    print("Created base smoke test page at:", page.get_browseable_url())

    #format PageBlock

    page.set_full_width(True)
    page.set_page_font("mono")
    page.set_small_text(True)
    page.children.add_new(TextBlock, title="Page settings should be:\n - Full width: set\n - Small text: set \n - Page Font: Mono ")

    #set cover with local notion file
    page.set_page_cover("/images/page-cover/nasa_space_shuttle_columbia_and_sunrise.jpg", 0.8)

    page.set_page_cover("https://www.birdlife.org/sites/default/files/styles/1600/public/slide.jpg", 0.1)

    page.set_page_cover_position(0.7)
    icon = "📫"

    page.set_page_icon(icon)

    col_list = page.children.add_new(ColumnListBlock)
    col1 = col_list.children.add_new(ColumnBlock)
    col2 = col_list.children.add_new(ColumnBlock)
    col1kid = col1.children.add_new(
        TextBlock, title="Some formatting: *italic*, **bold**, ***both***!"
    )
    assert (
        col1kid.title.replace("_", "*")
        == "Some formatting: *italic*, **bold**, ***both***!"
    )
    assert col1kid.title_plaintext == "Some formatting: italic, bold, both!"
    col2.children.add_new(TodoBlock, title="I should be unchecked")
    col2.children.add_new(TodoBlock, title="I should be checked", checked=True)

    page.children.add_new(HeaderBlock, title="The finest music:")
    video = page.children.add_new(VideoBlock, width=100)
    video.set_source_url("https://www.youtube.com/watch?v=oHg5SJYRHA0")

    assert video in page.children
    assert col_list in page.children
    assert video in page.children.filter(VideoBlock)
    assert col_list not in page.children.filter(VideoBlock)

    # check that the parent does not yet consider this page to be backlinking
    assert page not in parent_page.get_backlinks()

    page.children.add_new(SubheaderBlock, title="A link back to where I came from:")
    alias = page.children.add_alias(parent_page)
    assert alias.is_alias
    assert not page.is_alias
    page.children.add_new(
        QuoteBlock,
        title="Clicking [here]({}) should take you to the same place...".format(
            page.parent.get_browseable_url()
        ),
    )

    # check that the parent now knows about the backlink
    assert page in parent_page.get_backlinks()

    # ensure __repr__ methods are not breaking
    repr(page)
    repr(page.children)
    for child in page.children:
        repr(child)

    page.children.add_new(
        SubheaderBlock, title="The order of the following should be alphabetical:"
    )

    B = page.children.add_new(BulletedListBlock, title="B")
    D = page.children.add_new(BulletedListBlock, title="D")
    C2 = page.children.add_new(BulletedListBlock, title="C2")
    C1 = page.children.add_new(BulletedListBlock, title="C1")
    C = page.children.add_new(BulletedListBlock, title="C")
    A = page.children.add_new(BulletedListBlock, title="A")

    D.move_to(C, "after")
    A.move_to(B, "before")
    C2.move_to(C)
    C1.move_to(C, "first-child")

    page.children.add_new(CalloutBlock, title="I am a callout", icon="🤞")



    cvb = page.children.add_new(CollectionViewBlock)
    cvb.collection = client.get_collection(
        client.create_record("collection", parent=cvb, schema=get_collection_schema())
    )
    cvb.title = "My data!"
    view = cvb.views.add_new(view_type="table")

    special_code = uuid.uuid4().hex[:8]

    # add a row
    row1 = cvb.collection.add_row()
    assert row1.person == []
    row1.name = "Just some data"
    row1.title = "Can reference 'title' field too! " + special_code
    assert row1.name == row1.title
    row1.check_yo_self = True
    row1.estimated_value = None
    row1.estimated_value = 42
    row1.files = [
        "https://www.birdlife.org/sites/default/files/styles/1600/public/slide.jpg"
    ]
    row1.tags = None
    row1.tags = []
    row1.tags = ["A", "C"]
    row1.where_to = "https://learningequality.org"
    row1.category = "A"
    row1.category = ""
    row1.category = None
    row1.category = "B"

    start = datetime.strptime("2021-01-01 09:30", "%Y-%m-%d %H:%M")
    end = datetime.strptime("2021-01-05 20:45", "%Y-%m-%d %H:%M")
    timezone = "America/Los_Angeles"
    reminder = {"unit": "minute", "value": 30}
    row1.some_date = NotionDate(start, end=end, timezone=timezone, reminder=reminder)
    another_start = datetime.strptime("2021-02-01 09:30", "%Y-%m-%d %H:%M")
    another_end = datetime.strptime("2021-02-03 20:45", "%Y-%m-%d %H:%M")
    row1.another_date = NotionDate(another_start, end=another_end, timezone=timezone, reminder=reminder)

    # add another row
    row2 = cvb.collection.add_row(person=client.current_user, title="Metallic penguins")
    assert row2.person == [client.current_user]
    assert row2.name == "Metallic penguins"
    row2.check_yo_self = False
    row2.estimated_value = 22
    row2.files = [
        "https://www.picclickimg.com/d/l400/pict/223603662103_/Vintage-Small-Monet-and-Jones-JNY-Enamel-Metallic.jpg"
    ]
    row2.tags = ["A", "B"]
    row2.where_to = "https://learningequality.org"
    row2.category = "C"

    # check that options "C" have been added to the schema
    for prop in ["=d{|", "=d{q"]:
        assert cvb.collection.get("schema.{}.options.2.value".format(prop)) == "C"

    # check that existing options "A" haven't been affected
    for prop in ["=d{|", "=d{q"]:
        assert (
            cvb.collection.get("schema.{}.options.0.id".format(prop))
            == get_collection_schema()[prop]["options"][0]["id"]
        )

    # Run a filtered/sorted query using the view's default parameters
    result = view.default_query().execute()
    assert row1 == result[0]
    assert row2 == result[1]
    assert len(result) == 2

    # query the collection directly
    assert row1 in cvb.collection.get_rows(search=special_code)
    assert row2 not in cvb.collection.get_rows(search=special_code)
    assert row1 not in cvb.collection.get_rows(search="penguins")
    assert row2 in cvb.collection.get_rows(search="penguins")

    # search the entire space
    # Search endpoint is currently returning no results when searching for special_code and 'penguins'.

    #assert row1 in client.search_blocks(search=special_code)
    #assert row1 not in client.search_blocks(search="penguins")
    #assert row2 not in client.search_blocks(search=special_code)
    #assert row2 in client.search_blocks(search="penguins")

    #format TableView


    #Wrap Cell property
    view.format_set_wrap_cell(True)

    view.refresh_view()
    view_format = view.get("format")
    assert view_format["table_wrap"]

    # Property visibility and width
    property_visibility = {"Estimated Value": False}
    property_width = {"category": 100}
    view.format_properties(property_visibility, property_width)

    tableProperties_findIdx = lambda prop: [True if x["property"] == prop else False for x in
                                    view_format["table_properties"]].index(True)

    view.refresh_view()
    view_format = view.get("format")

    property_id = view.collection.get_schema_property("Estimated Value")["id"]
    idx = tableProperties_findIdx(property_id)
    assert not view_format["table_properties"][idx]["visible"]

    property_id = view.collection.get_schema_property("category")["id"]
    idx = tableProperties_findIdx(property_id)
    assert view_format["table_properties"][idx]["width"] == 100

    # Add Filter to TableView
    view_filter = [{"or": [["name", "string_contains", "exact", "Metallic"]]},
                   {"or": [["person", "is_empty", "", ""],["category", "enum_is", "exact", "A"]]}]
    view.update_view_filter(view_filter)

    view.refresh_view()
    view_query = view.get("query2")

    assert view_query["filter"] == get_expected_filter()

    # Add Sort to TableView
    view.update_view_sort([["name","descending"]])

    view.refresh_view()
    view_query = view.get("query2")

    assert view_query["sort"] == [{"property":"title","direction":"descending"}]

    # Add Aggregator to TableView
    view.update_view_aggregation([["name","count"]])

    view.refresh_view()
    view_query = view.get("query2")

    assert view_query["aggregations"] == [{"property": "title", "aggregator": "count"}]


    #Format BoardView

    board_view = cvb.views.add_new(view_type="board")

    board_view.update_group_by("tags")

    board_view.refresh_view()

    assert board_view.group_by == view.collection.get_schema_property("tags")["id"]

    # Formatting can set visibility of properties, visibility and width of columns, board_cover, board_cover_size and board_cover_aspect
    properties_visibility = {"files":False, "Estimated Value": False}
    column_values_hidden = {"default": True, "B":True}

    board_view.format_properties(properties_visibility, column_values_hidden, "files", "large", "contain")

    board_view.refresh_view()

    view_format = board_view.get("format")
    assert view_format == get_expected_board_format()

    #Format CalendarView
    calendar_view = cvb.views.add_new(view_type="calendar")

    calendar_view.update_calendar_by("Another Date")

    calendar_view.refresh_view()
    assert calendar_view.calendar_by == view.collection.get_schema_property("Another Date")["id"]

    calendar_view.format_properties(properties_visibility)

    view_format = calendar_view.get("format")
    assert view_format == get_expected_calendar_format()

    #Format GalleryView
    gallery_view = cvb.views.add_new(view_type="gallery")

    gallery_view.format_properties(properties_visibility, 100, "files", "large", "contain")

    view_format = gallery_view.get("format")
    assert view_format == get_expected_gallery_format()

    #Format TimelineView
    timeline_view = cvb.views.add_new(view_type="timeline")

    timeline_view.update_timeline_by("Another Date","Some Date")

    timeline_view.refresh_view()
    assert timeline_view.timeline_by == view.collection.get_schema_property("Another Date")["id"]
    assert timeline_view.timeline_by_end == view.collection.get_schema_property("Some Date")["id"]

    centerTime = datetime.strptime("2021-01-01 09:30", "%Y-%m-%d %H:%M")
    timeline_preference = ["year", centerTime]
    timeline_table_properties_visibility = {"files": True, "Estimated Value": True, "Category": False, "Another Date": False, "Person":True}
    timeline_table_properties_width = {"files": 200, "Estimated Value": 100, "Person":500}
    timeline_properties_visibility = {"another date": False, "person": False}
    on_first_load_show = 100
    timeline_show_table = True

    timeline_view.format_properties(timeline_properties_visibility, timeline_table_properties_visibility,
                                    timeline_table_properties_width,
                                    timeline_preference, timeline_show_table, on_first_load_show)

    view_format = timeline_view.get("format")
    assert view_format == get_expected_timeline_format()

    #Format ListView
    list_view = cvb.views.add_new(view_type="list")

    properties_visibility = {"files": False, "Estimated Value": False}
    list_view.format_properties(properties_visibility, on_first_load_show)

    view_format = list_view.get("format")
    assert view_format == get_expected_list_format()

    # Run an "aggregation" query
    aggregations = [
        {"property": "estimated_value", "aggregator": "sum", "id": "total_value"}
    ]
    result = view.build_query(aggregations=aggregations).execute()
    assert result.get_aggregate("total_value") == 64

    # Run a "filtered" query
    filter_params = {
        "filters": [
            {
                "filter": {
                    "value": {
                        "type": "exact",
                        "value": {"table": "notion_user", "id": client.current_user.id},
                    },
                    "operator": "person_does_not_contain",
                },
                "property": "person",
            }
        ],
        "operator": "and",
    }
    result = view.build_query(filter=filter_params).execute()
    assert row1 in result
    assert row2 not in result

    # Run a "sorted" query
    sort_params = [{"direction": "ascending", "property": "estimated_value"}]
    result = view.build_query(sort=sort_params).execute()
    assert row1 == result[1]
    assert row2 == result[0]

    # Test that reminders and time zone's work properly
    row1.refresh()
    assert row1.some_date.start == start
    assert row1.some_date.end == end
    assert row1.some_date.timezone == timezone
    assert row1.some_date.reminder == reminder

    print(
        "Check it out and make sure it looks good, then press any key here to delete it..."
    )
    input()

    _delete_page_fully(page)



def _delete_page_fully(page):

    id = page.id

    parent_page = page.parent

    assert page.get("alive") == True
    assert page in parent_page.children
    page.remove()
    assert page.get("alive") == False
    assert page not in parent_page.children

    assert (
        page.space_info
    ), "Page {} was fully deleted prematurely, as we can't get space info about it anymore".format(
        id
    )

    page.remove(permanently=True)

    time.sleep(1)

    assert (
        not page.space_info
    ), "Page {} was not really fully deleted, as we can still get space info about it".format(
        id
    )

def get_expected_filter():
    return {"operator":"or", "filters":[{'filter': {'value': {'type': 'exact', 'value': 'Metallic'}, 'operator': 'string_contains'}, 'property': 'title'},
            {'filters': [{'filter': {'value': {'type': '', 'value': ''}, 'operator': 'is_empty'}, 'property': 'LL[('},
                         {'filter': {'value': {'type': 'exact', 'value': 'A'}, 'operator': 'enum_is'}, 'property': '=d{q'}], 'operator': 'or'}]}

def get_expected_list_format():
    return {'list_properties': [{'property': '%9:q', 'visible': True}, {'property': '4Jv$', 'visible': True},
                                {'property': '=d{q', 'visible': True}, {'property': '=d{|', 'visible': True},
                                {'property': 'LL[(', 'visible': True}, {'property': 'OBcJ', 'visible': True},
                                {'property': 'TwR:', 'visible': True},
                                {'property': 'dV$q', 'visible': False}, {'property': 'qXLc', 'visible': True},
                                {'property': 'title', 'visible': True}],
            'inline_collection_first_load_limit': {'type': 'load_limit', 'limit': 100}}

def get_expected_timeline_format():

    return {'timeline_properties':
                [{'property': '%9:q', 'visible': True},
                 {'property': '4Jv$', 'visible': True},
                 {'property': '=d{q', 'visible': True},
                 {'property': '=d{|', 'visible': True},
                 {'property': 'LL[(', 'visible': False},
                 {'property': 'OBcJ', 'visible': True},
                 {'property': 'TwR:', 'visible': True},
                 {'property': 'dV$q', 'visible': True},
                 {'property': 'qXLc', 'visible': False},
                 {'property': 'title', 'visible': True}],
            'timeline_table_properties': [{'property': '%9:q', 'visible': True, 'width': 200},
                                          {'property': '4Jv$', 'visible': True, 'width': 100},
                                          {'property': '=d{q', 'visible': False, 'width': 200},
                                          {'property': '=d{|', 'visible': True, 'width': 200},
                                          {'property': 'LL[(', 'visible': True, 'width': 500},
                                          {'property': 'OBcJ', 'visible': True, 'width': 200},
                                          {'property': 'TwR:', 'visible': True, 'width': 200},
                                          {'property': 'dV$q', 'visible': True, 'width': 200},
                                          {'property': 'qXLc', 'visible': False, 'width': 200},
                                          {'property': 'title', 'visible': True, 'width': 200}],
            'inline_collection_first_load_limit': {'type': 'load_limit', 'limit': 100},
            'timeline_show_table': True,
            'timeline_preference': {'zoomLevel': 'year', 'centerTimestamp': 1609504200.0}}

def get_expected_calendar_format():
    return {'calendar_properties':
                [{'property': '%9:q', 'visible': True},
                 {'property': '4Jv$', 'visible': False},
                 {'property': '=d{q', 'visible': True},
                 {'property': '=d{|', 'visible': True},
                 {'property': 'LL[(', 'visible': True},
                 {'property': 'OBcJ', 'visible': True},
                 {'property': 'TwR:', 'visible': True},
                 {'property': 'dV$q', 'visible': False},
                 {'property': 'qXLc', 'visible': True},
                 {'property': 'title', 'visible': True}]}

def get_expected_board_format():
    return {'board_cover': {'type': 'property', 'property': 'dV$q'},
            'board_groups2': [{'value': {'type': 'multi_select'}, 'hidden': True, 'property': '=d{|'},
                              {'value': {'type': 'multi_select', 'value': 'B'}, 'hidden': True, 'property': '=d{|'}],
            'board_cover_size': 'large',
            'board_properties': [{'width': 200, 'visible': True, 'property': '%9:q'},
                                 {'width': 200, 'visible': False, 'property': '4Jv$'},
                                 {'width': 200, 'visible': True, 'property': '=d{q'},
                                 {'width': 200, 'visible': True, 'property': '=d{|'},
                                 {'width': 200, 'visible': True, 'property': 'LL[('},
                                 {'width': 200, 'visible': True, 'property': 'OBcJ'},
                                 {'width': 200, 'visible': True, 'property': 'TwR:'},
                                 {'width': 200, 'visible': False, 'property': 'dV$q'},
                                 {'width': 200, 'visible': True, 'property': 'qXLc'},
                                 {'width': 200, 'visible': True, 'property': 'title'}],
            'board_cover_aspect': 'contain'}

def get_expected_gallery_format():
    return{'gallery_properties': [{'property': '%9:q', 'visible': True}, {'property': '4Jv$', 'visible': False},
                            {'property': '=d{q', 'visible': True}, {'property': '=d{|', 'visible': True},
                            {'property': 'LL[(', 'visible': True}, {'property': 'OBcJ', 'visible': True},
                            {'property': 'TwR:', 'visible': True}, {'property': 'dV$q', 'visible': False},
                            {'property': 'qXLc', 'visible': True}, {'property': 'title', 'visible': True}],
     'inline_collection_first_load_limit': {'type': 'load_limit', 'limit': 100},
     'gallery_cover': {'type': 'property', 'property': 'dV$q'}, 'gallery_cover_size': 'large',
     'gallery_cover_aspect': 'contain'}

def get_collection_schema():
    return {
        "%9:q": {"name": "Check Yo'self", "type": "checkbox"},
        "=d{|": {
            "name": "Tags",
            "type": "multi_select",
            "options": [
                {
                    "color": "orange",
                    "id": "79560dab-c776-43d1-9420-27f4011fcaec",
                    "value": "A",
                },
                {
                    "color": "default",
                    "id": "002c7016-ac57-413a-90a6-64afadfb0c44",
                    "value": "B",
                },
            ],
        },
        "=d{q": {
            "name": "Category",
            "type": "select",
            "options": [
                {
                    "color": "orange",
                    "id": "59560dab-c776-43d1-9420-27f4011fcaec",
                    "value": "A",
                },
                {
                    "color": "default",
                    "id": "502c7016-ac57-413a-90a6-64afadfb0c44",
                    "value": "B",
                },
            ],
        },
        "LL[(": {"name": "Person", "type": "person"},
        "4Jv$": {"name": "Estimated value", "type": "number"},
        "OBcJ": {"name": "Where to?", "type": "url"},
        "TwR:": {"name": "Some Date", "type": "date"},
        "qXLc": {"name": "Another Date", "type": "date"},
        "dV$q": {"name": "Files", "type": "file"},
        "title": {"name": "Name", "type": "title"},
    }
