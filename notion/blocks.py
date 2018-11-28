from utils import extract_id, now
from maps import property_map, field_map, joint_map
from operations import build_operation
import random
import uuid


class Children(object):

    def __init__(self, parent):
        self._parent = parent
        self._client = parent._client

    def shuffle(self):
        content = self._content_list()
        random.shuffle(content)
        self._parent.set("content", content)

    def _content_list(self):
        return self._parent.get("content") or []

    def __repr__(self):
        rep = "[\n"
        for child in self:
            rep += "  {},\n".format(repr(child))
        rep += "]"
        return rep

    def __len__(self):
        return len(self._content_list() or [])

    def __getitem__(self, key):
        result = self._content_list()[key]
        if isinstance(result, list):
            return [self._client.get_block(id) for id in result]
        else:
            return [self._client.get_block(result)]

    def __delitem__(self, key):
        self._client.get_block(self._content_list()[key]).remove()

    def __iter__(self):
        return iter(self._client.get_block(id) for id in self._content_list())

    def __reversed__(self):
        return reversed(self.__iter__())

    def __contains__(self, item):
        if isinstance(item, str):
            item_id = extract_id(item)
        elif isinstance(item, Block):
            item_id = item.id
        else:
            return False
        return item_id in self._content_list()

    def add(self, block_type):
        """
        Create a new block, add it as the last child of this parent block, and return the corresponding Block instance.
        `block_type` can be either a type string, or a Block subclass.
        """

        # determine the block type string from the Block class, if that's what was provided
        if isinstance(block_type, type) and issubclass(block_type, Block) and hasattr(block_type, "_type"):
            block_type = block_type._type
        elif not isinstance(block_type, str):
            raise Exception("block_type must be a string or a Block subclass with a _type attribute")

        # make up a new UUID; apparently we get to choose our own!
        block_id = str(uuid.uuid4())

        with self._client.as_atomic_transaction():

            # create the new block
            self._client.submit_transaction(
                build_operation(
                    args={
                        "id": block_id,
                        "type": block_type,
                        "version": 1,
                        "alive": True,
                        "created_by": self._client.user_id,
                        "created_time": now(),
                        "parent_id": self._parent.id,
                        "parent_table": "block",
                    },
                    command="set",
                    id=block_id,
                    path=[],
                )
            )

            # add the block to the content list of the parent
            self._client.submit_transaction(
                build_operation(
                    id=self._parent.id,
                    path=["content"],
                    args={"id": block_id},
                    command="listAfter",
                )
            )

        return self._client.get_block(block_id)


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
        self._client = client
        self._block_id = extract_id(block_id)

    @property
    def id(self):
        return self._block_id

    @property
    def children(self):
        if not hasattr(self, "_children"):
            children_ids = self.get("content", [])
            self._client.bulk_update_block_cache(children_ids)
            self._children = Children(parent=self)
        return self._children

    @property
    def parent(self):
        parent_id = self.get("parent_id")
        parent_table = self.get("parent_table")
        if not parent_id or parent_table != "block":
            return None
        if not hasattr(self, "_parent"):
            self._parent = self._client.get_block(parent_id)
        return self._parent

    def __str__(self):
        return "type={}".format(self.type)

    def __repr__(self):
        return "<{} ({})>".format(self.__class__.__name__, self)

    def refresh(self):
        """
        Update the cached data for this block from the server (data for other blocks may be updated as a side effect).
        """
        self._client.update_block_cache(self.id)

    def _get_block_data(self):
        if self.id not in self._client.block_cache:
            self.refresh()
        return self._client.block_cache[self.id]

    def get(self, path=[], default=None, refresh=False):
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
            value = default
        return value

    def set(self, path, value, refresh=True):
        """
        Set a specific `value` (under the specific `path`) on the block's data structure on the server.
        If `refresh` is set to True, we refresh the data cache from the server after sending the update.
        """
        self._client.submit_transaction(build_operation(id=self.id, path=path, args=value))
        if refresh:
            self.refresh()

    def remove(self):
        """
        Removes the node from its parent, and marks it as inactive. This corresponds to what happens in the
        Notion UI when you delete a block. Note that it doesn't seem to *actually* delete it, just orphan it.
        """

        with self._client.as_atomic_transaction():
            # Mark the block as inactive
            self._client.submit_transaction(
                build_operation(
                    id=self.id,
                    path=[],
                    args={"alive": False},
                    command="update",
                )
            )
            # Remove the block's ID from the "content" list of its parent
            self._client.submit_transaction(
                build_operation(
                    id=self.get("parent_id"),
                    path=["content"],
                    args={"id": self.id},
                    command="listRemove",
                )
            )

    def move_to(self, target_block, position="last-child"):
        assert isinstance(target_block, Block), "target_block must be an instance of Block or one of its subclasses"
        assert position in ["first-child", "last-child", "before", "after"]

        if "child" in position:
            new_parent_id = target_block.id
            new_parent_table = "block"
        else:
            new_parent_id = target_block.get("parent_id")
            new_parent_table = target_block.get("parent_table")

        if position in ["first-child", "before"]:
            list_command = "listBefore"
        else:
            list_command = "listAfter"

        list_args = {"id": self.id}
        if position in ["before", "after"]:
            list_args[position] = target_block.id

        with self._client.as_atomic_transaction():

            # First, remove the node, before we re-insert and re-activate it at the target location
            self.remove()

            # Set the parent_id of the moving block to the new parent, and mark it as active again
            self._client.submit_transaction(
                build_operation(
                    id=self.id,
                    path=[],
                    args={"alive": True, "parent_id": new_parent_id, "parent_table": new_parent_table},
                    command="update",
                )
            )
            # Add the moving block's ID to the "content" list of the new parent
            self._client.submit_transaction(
                build_operation(
                    id=new_parent_id,
                    path=["content"],
                    args=list_args,
                    command=list_command,
                )
            )
            # update the local block cache to reflect the updates
            self._client.bulk_update_block_cache(block_ids=[self.id, self.get("parent_id"), target_block.id, target_block.get("parent_id")])


