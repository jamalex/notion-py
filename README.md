# notion-py

Unofficial Python 3 client for Notion.so API v3

Warning: This is still somewhat experimental, and doesn't have 100% API coverage. Issues and pull requests welcome!

# Usage

## Quickstart

`pip install notion`

```Python
from notion.client import NotionClient

# Obtain the `token_v2` value by inspecting your browser cookies on a logged-in session on Notion.so
client = NotionClient(token_v2="<token_v2>")

# Replace this URL with the URL of the page you want to edit
page = client.get_block("https://www.notion.so/myorg/Test-c0d20a71c0944985ae96e661ccc99821")

print("The old title is:", page.title)

# Note: You can use Markdown! We convert on-the-fly to Notion's internal formatted text data structure.
page.title = "The title has now changed, and has *live-updated* in the browser!"
```

## Concepts and notes

- We map tables in the Notion database into Python classes (subclassing `Record`), with each instance of a class representing a particular record. Some fields from the records (like `title` in the example above) have been mapped to model properties, allowing for easy, instantaneous read/write of the record. Other fields can be read with the `get` method, and written with the `set` method, but then you'll need to make sure to match the internal structures exactly.
- The tables we currently support are **block** (via `Block` class and its subclasses, corresponding to different `type` of blocks), **space** (via `Space` class), **collection** (via `Collection` class), **collection_view** (via `CollectionView` and subclasses), and **notion_user** (via `User` class).
- Data for all tables are stored in a central `RecordStore`, with the `Record` instances not storing state internally, but always referring to the data in the central `RecordStore`. Many API operations return updating versions of a large number of associated records, which we use to update the store, so the data in `Record` instances may sometimes update without being explicitly requested. You can also call the `refresh` method on a `Record` to trigger an update, or pass `force_update` to methods like `get`.
- The API doesn't have strong validation of most data, so be careful to maintain the structures Notion is expecting. You can view the full internal structure of a record by calling `myrecord.get()` with no arguments.
- When you call `client.get_block`, you can pass in either an ID, or the URL of a page. Note that pages themselves are just `blocks`, as are all the chunks of content on the page. You can get the URL for a block within a page by clicking "Copy Link" in the context menu for the block, and pass that URL into `get_block` as well.


## Example: Traversing the block tree

```Python
for child in page.children:
    print(child.title)

print("Parent of {} is {}".format(page.id, page.parent.id))
```

## Example: Adding a new node

```Python
newchild = page.children.add_new(TodoBlock, title="Something to get done")
newchild.checked = True
```

## Example: Deleting nodes

```Python
# soft-delete
page.remove()

# hard-delete
page.remove(permanently=True)
```

## Create an embedded content type (iframe, video, etc)

```Python
video = page.children.add_new(VideoBlock, width=200)
# sets "property.source" to the URL, and "format.display_source" to the embedly-converted URL
video.set_source_url("https://www.youtube.com/watch?v=oHg5SJYRHA0")
```

## Moving blocks around

```Python
# move my block to after the video
my_block.move_to(video, "after")

# move my block to the end of otherblock's children
my_block.move_to(otherblock, "last-child")

# (you can also use "before" and "first-child")
```

# TODO

* Support inline "user" and "page" links, and reminders, in markdown conversion
* Utilities to support updating/creating collection schemas
* Utilities to support updating/creating collection_view queries
* Support for easily managing page permissions
* Websocket support for live block cache updating
* "Render full page to markdown" mode
* "Import page from html" mode