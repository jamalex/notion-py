from .logger import logger
from .maps import property_map, field_map
from .records import Record


class User(Record):

    _table = "notion_user"

    given_name = field_map("given_name")
    family_name = field_map("family_name")
    email = field_map("email")
    locale = field_map("locale")
    time_zone = field_map("time_zone")

    @property
    def full_name(self):
        return " ".join([self.given_name or "", self.family_name or ""]).strip()

    def _str_fields(self):
        return super()._str_fields() + ["email", "full_name"]
