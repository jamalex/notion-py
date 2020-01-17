import markdown2
import requests
import dominate
import threading
from dominate.tags import *
from dominate.util import raw

from .block import *

class nullcontext:
	def __enter__(self):
		pass
	def __exit__(self,a,b,c):
		pass

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
	renders it straight to HTML
	"""
	return raw(markdown2.markdown(mdStr))

class BaseHTMLRenderer(BaseRenderer):
	"""
	BaseRenderer for HTML output, uses [Dominate](https://github.com/Knio/dominate)
	internally for generating HTML output
	Each token rendering method should create a dominate tag and it automatically
	gets added to the parent context (because of the with statement). If you return
	a given tag, it will be used as the parent container for all rendered children
	"""

	def __init__(self, start_block):
		self.start_block = start_block

	def render(self):
		with div() as d:
			self.render_block(self.start_block)
		return "".join(str(d) for d in d.children) #Return the array of Dominate dom_tags as strings

	def get_parent_element(self):
		"""
		Returns the current parent Dominate element (uses Dominate internals)
		https://github.com/Knio/dominate/issues/123
		"""
		def _get_thread_context():
			context = [threading.current_thread()]
			# if greenlet:
			# 	context.append(greenlet.getcurrent())
			# 	return hash(tuple(context))
		return dom_tag._with_contexts[_get_thread_context()]

	def render_block(self, block):
		assert isinstance(block, Block)
		type_renderer = getattr(self, "handle_" + block._type, None)
		if not callable(type_renderer):
			if hasattr(self, "handle_default"):
				type_renderer = self.handle_default
			else:
				raise Exception("No handler for block type '{}'.".format(block._type))
		#Render ourselves to an HTML element which automatically gets added to the parent
		#context with Dominate
		selfEl = type_renderer(block)
		if block.children:
			#If we have children, we need to add them to ourself (if we returned a tag
			#to add to) or make a new container for the children
			with selfEl or div(_class='children-list'):
				for child in block.children:
					self.render_block(child)

	def handle_default(self, block):
		p(renderMD(block.title))

	def handle_divider(self, block):
		hr()

	def handle_column_list(self, block):
		return div(style='display: flex;', _class='column-list')

	def handle_column(self, block):
		return div(_class='column')

	def handle_to_do(self, block):
		id = f'chk_{block.id}'
		input(label(_for=id), type='checkbox', id=id, checked=block.checked, title=block.title)

	def handle_code(self, block):
		#TODO: Do we want this to support Markdown? I think there's a notion-py
		#change that might affect this... (the unstyled-title or whatever)
		pre(code(block.title))

	def handle_factory(self, block):
		pass

	def handle_header(self, block):
		h2(renderMD(block.title))

	def handle_sub_header(self, block):
		h3(renderMD(block.title))

	def handle_sub_sub_header(self, block):
		h4(renderMD(block.title))

	def handle_page(self, block):
		h1(renderMD(block.title))

	def handle_bulleted_list(self, block):
		parent = self.get_parent_element()
		#print(parent)
		lastChild = parent.children[-1] if hasattr(parent, 'children') else None
		#Open a new ul if the last child was not a ul
		with lastChild if lastChild and isinstance(lastChild, ul) else ul():
			li(renderMD(block.title))

	def handle_numbered_list(self, block):
		parent = self.get_parent_element()
		#print(parent)
		lastChild = parent.children[-1] if hasattr(parent, 'children') else None
		#Open a new ul if the last child was not a ol
		with lastChild if lastChild and isinstance(lastChild, ol) else ol():
			li(renderMD(block.title))

	def handle_toggle(self, block):
		details(summary(renderMD(block.title)))

	def handle_quote(self, block):
		blockquote(renderMD(block.title))

	handle_text = handle_default

	def handle_equation(self, block):
		p(img(src=f'https://chart.googleapis.com/chart?cht=tx&chl={block.latex}'))

	def handle_embed(self, block):
		iframe(src=block.display_source or block.source, frameborder=0,
			sandbox='allow-scripts allow-popups allow-forms allow-same-origin',
			allowfullscreen='')

	def handle_video(self, block):
		#TODO, this won't work if there's no file extension, we might have
		#to query and get the MIME type...
		src = block.display_source or block.source
		srcType = src.split('.')[-1]
		video(source(src=src, type=f"video/{srcType}"), controls=True)

	handle_file = handle_embed
	handle_pdf = handle_embed

	def handle_audio(self, block):
		audio(src=block.display_source or block.source, controls=True)

	def handle_image(self, block):
		attrs = {}
		if block.caption: # Add the alt attribute if there's a caption
			attrs['alt'] = block.caption
		img(src=block.display_source or block.source, **attrs)

	def handle_bookmark(self, block):
		#return bookmark_template.format(link=, title=block.title, description=block.description, icon=block.bookmark_icon, cover=block.bookmark_cover)
		#It's just a social share card for the website we're bookmarking
		return a(href="block.link")

	def handle_link_to_collection(self, block):
		a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def handle_breadcrumb(self, block):
		p(renderMD(block.title))

	def handle_collection_view(self, block):
		a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def handle_collection_view_page(self, block):
		a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	handle_framer = handle_embed

	def handle_tweet(self, block):
		return requests.get("https://publish.twitter.com/oembed?url=" + block.source).json()["html"]

	handle_gist = handle_embed
	handle_drive = handle_embed
	handle_figma = handle_embed
	handle_loom = handle_embed
	handle_typeform = handle_embed
	handle_codepen = handle_embed
	handle_maps = handle_embed
	handle_invision = handle_embed

	def handle_callout(self, block):
		div( \
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