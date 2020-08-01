import os
from dataclasses import dataclass

import pytest

from notion.block import BasicBlock
from notion.client import NotionClient


@dataclass
class NotionTestContext:
    client: NotionClient
    root_page: BasicBlock


@pytest.fixture
def notion(cache=[]):
    if cache:
        return cache[0]

    token_v2 = os.environ["NOTION_TOKEN_V2"]
    page_url = os.environ["NOTION_PAGE_URL"]

    client = NotionClient(token_v2=token_v2)
    page = client.get_block(page_url)

    # clean previous blocks
    for child in page.children:
        child.remove(permanently=True)

    page.refresh()

    cache.append(NotionTestContext(client, page))
    return cache[0]
