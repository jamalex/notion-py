from notion.block import *


def assert_block_is_okay(notion, block, type, parent=None, **kwargs):
    parent = parent or notion.root_page

    assert block.id
    assert block.type == type
    assert block.alive is True
    assert block.is_alias is False
    assert block.parent == parent


def assert_block_attributes(block, **kwargs):
    for attr, value in kwargs.items():
        assert not getattr(block, attr)
        setattr(block, attr, value)

    block.refresh()

    for attr, value in kwargs.items():
        assert getattr(block, attr) == value


def test_block(notion):
    # create basic block from existing page
    block = Block(notion.client, notion.root_page.id)
    parent = notion.root_page.parent
    assert_block_is_okay(**locals(), type="page")

    assert len(block.children) == 0
    assert len(block.parent.id) == 36
    assert block.id == notion.root_page.id


def test_bookmark_block(notion):
    block = notion.root_page.children.add_new(BookmarkBlock)
    assert_block_is_okay(**locals(), type="bookmark")

    assert block.link == ""
    assert block.title == ""
    assert block.source == ""
    assert block.description == ""
    assert block.bookmark_icon is None
    assert block.bookmark_cover is None

    link = "github.com/arturtamborski/notion-py/"
    block.set_new_link(link)
    block.refresh()

    assert block.link == link
    assert block.title == "arturtamborski/notion-py"
    assert "This is a fork of the" in block.description
    assert "https://" in block.bookmark_icon
    assert "https://" in block.bookmark_cover

    block.set_source_url(link)
    block.refresh()

    assert block.source == link
    assert block.display_source == link


def test_breadcrumb_block(notion):
    block = notion.root_page.children.add_new(BreadcrumbBlock)
    assert_block_is_okay(**locals(), type="breadcrumb")


def test_bulleted_list_block(notion):
    block = notion.root_page.children.add_new(BulletedListBlock)
    assert_block_is_okay(**locals(), type="bulleted_list")
    assert_block_attributes(block, title="bulleted_list")


def test_callout_block(notion):
    block = notion.root_page.children.add_new(CalloutBlock)
    assert_block_is_okay(**locals(), type="callout")
    assert_block_attributes(block, icon="✔️", color="blue", title="callout")


def test_code_block(notion):
    block = notion.root_page.children.add_new(CodeBlock)
    assert_block_is_okay(**locals(), type="code")
    assert_block_attributes(block, color="blue", language="Erlang", title="code")


def test_codepen_block(notion):
    block = notion.root_page.children.add_new(CodepenBlock)
    assert_block_is_okay(**locals(), type="codepen")
    source = "https://codepen.io/MrWeb123/pen/QWyeQwp"
    assert_block_attributes(block, source=source, caption="caption")


def test_collection_view_block(notion):
    block = notion.root_page.children.add_new(CollectionViewBlock)
    assert_block_is_okay(**locals(), type="collection_view")


def test_collection_view_page_block(notion):
    block = notion.root_page.children.add_new(CollectionViewPageBlock)
    assert_block_is_okay(**locals(), type="collection_view_page")
    assert_block_attributes(block, icon="✔️", cover="cover")


def test_column_block(notion):
    block = notion.root_page.children.add_new(ColumnBlock)
    assert_block_is_okay(**locals(), type="column")

    assert block.column_ratio is None
    assert len(block.children) == 0

    block.column_ratio = 1 / 2
    block.refresh()

    assert block.column_ratio == 1 / 2


def test_column_list_block(notion):
    block = notion.root_page.children.add_new(ColumnListBlock)
    assert_block_is_okay(**locals(), type="column_list")

    assert len(block.children) == 0

    block.children.add_new(ColumnBlock)
    block.children.add_new(ColumnBlock)
    block.evenly_space_columns()
    block.refresh()

    assert len(block.children) == 2
    assert block.children[0].column_ratio == 1 / 2


def test_divider_block(notion):
    block = notion.root_page.children.add_new(DividerBlock)
    assert_block_is_okay(**locals(), type="divider")


def test_drive_block(notion):
    block = notion.root_page.children.add_new(DriveBlock)
    assert_block_is_okay(**locals(), type="drive")
    source = "https://drive.google.com/file/"
    source = source + "d/15kESeWR9wCWT7GW9VvChakTGin68iZsw/view"
    assert_block_attributes(block, source=source, caption="drive")


def test_embed_block(notion):
    block = notion.root_page.children.add_new(EmbedBlock)
    assert_block_is_okay(**locals(), type="embed")

    assert block.source == ""
    assert block.caption == ""

    caption = "block embed caption"
    block.upload_file("requirements.txt")
    block.caption = caption
    block.refresh()

    assert "secure.notion-static.com" in block.source
    assert block.caption == caption


def test_embed_or_upload_block(notion):
    block = notion.root_page.children.add_new(EmbedOrUploadBlock)
    assert_block_is_okay(**locals(), type="embed")


def test_equation_block(notion):
    block = notion.root_page.children.add_new(EquationBlock)
    assert_block_is_okay(**locals(), type="equation")
    assert_block_attributes(block, title="E=mc^{2}", color="blue")


def test_factory_block(notion):
    block = notion.root_page.children.add_new(FactoryBlock)
    assert_block_is_okay(**locals(), type="factory")
    assert_block_attributes(block, title="factory", color="blue")


