from .logger import logger
from .maps import property_map, field_map
from .records import Record


class Space(Record):

    _table = "space"

    child_list_key = "pages"

    name = field_map("name")
    domain = field_map("domain")
    icon = field_map("icon")

    @property
    def pages(self):
        # The page list includes pages the current user might not have permissions on, so it's slow to query.
        # Instead, we just filter for pages with the space as the parent.
        return self._client.search_pages_with_parent(self.id)

    @property
    def users(self):
        user_ids = [permission["user_id"] for permission in self.get("permissions")]
        self._client.refresh_records(notion_user=user_ids)
        return [self._client.get_user(user_id) for user_id in user_ids]

    def _str_fields(self):
        return super()._str_fields() + ["name", "domain"]

    def add_page(self, title, type="page", shared=False):
        assert type in [
            "page",
            "collection_view_page",
        ], "'type' must be one of 'page' or 'collection_view_page'"
        if shared:
            permissions = [{"role": "editor", "type": "space_permission"}]
        else:
            permissions = [
                {
                    "role": "editor",
                    "type": "user_permission",
                    "user_id": self._client.current_user.id,
                }
            ]
        page_id = self._client.create_record(
            "block", self, type=type, permissions=permissions
        )
        page = self._client.get_block(page_id)
        page.title = title
        return page
