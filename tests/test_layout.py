from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from flask import Flask, flash, render_template_string
from flask.testing import FlaskClient

PAGES = ["/", "/auth/register", "/auth/login"]


class _PageParser(HTMLParser):
    """Collects tag names, link targets and stylesheet hrefs from a page."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.links: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.stylesheets.append(values["href"])


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    return parser


@pytest.mark.parametrize("path", PAGES)
def test_page_uses_semantic_layout(client: FlaskClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    page = _parse(response.get_data(as_text=True))
    assert {"header", "nav", "main", "footer"} <= page.tags


@pytest.mark.parametrize("path", PAGES)
def test_internal_links_work(client: FlaskClient, path: str) -> None:
    page = _parse(client.get(path).get_data(as_text=True))
    internal = {link for link in page.links if not urlsplit(link).netloc and not link.startswith("#")}
    assert internal
    for link in internal:
        assert client.get(link).status_code == 200, link


def test_landing_page_links_to_sign_up_and_log_in(client: FlaskClient) -> None:
    page = _parse(client.get("/").get_data(as_text=True))
    assert "/auth/register" in page.links
    assert "/auth/login" in page.links


def test_stylesheet_is_served(client: FlaskClient) -> None:
    (href,) = _parse(client.get("/").get_data(as_text=True)).stylesheets
    response = client.get(href)
    assert response.status_code == 200
    assert response.mimetype == "text/css"
    response.close()


@pytest.mark.parametrize(("path", "heading"), [("/auth/register", "Sign up"), ("/auth/login", "Log in")])
def test_auth_placeholders(client: FlaskClient, path: str, heading: str) -> None:
    html = client.get(path).get_data(as_text=True)
    assert f"<h1>{heading}</h1>" in html
    assert "coming soon" in html
    assert 'aria-current="page"' in html


def test_unknown_url_shows_404_page(client: FlaskClient) -> None:
    response = client.get("/no-such-page")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "Page not found" in html
    assert "<main" in html


def _add_route(app: Flask, rule: str, view) -> None:  # type: ignore[no-untyped-def]
    app.add_url_rule(rule, endpoint=rule.strip("/"), view_func=view)


def test_uncaught_error_shows_500_page(app: Flask, caplog: pytest.LogCaptureFixture) -> None:
    def boom() -> str:
        raise RuntimeError("test-only failure")

    _add_route(app, "/boom", boom)
    app.config["PROPAGATE_EXCEPTIONS"] = False  # testing mode re-raises errors by default
    response = app.test_client().get("/boom")

    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert "Something went wrong" in html
    assert "test-only failure" not in html  # no internals shown to the visitor
    assert "test-only failure" in caplog.text  # but the error is logged


def test_flash_messages_render_by_category(app: Flask) -> None:
    def flashes() -> str:
        flash("Saved.", "success")
        flash("Nope.", "error")
        flash("Plain message.")
        return render_template_string('{% extends "base.html" %}')

    _add_route(app, "/flashes", flashes)
    html = app.test_client().get("/flashes").get_data(as_text=True)
    assert '<p class="flash flash-success">Saved.</p>' in html
    assert '<p class="flash flash-error">Nope.</p>' in html
    assert '<p class="flash flash-info">Plain message.</p>' in html


def test_flash_messages_are_escaped(app: Flask) -> None:
    def flashes() -> str:
        flash('<script>alert("x")</script>', "<b>bad-category</b>")
        return render_template_string('{% extends "base.html" %}')

    _add_route(app, "/flashes", flashes)
    html = app.test_client().get("/flashes").get_data(as_text=True)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "<b>bad-category</b>" not in html
    assert "flash-info" in html


def test_no_flash_container_without_messages(client: FlaskClient) -> None:
    assert 'class="flashes"' not in client.get("/").get_data(as_text=True)
