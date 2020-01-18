import mistletoe
from mistletoe import block_token
from mistletoe.html_renderer import HTMLRenderer
import requests
import dominate
import threading
from dominate.tags import *
from dominate.util import raw

from .block import *


class MistletoeHTMLRendererSpanTokens(HTMLRenderer):
    """
    Renders Markdown to HTML without any MD block tokens (like blockquote or code)
    except for the paragraph block token, because you need at least one
    """

    def __enter__(self):
        ret = super().__enter__()
        for tokenClsName in block_token.__all__[:-1]: #All but Paragraph token
            block_token.remove_token(getattr(block_token, tokenClsName))
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

class BaseHTMLRenderer(BaseRenderer):
	"""
	BaseRenderer for HTML output, uses [Dominate](https://github.com/Knio/dominate)
	internally for generating HTML output
	Each token rendering method should create a dominate tag and it automatically
	gets added to the parent context (because of the with statement). If you return
	a given tag, it will be used as the parent container for all rendered children
	"""

	def __init__(self, start_block):
		self._render_stack = []
		self.start_block = start_block

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
		return "".join(el.render(**kwargs) for el in els)

	def get_previous_sibling_el(self):
		"""
		Gets the previous sibling element in the rendered HTML tree
		"""
		current_parent = self._render_stack[-1]
		if not current_parent.children:
			return None #No children
		return current_parent.children[-1]

	def render_block(self, block):
		assert isinstance(block, Block)
		type_renderer = getattr(self, "render_" + block._type, None)
		if not callable(type_renderer):
			if hasattr(self, "render_default"):
				type_renderer = self.render_default
			else:
				raise Exception("No handler for block type '{}'.".format(block._type))
		#Render ourselves to a Dominate HTML element
		selfEl = type_renderer(block)
		if not block.children:
			#No children, return early
			return [selfEl]

		#If children, render them inside of us or inside a container
		selfIsContainerEl = 'data_is_container' in selfEl
		containerEl = selfEl if selfIsContainerEl else div(_class='children-list')
		retList = [selfEl]
		if not selfIsContainerEl:
			retList.append(containerEl)
		self._render_stack.append(containerEl)
		for child in block.children:
			for childEl in self.render_block(child):
				if childEl: #Might return None if pass or if no extra element to add
					containerEl.add(childEl)
		self._render_stack.pop()
		return retList

	def render_default(self, block):
		return p(renderMD(block.title))

	def render_divider(self, block):
		return hr()

	def render_column_list(self, block):
		return div(style='display: flex;', _class='column-list', data_is_container='true')

	def render_column(self, block):
		return div(_class='column', data_is_container='true')

	def render_to_do(self, block):
		id = f'chk_{block.id}'
		return input(label(_for=id), type='checkbox', id=id, checked=block.checked, title=block.title)

	def render_code(self, block):
		#TODO: Do we want this to support Markdown? I think there's a notion-py
		#change that might affect this... (the unstyled-title or whatever)
		return pre(code(block.title))

	def render_factory(self, block):
		pass

	def render_header(self, block):
		return h2(renderMD(block.title))

	def render_sub_header(self, block):
		return h3(renderMD(block.title))

	def render_sub_sub_header(self, block):
		return h4(renderMD(block.title))

	def render_page(self, block):
		return h1(renderMD(block.title))

	def render_bulleted_list(self, block):
		previousSibling = self.get_previous_sibling_el()
		previousSiblingIsUl = previousSibling and isinstance(previousSibling, ul)
		#Open a new ul if the last child was not a ul
		with previousSibling if previousSiblingIsUl else ul() as ret:
			li(renderMD(block.title))
		return None if previousSiblingIsUl else ret

	def render_numbered_list(self, block):
		previousSibling = self.get_previous_sibling_el()
		previousSiblingIsOl = previousSibling and isinstance(previousSibling, ol)
		#Open a new ul if the last child was not a ol
		with previousSibling if previousSiblingIsOl else ol() as ret:
			li(renderMD(block.title))
		return None if previousSiblingIsOl else ret

	def render_toggle(self, block):
		return details(summary(renderMD(block.title)))

	def render_quote(self, block):
		return blockquote(renderMD(block.title))

	render_text = render_default

	def render_equation(self, block):
		return p(img(src=f'https://chart.googleapis.com/chart?cht=tx&chl={block.latex}'))

	def render_embed(self, block):
		return iframe(src=block.display_source or block.source, frameborder=0,
			sandbox='allow-scripts allow-popups allow-forms allow-same-origin',
			allowfullscreen='')

	def render_video(self, block):
		#TODO, this won't work if there's no file extension, we might have
		#to query and get the MIME type...
		src = block.display_source or block.source
		srcType = src.split('.')[-1]
		return video(source(src=src, type=f"video/{srcType}"), controls=True)

	render_file = render_embed
	render_pdf = render_embed

	def render_audio(self, block):
		return audio(src=block.display_source or block.source, controls=True)

	def render_image(self, block):
		attrs = {}
		if block.caption: # Add the alt attribute if there's a caption
			attrs['alt'] = block.caption
		return img(src=block.display_source or block.source, **attrs)

	def render_bookmark(self, block):
		#return bookmark_template.format(link=, title=block.title, description=block.description, icon=block.bookmark_icon, cover=block.bookmark_cover)
		#It's just a social share card for the website we're bookmarking
		return a(href="block.link")

	def render_link_to_collection(self, block):
		return a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def render_breadcrumb(self, block):
		return p(renderMD(block.title))

	def render_collection_view(self, block):
		return a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def render_collection_view_page(self, block):
		return a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	render_framer = render_embed

	def render_tweet(self, block):
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
		return div( \
			div(block.icon, _class="icon") + div(renderMD(block.title), _class="text"), \
		_class="callout")

#This is the minimal css stylesheet to apply to get
#decent lookint output, it won't make it look exactly like Notion.so
#but will have the same basic structure
"""
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
"""