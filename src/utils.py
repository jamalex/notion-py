import uuid

from settings import BASE_URL


def extract_id(url_or_id):
    """
    Extract the block/page ID from a Notion.so URL -- if it's a bare page URL, it will be the
    ID of the page. If there's a hash with a block ID in it (from clicking "Copy Link") on a
    block in a page), it will instead be the ID of that block. If it's already in ID format,
    it will be passed right through.
    """
    if url_or_id.startswith("http"):
        assert url_or_id.startswith(BASE_URL)
        url_or_id = url_or_id.split("#")[-1].split("/")[-1].split("?")[0].split("-")[-1]
    return str(uuid.UUID(url_or_id))