def test_figma_block(notion):
    block = notion.root_page.children.add_new(FigmaBlock)
    assert_block_is_okay(**locals(), type="figma")


def test_file_block(notion):
    block = notion.root_page.children.add_new(FileBlock)
    assert_block_is_okay(**locals(), type="file")

    assert block.title == ""
    assert block.source == ""
    assert block.file_id is None

    title = "requirements.txt"
    block.upload_file(title)
    block.title = title
    block.refresh()

    assert block.title == title
    assert "secure.notion-static.com" in block.source
    assert len(block.file_id) == 36


def test_framer_block(notion):
    block = notion.root_page.children.add_new(FramerBlock)
    assert_block_is_okay(**locals(), type="framer")


def test_gist_block(notion):
    block = notion.root_page.children.add_new(GistBlock)
    assert_block_is_okay(**locals(), type="gist")
    source = "https://gist.github.com/arturtamborski/"
    source = source + "539a335fcd71f88bb8c05f316f54ba31"
    assert_block_attributes(block, source=source, caption="caption")


def test_header_block(notion):
    block = notion.root_page.children.add_new(HeaderBlock)
    assert_block_is_okay(**locals(), type="header")
    assert_block_attributes(block, title="header", color="blue")


def test_image_block(notion):
    block = notion.root_page.children.add_new(ImageBlock)
    assert_block_is_okay(**locals(), type="image")
    source = "https://raw.githubusercontent.com/jamalex/"
    source = source + "notion-py/master/ezgif-3-a935fdcb7415.gif"
    assert_block_attributes(block, source=source, caption="caption")


def test_invision_block(notion):
    block = notion.root_page.children.add_new(InvisionBlock)
    assert_block_is_okay(**locals(), type="invision")


def test_link_to_collection_block(notion):
    block = notion.root_page.children.add_new(LinkToCollectionBlock)
    assert_block_is_okay(**locals(), type="link_to_collection")


def test_loom_block(notion):
    block = notion.root_page.children.add_new(LoomBlock)
    assert_block_is_okay(**locals(), type="loom")


def test_maps_block(notion):
    block = notion.root_page.children.add_new(MapsBlock)
    assert_block_is_okay(**locals(), type="maps")
    source = "https://goo.gl/maps/MrLSwJ3YqdkqekuGA"
    assert_block_attributes(block, source=source, caption="caption")


def test_media_block(notion):
    pass
    # TODO: fix
    # block = notion.root_page.children.add_new(MediaBlock)
    # assert_block_is_okay(**locals(), type='media')


def test_numbered_list_block(notion):
    block = notion.root_page.children.add_new(NumberedListBlock)
    assert_block_is_okay(**locals(), type="numbered_list")
    assert_block_attributes(block, title="numbered_list")


def test_pdf_block(notion):
    block = notion.root_page.children.add_new(PDFBlock)
    assert_block_is_okay(**locals(), type="pdf")


def test_page_block(notion):
    block = notion.root_page.children.add_new(PageBlock)
    assert_block_is_okay(**locals(), type="page")
    cover = "/images/page-cover/woodcuts_3.jpg"
    assert_block_attributes(
        block, title="numbered_list", cover=cover, color="blue", icon="✔️"
    )


def test_quote_block(notion):
    block = notion.root_page.children.add_new(QuoteBlock)
    assert_block_is_okay(**locals(), type="quote")
    assert_block_attributes(block, title="quote", color="blue")


def test_subheader_block(notion):
    block = notion.root_page.children.add_new(SubheaderBlock)
    assert_block_is_okay(**locals(), type="sub_header")
    assert_block_attributes(block, title="subheader", color="blue")


def test_subsubheader_block(notion):
    block = notion.root_page.children.add_new(SubsubheaderBlock)
    assert_block_is_okay(**locals(), type="sub_sub_header")
    assert_block_attributes(block, title="subsubheader", color="blue")


def test_text_block(notion):
    block = notion.root_page.children.add_new(TextBlock)
    assert_block_is_okay(**locals(), type="text")
    assert_block_attributes(block, title="text", color="blue")


def test_todo_block(notion):
    block = notion.root_page.children.add_new(TodoBlock)
    assert_block_is_okay(**locals(), type="to_do")
    assert_block_attributes(block, title="text", color="blue", checked=True)


def test_toggle_block(notion):
    block = notion.root_page.children.add_new(ToggleBlock)
    assert_block_is_okay(**locals(), type="toggle")
    assert_block_attributes(block, title="text", color="blue")


def test_tweet_block(notion):
    block = notion.root_page.children.add_new(TweetBlock)
    assert_block_is_okay(**locals(), type="tweet")
    source = "https://twitter.com/arturtamborski/status/1289293818609704961"
    assert_block_attributes(block, source=source, caption="caption")


def test_typeform_block(notion):
    block = notion.root_page.children.add_new(TypeformBlock)
    assert_block_is_okay(**locals(), type="typeform")
    source = "https://linklocal.typeform.com/to/I3lVBn"
    assert_block_attributes(block, source=source, caption="caption")


def test_video_block(notion):
    block = notion.root_page.children.add_new(VideoBlock)
    assert_block_is_okay(**locals(), type="video")
    source = "https://streamable.com/8ud2kh"
    assert_block_attributes(block, source=source, caption="caption")
