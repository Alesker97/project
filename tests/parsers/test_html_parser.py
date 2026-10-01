import logging
import pytest
from bs4 import BeautifulSoup
from src.parsers.html_parser import HTMLParser


VALID_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Тестовая страница</title>
    <meta
        name="description"
        content="Описание тестовой страницы"
    >
    <meta
        name="keywords"
        content="python, asyncio, parsing"
    >
</head>
<body>
    <header>Шапка страницы</header>
    <main>
        <h1>Главный заголовок</h1>
        <p>Основной текст страницы</p>
        <a href="/about">О проекте</a>
        <a href="https://external.example.org/news#top">
            Внешняя ссылка
        </a>
    </main>
    <script>ignored()</script>
</body>
</html>
"""

STRUCTURED_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h1>Главный заголовок</h1>
    <h2>Второй заголовок</h2>
    <h3>Третий заголовок</h3>
    <h4>Не извлекаемый заголовок</h4>

    <img src="/images/logo.png" alt="Логотип сайта">
    <img
        src="https://cdn.example.org/banner.png"
        alt="Рекламный баннер"
    >
    <img src="//cdn.example.org/icon.png">
    <img src="data:image/png;base64,image">
    <img alt="Изображение без адреса">

    <table>
        <thead>
            <tr>
                <th>Имя</th>
                <th>Возраст</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Алексей</td>
                <td>30</td>
            </tr>
            <tr>
                <td>Мария</td>
                <td>28</td>
            </tr>
        </tbody>
    </table>

    <ul>
        <li>Первый пункт</li>
        <li>Второй пункт</li>
    </ul>

    <ol>
        <li>Первый шаг</li>
        <li>Второй шаг</li>
    </ol>
</body>
</html>
"""


async def test_parse_html_returns_core_data() -> None:
    parser = HTMLParser()

    result = await parser.parse_html(
        VALID_HTML,
        "https://example.com/catalog/page",
    )

    assert result["url"] == (
        "https://example.com/catalog/page"
    )
    assert result["title"] == "Тестовая страница"
    assert "Шапка страницы" in result["text"]
    assert "Главный заголовок" in result["text"]
    assert "Основной текст страницы" in result["text"]
    assert "ignored()" not in result["text"]
    assert result["links"] == [
        "https://example.com/about",
        "https://external.example.org/news",
    ]
    assert result["metadata"] == {
        "title": "Тестовая страница",
        "description": "Описание тестовой страницы",
        "keywords": "python, asyncio, parsing",
    }


def test_extract_text_uses_css_selector() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        VALID_HTML,
        "lxml",
    )

    result = parser.extract_text(
        soup,
        "main",
    )

    assert result == (
        "Главный заголовок "
        "Основной текст страницы "
        "О проекте "
        "Внешняя ссылка"
    )


def test_extract_links_converts_and_validates_urls() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        """
        <html>
        <body>
            <a href="/about#team">О проекте</a>
            <a href="../contact">Контакты</a>
            <a href="https://other.example.org/news#top">
                Новости
            </a>
            <a href="/about">Повтор</a>
            <a href="#section">Раздел</a>
            <a href="mailto:user@example.com">Почта</a>
            <a href="tel:+79990000000">Телефон</a>
            <a href="javascript:void(0)">Скрипт</a>
            <a href="">Пустая ссылка</a>
        </body>
        </html>
        """,
        "lxml",
    )

    result = parser.extract_links(
        soup,
        "https://example.com/catalog/page",
    )

    assert result == [
        "https://example.com/about",
        "https://example.com/contact",
        "https://other.example.org/news",
    ]


def test_extract_metadata_returns_empty_values() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        "<html><body><p>Текст</p></body></html>",
        "lxml",
    )

    result = parser.extract_metadata(soup)

    assert result == {
        "title": "",
        "description": "",
        "keywords": "",
    }


