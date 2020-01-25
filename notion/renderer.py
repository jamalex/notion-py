import mistletoe
from mistletoe import block_token, span_token
from mistletoe.html_renderer import HTMLRenderer as MistletoeHTMLRenderer
import requests
import dominate
from dominate.tags import *
from dominate.util import raw
from more_itertools import flatten

from .block import *
from .collection import Collection

#This is the minimal css stylesheet to apply to get
#decent lookint output, it won't make it look exactly like Notion.so
#but will have the same basic structure
HTMLRendererStyles = """
<style>
html, body {
	padding: 20px;
	margin: 20px auto;
	width: 900px;
	font-size: 16px;
	font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif, "Segoe UI Emoji", "Segoe UI Symbol";
}
.children-list {
	margin-left: cRems(20px);
}
.column-list {
	display: flex;
	align-items: center;
	justify-content: center;
}
.callout {
	display: flex;
}
.callout > .icon {
	flex: 0 1 40px;
}
.callout > .text {
	flex: 1 1 auto;
}
</style>
"""

class MistletoeHTMLRendererSpanTokens(MistletoeHTMLRenderer):
    """
    Renders Markdown to HTML without any MD block tokens (like blockquote or code)
    except for the paragraph block token, because you need at least one
    """

    def __enter__(self):
        ret = super().__enter__()
        for tokenClsName in block_token.__all__[:-1]: #All but Paragraph token
            block_token.remove_token(getattr(block_token, tokenClsName))
        span_token.remove_token(span_token.AutoLink) #don't autolink urls in markdown
        return ret
    # Auto resets tokens in __exit__, so no need to readd the tokens anywhere

    def render_paragraph(self, token):
        """
        Only used for span tokens, so don't render out anything
        """
        return self.render_inner(token)

class BaseRenderer(object):

	def __init__(self, start_block):
		self.start_block = start_block

	def render(self):
		pass

	def render_block(self, block):
		pass

def renderMD(mdStr):
	"""
	Render the markdown string to HTML, wrapped with dominate "raw" so Dominate
	renders it straight to HTML.
	"""
	#[:-1] because it adds a newline for some reason
	#TODO: Follow up on this and make it more robust
	#https://github.com/miyuchina/mistletoe/blob/master/mistletoe/block_token.py#L138-L152
	return raw(mistletoe.markdown(mdStr, MistletoeHTMLRendererSpanTokens)[:-1])

def href_for_block(block):
	"""
	Gets the href for a given block
	"""
	return f'https://www.notion.so/{block.id.replace("-", "")}'

def handles_children_rendering(func):
	setattr(func, 'handles_children_rendering', True)
	return func

