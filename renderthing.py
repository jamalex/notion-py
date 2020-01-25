import subprocess
from notion.client import NotionClient
from notion.renderer import BaseHTMLRenderer

cl = NotionClient("46a40b826ac2a89b1089342be5090a8f5cc0863b93dee048cc2fe42eb462e5a277451ce92ab951f215b85a6dd61e177633c5b1ea6e6af48a25ad6dda0d87c0965cf351f5944fb4a2cdaae42ddb13")
b = cl.get_block("https://www.notion.so/sourceequine/P-Source-Equine-Prototype-Scope-410bde26aa1a495c9c4e15dea45ad5f9")
subprocess.run("clip", universal_newlines=True, input=BaseHTMLRenderer(b, render_sub_pages=False, with_styles=True, render_table_pages_after_table=True).render())