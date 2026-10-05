from collections import Counter

import pytest
from aiohttp import web

from src.parsers.sitemap_parser import SitemapParser


@pytest.fixture
async def sitemap_site():
    hits = Counter()

    async def handle(request):
        hits[request.path] += 1
        base = f"http://{request.host}"
        if request.path == "/index.xml":
            xml = (
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<sitemap><loc>/pages.xml</loc></sitemap>'
                '<sitemap><loc>/nested.xml</loc></sitemap>'
                '<sitemap><loc>/pages.xml</loc></sitemap></sitemapindex>'
            )
        elif request.path == "/nested.xml":
            xml = '<sitemapindex><sitemap><loc>/index.xml</loc></sitemap><sitemap><loc>/more.xml</loc></sitemap></sitemapindex>'
        elif request.path == "/pages.xml":
            xml = f'<urlset><url><loc>{base}/a</loc></url><url><loc>{base}/b</loc></url></urlset>'
        elif request.path == "/more.xml":
            xml = f'<urlset><url><loc>{base}/b</loc></url><url><loc>{base}/c</loc></url></urlset>'
        elif request.path == "/broken.xml":
            xml = "<urlset><url>"
        else:
            return web.Response(status=404)
        return web.Response(text=xml, content_type="application/xml")

    app = web.Application()
    app.router.add_get("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}", hits
    finally:
        await runner.cleanup()


async def test_sitemap_index_recursion_deduplication_and_cycle(sitemap_site):
    base, hits = sitemap_site
    parser = SitemapParser()
    try:
        assert await parser.fetch_sitemap(f"{base}/index.xml") == [
            f"{base}/a", f"{base}/b", f"{base}/c",
        ]
        assert hits["/index.xml"] == 1
        assert hits["/pages.xml"] == 1
        assert hits["/nested.xml"] == 1
    finally:
        await parser.close()


async def test_sitemap_invalid_xml_and_limit(sitemap_site):
    base, _ = sitemap_site
    parser = SitemapParser(max_sitemaps=2)
    try:
        with pytest.raises(ValueError, match="Некорректный sitemap"):
            await parser.fetch_sitemap(f"{base}/broken.xml")
        with pytest.raises(ValueError, match="лимит"):
            await parser.fetch_sitemap(f"{base}/index.xml")
    finally:
        await parser.close()