class BaseHTMLRenderer(BaseRenderer):
	"""
	BaseRenderer for HTML output, uses [Dominate](https://github.com/Knio/dominate)
	internally for generating HTML output
	Each token rendering method should create a dominate tag and it automatically
	gets added to the parent context (because of the with statement). If you return
	a given tag, it will be used as the parent container for all rendered children
	"""

	def __init__(self, start_block, render_linked_pages=False, render_sub_pages=True,
		render_table_pages_after_table=False, with_styles=False):
		"""
		start_block The root block to render from
		follow_links Whether to follow "Links to pages"
		"""
		self.exclude_ids = [] #TODO: Add option for this
		self.start_block = start_block
		self.render_linked_pages = render_linked_pages
		self.render_sub_pages = render_sub_pages
		self.render_table_pages_after_table = render_table_pages_after_table
		self.with_styles = with_styles

		self._render_stack = []

	def render(self, **kwargs):
		"""
		Renders the HTML, kwargs takes kwargs for Dominate's render() function
		https://github.com/Knio/dominate#rendering

		These can be:
		`pretty` - Whether or not to be pretty
		`indent` - Indent character to use
		`xhtml` - Whether or not to use XHTML instead of HTML (<br /> instead of <br>)
		"""
		els = self.render_block(self.start_block)
		return (HTMLRendererStyles if self.with_styles else "") + \
			"".join(el.render(**kwargs) for el in els)

	def get_parent_el(self):
		"""
		Gets the current parent off the render stack
		"""
		if not self._render_stack:
			return None
		return self._render_stack[-1]

	def get_previous_sibling_el(self):
		"""
		Gets the previous sibling element in the rendered HTML tree
		"""
		parentEl = self.get_parent_el()
		if not parentEl or not parentEl.children:
			return None #No parent or no siblings
		return parentEl.children[-1]

	def render_block(self, block):
		if block.id in self.exclude_ids:
			return [] #don't render this block

		assert isinstance(block, Block)
		type_renderer = getattr(self, "render_" + block._type, None)
		if not callable(type_renderer):
			if hasattr(self, "render_default"):
				type_renderer = self.render_default
			else:
				raise Exception("No handler for block type '{}'.".format(block._type))
		class_function = getattr(self.__class__, type_renderer.__name__)

		#Render ourselves to a Dominate HTML element
		els = type_renderer(block) #Returns a list of elements

		#If the block has no children, or the called function handles the child
		#rendering itself, don't render the children
		if not block.children or hasattr(class_function, 'handles_children_rendering'):
			return els

		#Otherwise, render and use the default append as a children-list
		return els + self.render_blocks_into(block.children, None)

	def render_blocks_into(self, blocks, containerEl=None):
		if containerEl is None: #Default behavior is to add a container for the children
			containerEl = div(_class='children-list')
		self._render_stack.append(containerEl)
		for block in blocks:
			els = self.render_block(block)
			containerEl.add(els)
		self._render_stack.pop()
		return [containerEl]

	# == Conversions for rendering notion-py block types to elemenets ==
	# Each function should return a list containing dominate tags
	# Marking a function with handles_children_rendering means it handles rendering
	# it's own `.children` and doesn't need to perform the default rendering

	def render_default(self, block):
		return [p(renderMD(block.title))]

	def render_divider(self, block):
		return [hr()]

	@handles_children_rendering
	def render_column_list(self, block):
		return self.render_blocks_into(block.children, div(style='display: flex;', _class='column-list'))

	@handles_children_rendering
	def render_column(self, block):
		return self.render_blocks_into(block.children, div(_class='column'))

	def render_to_do(self, block):
		id = f'chk_{block.id}'
		return [input( \
				label(_for=id), \
			type='checkbox', id=id, checked=block.checked, title=block.title)]

	def render_code(self, block):
		#TODO: Do we want this to support Markdown? I think there's a notion-py
		#change that might affect this... (the unstyled-title or whatever)
		return [pre(code(block.title))]

	def render_factory(self, block):
		return []

	def render_header(self, block):
		return [h2(renderMD(block.title))]

	def render_sub_header(self, block):
		return [h3(renderMD(block.title))]

	def render_sub_sub_header(self, block):
		return [h4(renderMD(block.title))]

	@handles_children_rendering
	def render_page(self, block):
		#TODO: I would use isinstance(xxx, CollectionRowBlock) here but it's buggy
		#https://github.com/jamalex/notion-py/issues/103
		if isinstance(block.parent, Collection): #If it's a child of a collection (CollectionRowBlock)
			if not self.render_table_pages_after_table:
				return []
			return [h3(renderMD(block.title))] + self.render_blocks_into(block.children)
		elif block.parent.id != block.get()['parent_id']:
			#A link is a PageBlock where the parent id doesn't equal the _actual_ parent id
			#of the block
			if not self.render_linked_pages:
				#Render only the link, none of the content in the link
				return [a(h4(renderMD(block.title)), href=href_for_block(block))]
		else: #A normal PageBlock
			if not self.render_sub_pages and self._render_stack:
				return [h4(renderMD(block.title))] #Subpages when not rendering them render like in Notion, as a simple heading

		#Otherwise, render a page normally in it's entirety
		#TODO: This should probably not use a "children-list" but we need to refactor
		#the _render_stack to make that work...
		return [h1(renderMD(block.title))] + self.render_blocks_into(block.children)

	@handles_children_rendering
	def render_bulleted_list(self, block):
		previousSibling = self.get_previous_sibling_el()
		previousSiblingIsUl = previousSibling and isinstance(previousSibling, ul)
		containerEl = previousSibling if previousSiblingIsUl else ul() #Make a new ul if there's no previous ul

		blockEl = li(renderMD(block.title))
		containerEl.add(blockEl) #Render out ourself into the stack
		self.render_blocks_into(block.children, containerEl)
		return [] if containerEl.parent else [containerEl] #Only return if it's not in the rendered output yet

	@handles_children_rendering
	def render_numbered_list(self, block):
		previousSibling = self.get_previous_sibling_el()
		previousSiblingIsOl = previousSibling and isinstance(previousSibling, ol)
		containerEl = previousSibling if previousSiblingIsOl else ol() #Make a new ol if there's no previous ol

		blockEl = li(renderMD(block.title))
		containerEl.add(blockEl) #Render out ourself into the stack
		self.render_blocks_into(block.children, containerEl)
		return [] if containerEl.parent else [containerEl] #Only return if it's not in the rendered output yet

	def render_toggle(self, block):
		return [details(summary(renderMD(block.title)))]

	def render_quote(self, block):
		return [blockquote(renderMD(block.title))]

	render_text = render_default

	def render_equation(self, block):
		return [p(img(src=f'https://chart.googleapis.com/chart?cht=tx&chl={block.latex}'))]

	def render_embed(self, block):
		return [iframe(src=block.display_source or block.source, frameborder=0,
			sandbox='allow-scripts allow-popups allow-forms allow-same-origin',
			allowfullscreen='')]

	def render_video(self, block):
		#TODO, this won't work if there's no file extension, we might have
		#to query and get the MIME type...
		src = block.display_source or block.source
		srcType = src.split('.')[-1]
		return [video(source(src=src, type=f"video/{srcType}"), controls=True)]

	render_file = render_embed
	render_pdf = render_embed

	def render_audio(self, block):
		return [audio(src=block.display_source or block.source, controls=True)]

	def render_image(self, block):
		attrs = {}
		if block.caption: # Add the alt attribute if there's a caption
			attrs['alt'] = block.caption
		return [img(src=block.display_source or block.source, **attrs)]

	def render_bookmark(self, block):
		#return bookmark_template.format(link=, title=block.title, description=block.description, icon=block.bookmark_icon, cover=block.bookmark_cover)
		#TODO: It's just a social share card for the website we're bookmarking
		return [a(href="block.link")]

	def render_link_to_collection(self, block):
		return [a(renderMD(block.title), href=href_for_block(block))]

	def render_breadcrumb(self, block):
		return [p(renderMD(block.title))]

	def render_collection_view_page(self, block):
		print("TEST")
		return [a(renderMD(block.title), href=href_for_block(block))]

	render_framer = render_embed

	def render_tweet(self, block):
		#TODO: Convert to a list or something
		return requests.get("https://publish.twitter.com/oembed?url=" + block.source).json()["html"]

	render_gist = render_embed
	render_drive = render_embed
	render_figma = render_embed
	render_loom = render_embed
	render_typeform = render_embed
	render_codepen = render_embed
	render_maps = render_embed
	render_invision = render_embed

	def render_callout(self, block):
		return [div( \
			div(block.icon, _class="icon") + div(renderMD(block.title), _class="text"), \
		_class="callout")]

	def render_collection_view(self, block):
		#Render out the table itself
		#TODO

		#Render out all the embedded PageBlocks
		if not self.render_table_pages_after_table:
			return [] #Don't render out any of the internal pages

		return [h2(block.title)] + self.render_blocks_into(block.collection.get_rows())