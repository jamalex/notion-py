from datetime import datetime

from .client import *
from .block import *


def run_live_smoke_test(token_v2, parent_page_url_or_id):

    client = NotionClient(token_v2=token_v2)

    parent_page = client.get_block(parent_page_url_or_id)

    page = parent_page.children.add_new(PageBlock, title="Smoke test at {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    print("Created base smoke test page at:", page.get_browseable_url())

    col_list = page.children.add_new(ColumnListBlock)
    col1 = col_list.children.add_new(ColumnBlock)
    col2 = col_list.children.add_new(ColumnBlock)
    col1.children.add_new(TextBlock, title="Some formatting: *italic*, **bold**, ***both***!")
    col2.children.add_new(TodoBlock, title="I should be unchecked")
    col2.children.add_new(TodoBlock, title="I should be checked", checked=True)

    page.children.add_new(HeaderBlock, title="The finest music:")
    video = page.children.add_new(VideoBlock, width=100)
    video.set_source_url("https://www.youtube.com/watch?v=oHg5SJYRHA0")

    assert video in page.children
    assert col_list in page.children
    assert video in page.children.filter(VideoBlock)
    assert col_list not in page.children.filter(VideoBlock)

    page.children.add_new(SubheaderBlock, title="A link back to where I came from:")
    alias = page.children.add_alias(parent_page)
    assert alias.is_alias
    assert not page.is_alias
    page.children.add_new(QuoteBlock, title="Clicking [here]({}) should take you to the same place...".format(page.parent.get_browseable_url()))

    # ensure __repr__ methods are not breaking
    repr(page)
    repr(page.children)
    for child in page.children:
        repr(child)

    page.children.add_new(SubheaderBlock, title="The order of the following should be alphabetical:")

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

    cvb = page.children.add_new(CollectionViewBlock)
    collection = client.get_collection(client.create_record("collection", parent=cvb, schema=get_collection_schema()))
    view = client.get_collection_view(client.create_record("collection_view", parent=cvb, type="table"), collection=collection)
    view.set("collection_id", collection.id)
    cvb.set("collection_id", collection.id)
    cvb.set("view_ids", [view.id])
    cvb.title = "My data!"

    row = collection.add_row()
    row.name = "Just some data"
    row.check_yo_self = True
    row.files = ["https://www.birdlife.org/sites/default/files/styles/1600/public/slide.jpg"]
    row.person = client.current_user
    row.tags = ["A", "C"]
    row.where_to = "https://learningequality.org"
    
    print("Check it out and make sure it looks good, then press any key here to delete it...")
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

    assert page.space_info, "Page {} was fully deleted prematurely, as we can't get space info about it anymore".format(id)

    page.remove(permanently=True)

    time.sleep(1)

    assert not page.space_info, "Page {} was not really fully deleted, as we can still get space info about it".format(id)


def get_collection_schema():
    return {
        "%9:q": {"name": "Check Yo'self", "type": "checkbox"},
        "=d{|": {
            "name": "Tags",
            "type": "multi_select",
            "options": [{
                "color": "orange",
                "id": "79560dab-c776-43d1-9420-27f4011fcaec",
                "value": "A"
            }, {
                "color": "default",
                "id": "002c7016-ac57-413a-90a6-64afadfb0c44",
                "value": "B"
            }, {
                "color": "blue",
                "id": "77f431ab-aeb2-48c2-9e40-3a630fb86a5b",
                "value": "C"
            }]},
        "LL[(": {"name": "Person", "type": "person"},
        "OBcJ": {"name": "Where to?", "type": "url"},
        "dV$q": {"name": "Files", "type": "file"},
        "title": {"name": "Name", "type": "title"}
    }