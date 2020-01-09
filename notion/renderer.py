import markdown2
import requests
import dominate
from dominate.tags import *

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
		with div() as d:
			self.render_block(self.start_block)
		return d

	def calculate_child_indent(self, block):
		if block.type == "page":
			return 0
		else:
			return 1

	def render_block(self, block, level=0):
		assert isinstance(block, Block)
		type_renderer = getattr(self, "handle_" + block._type, None)
		if not callable(type_renderer):
			if hasattr(self, "handle_default"):
				type_renderer = self.handle_default
			else:
				raise Exception("No handler for block type '{}'.".format(block._type))
		#Render ourselves to an HTML element and then add all our children to it
		selfEl = type_renderer(block, level=level)
		with selfEl if isinstance(selfEl, dominate.dom_tag.dom_tag) else nullcontext():
			for child in block.children:
				self.render_block(child, level=level+self.calculate_child_indent(block))
		return selfEl


bookmark_template = """
<div>
   <div style="display: flex;">
      <a target="_blank" rel="noopener noreferrer" href="{link}" style="display: block; color: inherit; text-decoration: none; flex-grow: 1; min-width: 0px;">
         <div role="button" style="user-select: none; transition: background 120ms ease-in 0s; cursor: pointer; width: 100%; display: flex; flex-wrap: wrap-reverse; align-items: stretch; text-align: left; overflow: hidden; border: 1px solid rgba(55, 53, 47, 0.16); border-radius: 3px; position: relative; color: inherit; fill: inherit;">
            <div style="flex: 4 1 180px; min-height: 60px; padding: 12px 14px 14px; overflow: hidden; text-align: left;">
               <div style="font-size: 14px; line-height: 20px; color: rgb(55, 53, 47); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px;">{title}</div>
               <div style="font-size: 12px; line-height: 16px; color: rgba(55, 53, 47, 0.6); height: 32px; overflow: hidden;">{description}</div>
               <div style="display: flex; margin-top: 6px;">
                  <img src="{icon}" style="width: 16px; height: 16px; min-width: 16px; margin-right: 6px;">
                  <div style="font-size: 12px; line-height: 16px; color: rgb(55, 53, 47); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{link}/div>
               </div>
            </div>
            <div style="flex: 1 1 180px; min-height: 80px; display: block; position: relative;">
               <div style="position: absolute; top: 0px; left: 0px; right: 0px; bottom: 0px;">
                  <div style="width: 100%; height: 100%;"><img src="{cover}" style="display: block; object-fit: cover; border-radius: 1px; width: 100%; height: 100%;"></div>
               </div>
            </div>
         </div>
      </a>
   </div>
</div>
"""

callout_template = """
<div style="padding: 16px 16px 16px 12px; display: flex; width: 100%; border-radius: 3px; border-width: 1px; border-style: solid; border-color: transparent; background: rgba(235, 236, 237, 0.3);">
   <div>
      <div role="button" style="user-select: none; cursor: pointer; display: flex; align-items: center; justify-content: center; height: 24px; width: 24px; border-radius: 3px; flex-shrink: 0;">
         <div style="display: flex; align-items: center; justify-content: center; height: 24px; width: 24px;">
            <div style="height: 16.8px; width: 16.8px; font-size: 16.8px; line-height: 1.1; margin-left: 0px; color: black;">{icon}</div>
         </div>
      </div>
   </div>
   <div style="max-width: 100%; width: 100%; white-space: pre-wrap; word-break: break-word; caret-color: rgb(55, 53, 47); margin-left: 8px;">{title}</div>
</div>
"""

class BaseHTMLRenderer(BaseRenderer):
	def handle_default(self, block, level=0):
		p(block.title)

	def handle_divider(self, block, level=0):
		hr()

	def handle_column_list(self, block, level=0):
		return div(style='display: flex;', _class='column-list')

	def handle_column(self, block, level=0):
		return div(_class='column')

	def handle_to_do(self, block, level=0):
		id = f'chk_{block.id}'
		input(type='checkbox', id=id, checked=block.checked, title=block.title).add(
			label(_for=id)).add(br())

	def handle_code(self, block, level=0):
		code(block.title)

	def handle_factory(self, block, level=0):
		pass

	def handle_header(self, block, level=0):
		h2(block.title)

	def handle_sub_header(self, block, level=0):
		h3(block.title)

	def handle_sub_sub_header(self, block, level=0):
		h4(block.title)

	def handle_page(self, block, level=0):
		h1(block.title)

	def handle_bulleted_list(self, block, level=0):
		ctx = next(dom_tag._with_contexts.values())
		with ctx.children[-1] if isinstance(ctx.children[-1], ul) else ul():
			li(block.title)

	def handle_numbered_list(self, block, level=0):
		ctx = next(dom_tag._with_contexts.values())
		with ctx.children[-1] if isinstance(ctx.children[-1], ol) else ol():
			li(block.title)

	def handle_toggle(self, block, level=0):
		details(summary(block.title))

	def handle_quote(self, block, level=0):
		blockquote(block.title)

	def handle_text(self, block, level=0):
		return self.handle_default(block=block, level=level)

	def handle_equation(self, block, level=0):
		p(img(src=f'https://chart.googleapis.com/chart?cht=tx&chl={block.latex}'))

	def handle_embed(self, block, level=0):
		iframe(src=block.display_source or block.source, frameborder=0,
			sandbox='allow-scripts allow-popups allow-forms allow-same-origin',
			allowfullscreen='')

	def handle_video(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_file(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_audio(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_pdf(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_image(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_bookmark(self, block, level=0):
		return bookmark_template.format(link=block.link, title=block.title, description=block.description, icon=block.bookmark_icon, cover=block.bookmark_cover)

	def handle_link_to_collection(self, block, level=0):
		a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def handle_breadcrumb(self, block, level=0):
		p(block.title)

	def handle_collection_view(self, block, level=0):
		a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def handle_collection_view_page(self, block, level=0):
		a(href=f'https://www.notion.so/{block.id.replace("-", "")}')

	def handle_framer(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_tweet(self, block, level=0):
		return requests.get("https://publish.twitter.com/oembed?url=" + block.source).json()["html"]

	def handle_gist(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_drive(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_figma(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_loom(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_typeform(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_codepen(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_maps(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_invision(self, block, level=0):
		return self.handle_embed(block=block, level=level)

	def handle_callout(self, block, level=0):
		return callout_template.format(icon=block.icon, title=markdown2.markdown(block.title))
