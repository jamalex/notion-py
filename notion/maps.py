from .markdown import markdown_to_notion, notion_to_markdown


def field_map(path, python_to_api=lambda x: x, api_to_python=lambda x: x):
    """
    Returns a property that maps a Block attribute onto a field in the API data structures.
    
    - `path` can either be a top-level field-name, a list that specifies the key names to traverse,
      or a dot-delimited string representing the same traversal.

    - `python_to_api` is a function that converts values as given in the Python layer into the
      internal representation to be sent along in the API request.

    - `api_to_python` is a function that converts what is received from the API into an internal
      representation to be returned to the Python layer.
    """

    if not isinstance(path, tuple):
        path = (path,)

    def fget(self):
        return api_to_python(self.get(path[0]))

    def fset(self, value):
        for p in path:
            self.set(p, python_to_api(value))

    return property(fget=fget, fset=fset)


def property_map(name, python_to_api=lambda x: x, api_to_python=lambda x: x, markdown=True):
    """
    Similar to `field_map`, except it works specifically with the data under the "properties" field
    in the API's block table, and just takes a single name to specify which subkey to reference.
    Also, these properties all seem to use a special "embedded list" format that breaks the text
    up into a sequence of chunks and associated format metadata. If `markdown` is True, we convert
    this representation into commonmark-compatible markdown, and back again when saving.
    """

    def py2api(x):
        x = python_to_api(x)
        if markdown:
            x = markdown_to_notion(x)
        return x

    def api2py(x):
        x = x or [[""]]
        if markdown:
            x = notion_to_markdown(x)
        return api_to_python(x)

    return field_map(["properties", name], python_to_api=py2api, api_to_python=api2py)


def joint_map(*mappings):
    """
    Combine multiple `field_map` and `property_map` instances together to map an attribute to multiple API fields.
    Note: when "getting", the first one will be used. When "setting", they will all be set in parallel.
    """

    def fget(self):
        return mappings[0].fget(self)

    def fset(self, value):
        for m in mappings:
            m.fset(self, value)

    return property(fget=fget, fset=fset)
