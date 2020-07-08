"""
Tests for notion-py renderer
"""

import uuid
from functools import partial
from unittest.mock import Mock, PropertyMock

from notion.renderer import BaseHTMLRenderer
from notion.block import (
    TextBlock,
    BulletedListBlock,
    PageBlock,
    NumberedListBlock,
    ImageBlock,
    ColumnBlock,
    ColumnListBlock,
)


def MockSpace(pages=[]):
    # TODO: Doesn't operate at all like *Block types...
    spaceMock = Mock()
    spaceMock.pages = pages
    spaceMock.id = uuid.uuid4()
    for page in pages:
        type(page).parent = PropertyMock(return_value=spaceMock)
    return spaceMock


testSpace = MockSpace()


def BlockMock(blockType, inputDict, children=[]):
    global testSpace

    blockMock = Mock(spec=blockType)
    blockMock._type = blockType._type
    blockMock.__dict__.update(inputDict)
    blockMock.id = uuid.uuid4()
    blockMock.get = Mock(return_value={})
    blockMock.children = children
    if issubclass(blockType, PageBlock):
        # PageBlocks always need a parent, might be overwritten later
        type(blockMock).parent = PropertyMock(return_value=testSpace)
        blockMock.get = Mock(return_value={"parent_id": testSpace.id})

    # Setup children references if passed
    for child in children:
        # Can't set a mock on a property of a mock in a circular relationship
        # or it messes up so use PropertyMock
        type(child).parent = PropertyMock(return_value=blockMock)
        child.get = Mock(return_value={"parent_id": blockMock.id})
    return blockMock


for blockCls in [
    TextBlock,
    BulletedListBlock,
    PageBlock,
    NumberedListBlock,
    ImageBlock,
    ColumnBlock,
    ColumnListBlock,
]:
    globals()["Mock" + blockCls.__name__] = partial(BlockMock, blockCls)


def test_TextBlock():
    """it renders a TextBlock"""
    # arrange
    block = MockTextBlock({"title": "Hold up, lemme test this block..."})

    # act
    output = BaseHTMLRenderer(block).render(pretty=False)

    # assert
    assert output == "<p>Hold up, lemme test this block...</p>"


def test_BulletedListBlock():
    """it renders BulletedListBlocks"""
    # arrange
    block = MockPageBlock(
        {"title": "Test Page"},
        [
            MockBulletedListBlock({"title": ":3"}),
            MockBulletedListBlock({"title": ":F"}),
            MockBulletedListBlock({"title": ">:D"}),
        ],
    )

    # act
    output = BaseHTMLRenderer(block).render(pretty=False)

    # assert
    assert (
        output
        == '<h1>Test Page</h1><div class="children-list"><ul><li>:3</li><li>:F</li><li>&gt;:D</li></ul></div>'
    )


def test_BulletedListBlockNested():
    """it renders BulletedListBlocks"""
    # arrange
    block = MockPageBlock(
        {"title": "Test Page"},
        [
            MockBulletedListBlock(
                {"title": "owo"}, [MockBulletedListBlock({"title": "OwO"})]
            )
        ],
    )

    # act
    output = BaseHTMLRenderer(block).render(pretty=False)

    # assert
    assert (
        output
        == '<h1>Test Page</h1><div class="children-list"><ul><li>owo</li><ul><li>OwO</li></ul></ul></div>'
    )


def test_NumberedListBlock():
    """it renders NumberedListBlocks"""
    # arrange
    block = MockPageBlock(
        {"title": "Test Page"},
        [
            MockNumberedListBlock({"title": ":3"}),
            MockNumberedListBlock({"title": ":F"}),
            MockNumberedListBlock({"title": ">:D"}),
        ],
    )

    # act
    output = BaseHTMLRenderer(block).render(pretty=False)

    # assert
    assert (
        output
        == '<h1>Test Page</h1><div class="children-list"><ol><li>:3</li><li>:F</li><li>&gt;:D</li></ol></div>'
    )


def test_ImageBlock():
    """it renders an ImageBlock"""
    # arrange
    block = MockImageBlock(
        {
            "caption": "Its a me! Placeholderio",
            "display_source": "https://via.placeholder.com/20x20",
            "source": "https://via.placeholder.com/20x20",
        }
    )

    # act
    output = BaseHTMLRenderer(block).render(pretty=False)

    # assert
    assert (
        output
        == '<img alt="Its a me! Placeholderio" src="https://via.placeholder.com/20x20">'
    )


def test_ColumnList():
    """it renders a ColumnList"""
    # arrange
    block = MockColumnListBlock(
        {},
        [
            MockColumnBlock({}, [MockTextBlock({"title": "Whats wrong Jimmykun?"})]),
            MockColumnBlock(
                {},
                [
                    MockTextBlock({"title": "Could it be that youre"}),
                    MockTextBlock({"title": "craving my, c r o i s s a n t?"}),
                ],
            ),
        ],
    )

    # act
    output = BaseHTMLRenderer(block).render(pretty=False)

    # assert
    assert (
        output
        == '<div class="column-list" style="display: flex;">'
        + '<div class="column"><p>Whats wrong Jimmykun?</p></div>'
        + '<div class="column"><p>Could it be that youre</p><p>craving my, c r o i s s a n t?</p></div>'
        "</div>"
    )
