from utils import extract_id
from maps import property_map, field_map, joint_map
from operations import build_operation

class Block(object):
    """
    Most data in Notion is stored as a "block" (including pages, and all the individual elements within a page).
    These blocks have different types, and in some cases we create subclasses of this class to represent those types.
    Attributes on the Block are mapped to useful attributes of the server-side data structure, as properties, so you can
    get and set values on the API just by reading/writing attributes on these classes. We store a shared local cache on
    the `NotionClient` object of all block data, and reference that as needed from here. Data can be refreshed from the
    server using the `refresh` method.
    """

    type = field_map("type")
    alive = field_map("alive")

    def __init__(self, client, block_id, *args, **kwargs):
        self.client = client
        self.block_id = extract_id(block_id)

    def refresh(self):
        """
        Update the cached data for this block from the server (data for other blocks may be updated as a side effect).
        """
        self.client.update_block_cache(self.block_id)

    def _get_block_data(self):
        if self.block_id not in self.client.block_cache:
            self.refresh()
        return self.client.block_cache[self.block_id]

    def get(self, path=[], refresh=False):
        """
        Retrieve cached data for this block. The `path` is a list (or dot-delimited string) the specifies the field
        to retrieve the value for. If no path is supplied, return the entire cached data structure for this block.
        If `refresh` is set to True, we refresh the data cache from the server before reading the values.
        """
        if refresh:
            self.refresh()
        if isinstance(path, str):
            path = path.split(".")
        value = self._get_block_data()["value"]
        try:
            for key in path:
                value = value[key]
        except KeyError:
            value = None
        return value

    def set(self, path, value, refresh=True):
        """
        Set a specific `value` (under the specific `path`) on the block's data structure on the server.
        If `refresh` is set to True, we refresh the data cache from the server after sending the update.
        """
        self.client.submit_transaction(build_operation(id=self.block_id, path=path, args=value))
        if refresh:
            self.refresh()


class BasicBlock(Block):

    title = property_map("title")
    color = field_map("format.block_color")


class TodoBlock(BasicBlock):

    checked = property_map("checked", python_to_api=lambda x: "Yes" if x else "No", api_to_python=lambda x: x == "Yes")


class CodeBlock(BasicBlock):

    language = property_map("language")
    wrap = field_map("format.code_wrap")


class MediaBlock(Block):

    caption = property_map("caption")


class ImageBlock(MediaBlock):
    
    width = field_map("format.block_width")


class EmbedBlock(MediaBlock):

    source = joint_map(field_map("format.display_source"), property_map("source"))
    height = field_map("format.block_height")
    full_width = field_map("format.block_full_width")
    page_width = field_map("format.block_page_width")
    width = field_map("format.block_width")


class BookmarkBlock(MediaBlock):

    bookmark_cover = field_map("format.bookmark_cover")
    bookmark_icon = field_map("format.bookmark_icon")
    description = property_map("description")
    link = property_map("link")
    title = property_map("title")


BLOCK_TYPES = {
    "": Block,
    "text": BasicBlock,
    "header": BasicBlock,
    "sub_header": BasicBlock,
    "page": BasicBlock,
    "to_do": TodoBlock,
    "bulleted_list": BasicBlock,
    "numbered_list": BasicBlock,
    "toggle": BasicBlock,
    "code": CodeBlock,
    "quote": BasicBlock,
    "image": ImageBlock,
    "embed": EmbedBlock,
    "bookmark": BookmarkBlock,
}
