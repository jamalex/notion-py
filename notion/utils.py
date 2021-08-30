import requests
import uuid

from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, quote_plus, unquote_plus
from datetime import datetime
from slugify import slugify as _dash_slugify

from .settings import BASE_URL, SIGNED_URL_PREFIX, S3_URL_PREFIX, S3_URL_PREFIX_ENCODED


class InvalidNotionIdentifier(Exception):
    pass

def now():
    return int(datetime.now().timestamp() * 1000)


def extract_id(url_or_id):
    """
    Extract the block/page ID from a Notion.so URL -- if it's a bare page URL, it will be the
    ID of the page. If there's a hash with a block ID in it (from clicking "Copy Link") on a
    block in a page), it will instead be the ID of that block. If it's already in ID format,
    it will be passed right through.
    """
    input_value = url_or_id
    if url_or_id.startswith(BASE_URL):
        url_or_id = (
            url_or_id.split("#")[-1]
            .split("/")[-1]
            .split("&p=")[-1]
            .split("?")[0]
            .split("-")[-1]
        )
    try:
        return str(uuid.UUID(url_or_id))
    except ValueError:
        raise InvalidNotionIdentifier(input_value)


def get_embed_data(source_url):

    return requests.get(
        "https://api.embed.ly/1/oembed?key=421626497c5d4fc2ae6b075189d602a2&url={}".format(
            source_url
        )
    ).json()


def get_embed_link(source_url):

    data = get_embed_data(source_url)

    if "html" not in data:
        return source_url

    url = list(BeautifulSoup(data["html"], "html.parser").children)[0]["src"]

    return parse_qs(urlparse(url).query)["src"][0]


def add_signed_prefix_as_needed(url, client=None, id=""):

    if url is None:
        return

    if url.startswith(S3_URL_PREFIX):
        url = SIGNED_URL_PREFIX + quote_plus(url) + "?table=block&id=" + id
        if client:
            url = client.session.head(url).headers.get("Location")

    return url


def remove_signed_prefix_as_needed(url):
    if url is None:
        return
    if url.startswith(SIGNED_URL_PREFIX):
        return unquote_plus(url[len(S3_URL_PREFIX) :])
    elif url.startswith(S3_URL_PREFIX_ENCODED):
        parsed = urlparse(url.replace(S3_URL_PREFIX_ENCODED, S3_URL_PREFIX))
        return "{}://{}{}".format(parsed.scheme, parsed.netloc, parsed.path)
    else:
        return url


def slugify(original):
    return _dash_slugify(original).replace("-", "_")


def get_by_path(path, obj, default=None):

    if isinstance(path, str):
        path = path.split(".")

    value = obj

    # try to traverse down the sequence of keys defined in the path, to get the target value if it exists
    try:
        for key in path:
            if isinstance(value, list):
                key = int(key)
            value = value[key]
    except (KeyError, TypeError, IndexError):
        value = default

    return value
