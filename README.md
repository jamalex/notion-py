# notion-py
Unofficial alpha Python API client for Notion.so

Warning: This is still experimental/incomplete, and has not yet been packaged. To use it, clone the repo and add the repo  directory to your `PYTHONPATH`.

## Usage example

Obtain the `token_v2` value by inspecting your browser cookies on a logged-in session on Notion.so.

```Python
from notion.client import NotionClient

client = NotionClient(token_v2="<token_v2>")

page = client.get_block("https://www.notion.so/myorg/Test-c0d20a71c0944985ae96e661ccc99821")

page.title = "The title has now changed!"
```








## TODO

* Utilities to support updating/creating collection schemas
* Utilities to support updating/creating collection_view queries
* Websocket support for live block cache updating
* "Render full page to markdown" mode
* "Import page from html" mode