class BasicBlock(Block):

    title = property_map("title")
    color = field_map("format.block_color")

    def convert_to_type(self, new_type):
        """
        Convert this block into another type of BasicBlock. Returns a new instance of the appropriate class.
        """
        assert new_type in BLOCK_TYPES and issubclass(BLOCK_TYPES[new_type], BasicBlock), \
            "Target type must correspond to a subclass of BasicBlock"
        self.type = new_type
        return self._client.get_block(self.id)

    def __str__(self):
        return "id={}, title={}".format(self.id, repr(self.title))


class TodoBlock(BasicBlock):

    _type = "to_do"

    checked = property_map("checked", python_to_api=lambda x: "Yes" if x else "No", api_to_python=lambda x: x == "Yes")


class CodeBlock(BasicBlock):

    _type = "code"

    language = property_map("language")
    wrap = field_map("format.code_wrap")


class MediaBlock(Block):

    caption = property_map("caption")

    def __str__(self):
        return "id={}, caption={}".format(self.id, repr(self.caption))


class ImageBlock(MediaBlock):

    _type = "image"

    width = field_map("format.block_width")


class EmbedBlock(MediaBlock):

    _type = "embed"

    source = joint_map(field_map("format.display_source"), property_map("source"))
    height = field_map("format.block_height")
    full_width = field_map("format.block_full_width")
    page_width = field_map("format.block_page_width")
    width = field_map("format.block_width")


class BookmarkBlock(MediaBlock):

    _type = "bookmark"

    bookmark_cover = field_map("format.bookmark_cover")
    bookmark_icon = field_map("format.bookmark_icon")
    description = property_map("description")
    link = property_map("link")
    title = property_map("title")


class HeaderBlock(BasicBlock):

    _type = "header"
    # TODO: add custom fields


class SubheaderBlock(BasicBlock):

    _type = "sub_header"
    # TODO: add custom fields


class PageBlock(BasicBlock):

    _type = "page"
    # TODO: add custom fields


class BulletedListBlock(BasicBlock):

    _type = "bulleted_list"
    # TODO: add custom fields


class NumberedListBlock(BasicBlock):

    _type = "numbered_list"
    # TODO: add custom fields


class ToggleBlock(BasicBlock):

    _type = "toggle"
    # TODO: add custom fields


class QuoteBlock(BasicBlock):

    _type = "quote"
    # TODO: add custom fields


class TextBlock(BasicBlock):

    _type = "text"
    # TODO: add custom fields


BLOCK_TYPES = {cls._type: cls for cls in locals().values() if type(cls) == type and issubclass(cls, Block) and hasattr(cls, "_type")}