async def test_parse_html_handles_empty_html() -> None:
    parser = HTMLParser()

    result = await parser.parse_html(
        "",
        "https://example.com/empty",
    )

    assert result == {
        "url": "https://example.com/empty",
        "title": "",
        "text": "",
        "links": [],
        "metadata": {
            "title": "",
            "description": "",
            "keywords": "",
        },
        "images": [],
        "headings": [],
        "tables": [],
        "lists": [],
    }


async def test_parse_html_handles_broken_html() -> None:
    parser = HTMLParser()
    broken_html = """
    <html>
    <body>
        <h1>Сломанный заголовок
        <p>Текст страницы
        <a href="/page">Ссылка
    """

    result = await parser.parse_html(
        broken_html,
        "https://example.com",
    )

    assert result["url"] == "https://example.com"
    assert "Сломанный заголовок" in result["text"]
    assert "Текст страницы" in result["text"]
    assert result["links"] == [
        "https://example.com/page",
    ]


async def test_parse_html_returns_partial_result(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    parser = HTMLParser()

    def raise_error(
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[str]:
        raise RuntimeError("Ошибка извлечения ссылок")

    monkeypatch.setattr(
        parser,
        "extract_links",
        raise_error,
    )
    caplog.set_level(
        logging.WARNING,
        logger="src.parsers.html_parser",
    )

    result = await parser.parse_html(
        VALID_HTML,
        "https://example.com",
    )

    assert result["title"] == "Тестовая страница"
    assert "Основной текст страницы" in result["text"]
    assert result["links"] == []
    assert (
        "Не удалось извлечь ссылки страницы"
        in caplog.text
    )


def test_extract_images_returns_valid_images() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        STRUCTURED_HTML,
        "lxml",
    )

    result = parser.extract_images(
        soup,
        "https://example.com/catalog/page",
    )

    assert result == [
        {
            "src": "https://example.com/images/logo.png",
            "alt": "Логотип сайта",
        },
        {
            "src": (
                "https://cdn.example.org/banner.png"
            ),
            "alt": "Рекламный баннер",
        },
        {
            "src": "https://cdn.example.org/icon.png",
            "alt": "",
        },
    ]


def test_extract_headings_returns_h1_h2_h3() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        STRUCTURED_HTML,
        "lxml",
    )

    result = parser.extract_headings(soup)

    assert result == [
        {
            "level": "h1",
            "text": "Главный заголовок",
        },
        {
            "level": "h2",
            "text": "Второй заголовок",
        },
        {
            "level": "h3",
            "text": "Третий заголовок",
        },
    ]


def test_extract_tables_returns_rows_and_cells() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        STRUCTURED_HTML,
        "lxml",
    )

    result = parser.extract_tables(soup)

    assert result == [
        [
            ["Имя", "Возраст"],
            ["Алексей", "30"],
            ["Мария", "28"],
        ]
    ]


def test_extract_lists_returns_ul_and_ol() -> None:
    parser = HTMLParser()
    soup = BeautifulSoup(
        STRUCTURED_HTML,
        "lxml",
    )

    result = parser.extract_lists(soup)

    assert result == [
        {
            "type": "ul",
            "items": [
                "Первый пункт",
                "Второй пункт",
            ],
        },
        {
            "type": "ol",
            "items": [
                "Первый шаг",
                "Второй шаг",
            ],
        },
    ]


async def test_parse_html_returns_structured_data() -> None:
    parser = HTMLParser()

    result = await parser.parse_html(
        STRUCTURED_HTML,
        "https://example.com/catalog/page",
    )

    assert len(result["images"]) == 3
    assert len(result["headings"]) == 3
    assert len(result["tables"]) == 1
    assert len(result["lists"]) == 2

    assert result["images"][0] == {
        "src": "https://example.com/images/logo.png",
        "alt": "Логотип сайта",
    }
    assert result["headings"][0] == {
        "level": "h1",
        "text": "Главный заголовок",
    }
    assert result["tables"][0][1] == [
        "Алексей",
        "30",
    ]
    assert result["lists"][1] == {
        "type": "ol",
        "items": [
            "Первый шаг",
            "Второй шаг",
        ],
    }
