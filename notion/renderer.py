import markdown2
import requests

from .block import *


class BaseRenderer(object):

	def __init__(self, start_block):
		self.start_block = start_block

	def render(self):
		return self.render_block(self.start_block)

	def calculate_child_indent(self, block):
		if block.type == "page":
			return 0
		else:
			return 1

	def render_block(self, block, level=0, preblock=None, postblock=None):
		assert isinstance(block, Block)
		type_renderer = getattr(self, "handle_" + block._type, None)
		if not callable(type_renderer):
			if hasattr(self, "handle_default"):
				type_renderer = self.handle_default
			else:
				raise Exception("No handler for block type '{}'.".format(block._type))
		pretext = type_renderer(block, level=level, preblock=preblock, postblock=postblock)
		if isinstance(pretext, tuple):
			pretext, posttext = pretext
		else:
			posttext = ""
		return pretext + self.render_children(block, level=level+self.calculate_child_indent(block)) + posttext

	def render_children(self, block, level):
		kids = block.children
		if not kids:
			return ""
		text = ""
		for i in range(len(kids)):
			preblock = None
			postblock = None
			if i > 0:
				preblock = kids[i-1]
			if i < len(kids)-2:
				postblock = kids[i + 1]
			text += self.render_block(kids[i], level=level, preblock=preblock, postblock=postblock)
		return text


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

	def create_opening_tag(self, tagname, attributes={}):
		attrs = "".join(' {}="{}"'.format(key, val) for key, val in attributes.items())
		return "<{tagname}{attrs}>".format(tagname=tagname, attrs=attrs)

	def wrap_in_tag(self, block, tagname, fieldname="title", attributes={}):
		opentag = self.create_opening_tag(tagname, attributes)
		innerhtml = markdown2.markdown(getattr(block, fieldname))
		return "{opentag}{innerhtml}</{tagname}>".format(opentag=opentag, tagname=tagname, innerhtml=innerhtml)

	def left_margin_for_level(self, level):
		return {"display": "margin-left: {}px;".format(level * 20)}

	def handle_default(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "p", attributes=self.left_margin_for_level(level))

	def handle_divider(self, block, level=0, preblock=None, postblock=None):
		return "<hr/>"

	def handle_column_list(self, block, level=0, preblock=None, postblock=None):
		return '<div style="display: flex; padding-top: 12px; padding-bottom: 12px;">', '</div>'

	def handle_column(self, block, level=0, preblock=None, postblock=None):
		buffer = (len(block.parent.children) - 1) * 46
		width = block.get("format.column_ratio")
		return '<div style="flex-grow: 0; flex-shrink: 0; width: calc((100% - {}px) * {});">'.format(buffer, width), '</div>'

	def handle_to_do(self, block, level=0, preblock=None, postblock=None):
		return '<input type="checkbox" id="{id}" name="{id}"{checked}><label for="{id}">{title}</label><br/>'.format(
			id="chk_" + block.id,
			checked=" checked" if block.checked else "",
			title=block.title,
		)

	def handle_code(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "code", attributes=self.left_margin_for_level(level))

	def handle_factory(self, block, level=0, preblock=None, postblock=None):
		return ""

	def handle_header(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "h2", attributes=self.left_margin_for_level(level))

	def handle_sub_header(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "h3", attributes=self.left_margin_for_level(level))

	def handle_sub_sub_header(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "h4", attributes=self.left_margin_for_level(level))

	def handle_page(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "h1", attributes=self.left_margin_for_level(level))

	def handle_bulleted_list(self, block, level=0, preblock=None, postblock=None):
		text = ""
		if preblock is None or preblock.type != "bulleted_list":
			text = self.create_opening_tag("ul", attributes=self.left_margin_for_level(level))
		text += self.wrap_in_tag(block, "li")
		if postblock is None or postblock.type != "bulleted_list":
			text += "</ul>"
		return text

	def handle_numbered_list(self, block, level=0, preblock=None, postblock=None):
		text = ""
		if preblock is None or preblock.type != "numbered_list":
			text = self.create_opening_tag("ol", attributes=self.left_margin_for_level(level))
		text += self.wrap_in_tag(block, "li")
		if postblock is None or postblock.type != "numbered_list":
			text += "</ol>"
		return text

	def handle_toggle(self, block, level=0, preblock=None, postblock=None):
		innerhtml = markdown2.markdown(block.title)
		opentag = self.create_opening_tag("details", attributes=self.left_margin_for_level(level))
		return '{opentag}<summary>{innerhtml}</summary>'.format(opentag=opentag, innerhtml=innerhtml), '</details>'

	def handle_quote(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "blockquote", attributes=self.left_margin_for_level(level))

	def handle_text(self, block, level=0, preblock=None, postblock=None):
		return self.handle_default(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_equation(self, block, level=0, preblock=None, postblock=None):
		text = self.create_opening_tag("p", attributes=self.left_margin_for_level(level))
		return text + '<img src="https://chart.googleapis.com/chart?cht=tx&chl={}"/></p>'.format(block.latex)

	def handle_embed(self, block, level=0, preblock=None, postblock=None):
		iframetag = self.create_opening_tag("iframe", attributes={
			"src": block.display_source or block.source,
			"frameborder": 0,
			"sandbox": "allow-scripts allow-popups allow-forms allow-same-origin",
			"allowfullscreen": "",
			"style": "width: {width}px; height: {height}px; border-radius: 1px;".format(width=block.width, height=block.height),
		})
		return '<div style="text-align: center;">' + iframetag + "</iframe></div>"

	def handle_video(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_file(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_audio(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_pdf(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_image(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_bookmark(self, block, level=0, preblock=None, postblock=None):
		return bookmark_template.format(link=block.link, title=block.title, description=block.description, icon=block.bookmark_icon, cover=block.bookmark_cover)

	def handle_link_to_collection(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "p", attributes={"href": "https://www.notion.so/" + block.id.replace("-", "")})

	def handle_breadcrumb(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "p", attributes=self.left_margin_for_level(level))

	def handle_collection_view(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "p", attributes={"href": "https://www.notion.so/" + block.id.replace("-", "")})

	def handle_collection_view_page(self, block, level=0, preblock=None, postblock=None):
		return self.wrap_in_tag(block, "p", attributes={"href": "https://www.notion.so/" + block.id.replace("-", "")})

	def handle_framer(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_tweet(self, block, level=0, preblock=None, postblock=None):
		return requests.get("https://publish.twitter.com/oembed?url=" + block.source).json()["html"]

	def handle_gist(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_drive(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_figma(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_loom(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_typeform(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_codepen(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_maps(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_invision(self, block, level=0, preblock=None, postblock=None):
		return self.handle_embed(block=block, level=level, preblock=preblock, postblock=postblock)

	def handle_callout(self, block, level=0, preblock=None, postblock=None):
		return callout_template.format(icon=block.icon, title=markdown2.markdown(block.title))

