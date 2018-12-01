from records import Record
from maps import property_map, field_map


class Space(Record):

    _table = "space"

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
