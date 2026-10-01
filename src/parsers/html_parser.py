import asyncio
import logging
from urllib.parse import urldefrag, urljoin, urlparse
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


class HTMLParser:
    async def parse_html(
        self,
        html: str,
        url: str,
    ) -> dict[str, object]:
        return await asyncio.to_thread(
            self._parse_html,
            html,
            url,
        )

    def _parse_html(
        self,
        html: str,
        url: str,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "url": url,
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

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception as error:
            logger.warning(
                "Не удалось разобрать HTML страницы %s: %s",
                url,
                error,
            )
            return result

        try:
            metadata = self.extract_metadata(soup)
            result["metadata"] = metadata
            result["title"] = metadata["title"]
        except Exception as error:
            logger.warning(
                "Не удалось извлечь метаданные страницы %s: %s",
                url,
                error,
            )

        try:
            result["text"] = self.extract_text(soup)
        except Exception as error:
            logger.warning(
                "Не удалось извлечь текст страницы %s: %s",
                url,
                error,
            )

        try:
            result["links"] = self.extract_links(
                soup,
                url,
            )
        except Exception as error:
            logger.warning(
                "Не удалось извлечь ссылки страницы %s: %s",
                url,
                error,
            )

        try:
            result["images"] = self.extract_images(
                soup,
                url,
            )
        except Exception as error:
            logger.warning(
                "Не удалось извлечь изображения страницы %s: %s",
                url,
                error,
            )

        try:
            result["headings"] = self.extract_headings(
                soup
            )
        except Exception as error:
            logger.warning(
                "Не удалось извлечь заголовки страницы %s: %s",
                url,
                error,
            )

        try:
            result["tables"] = self.extract_tables(soup)
        except Exception as error:
            logger.warning(
                "Не удалось извлечь таблицы страницы %s: %s",
                url,
                error,
            )

        try:
            result["lists"] = self.extract_lists(soup)
        except Exception as error:
            logger.warning(
                "Не удалось извлечь списки страницы %s: %s",
                url,
                error,
            )

        return result

    def extract_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[str]:
        links = []
        seen_links = set()

        for element in soup.find_all("a", href=True):
            href = element.get("href")

            if not isinstance(href, str):
                continue

            href = href.strip()

            if not href or href.startswith("#"):
                continue

            absolute_url = urljoin(base_url, href)
            absolute_url, _ = urldefrag(absolute_url)
            parsed_url = urlparse(absolute_url)

            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_url.netloc
            ):
                continue

            if absolute_url in seen_links:
                continue

            seen_links.add(absolute_url)
            links.append(absolute_url)

        return links

    def extract_images(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[dict[str, str]]:
        images = []

        for element in soup.find_all("img"):
            src = element.get("src")
            alt = element.get("alt", "")

            if not isinstance(src, str) or not src.strip():
                continue

            absolute_url = urljoin(
                base_url,
                src.strip(),
            )
            absolute_url, _ = urldefrag(absolute_url)
            parsed_url = urlparse(absolute_url)

            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_url.netloc
            ):
                continue

            normalized_alt = (
                " ".join(alt.split())
                if isinstance(alt, str)
                else ""
            )

            images.append(
                {
                    "src": absolute_url,
                    "alt": normalized_alt,
                }
            )

        return images

    def extract_headings(
        self,
        soup: BeautifulSoup,
    ) -> list[dict[str, str]]:
        headings = []

        for element in soup.find_all(
            ["h1", "h2", "h3"]
        ):
            text = element.get_text(
                " ",
                strip=True,
            )

            if not text:
                continue

            headings.append(
                {
                    "level": element.name,
                    "text": text,
                }
            )

        return headings

    def extract_tables(
        self,
        soup: BeautifulSoup,
    ) -> list[list[list[str]]]:
        tables = []

        for table_element in soup.find_all("table"):
            table_rows = []

            for row_element in table_element.find_all("tr"):
                cells = row_element.find_all(
                    ["th", "td"],
                    recursive=False,
                )

                if not cells:
                    continue

                row = [
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                    for cell in cells
                ]
                table_rows.append(row)

            if table_rows:
                tables.append(table_rows)

        return tables

    def extract_lists(
        self,
        soup: BeautifulSoup,
    ) -> list[dict[str, object]]:
        lists = []

        for list_element in soup.find_all(
            ["ul", "ol"]
        ):
            items = [
                item.get_text(
                    " ",
                    strip=True,
                )
                for item in list_element.find_all(
                    "li",
                    recursive=False,
                )
            ]
            items = [
                item
                for item in items
                if item
            ]

            if not items:
                continue

            lists.append(
                {
                    "type": list_element.name,
                    "items": items,
                }
            )

        return lists

    def extract_text(
        self,
        soup: BeautifulSoup,
        selector: str | None = None,
    ) -> str:
        root = soup.select_one(selector) if selector else soup

        if root is None:
            return ""

        text_parts = []

        for text_node in root.find_all(string=True):
            parent = text_node.parent

            if (
                parent is None
                or parent.name
                in {
                    "script",
                    "style",
                    "noscript",
                    "title",
                }
            ):
                continue

            text = " ".join(str(text_node).split())

            if text:
                text_parts.append(text)

        return " ".join(text_parts)

    def extract_metadata(
        self,
        soup: BeautifulSoup,
    ) -> dict[str, str]:
        metadata = {
            "title": "",
            "description": "",
            "keywords": "",
        }

        if soup.title is not None:
            metadata["title"] = soup.title.get_text(
                " ",
                strip=True,
            )

        for element in soup.find_all("meta"):
            name = element.get("name")
            content = element.get("content")

            if not isinstance(name, str):
                continue

            normalized_name = name.strip().lower()

            if (
                normalized_name
                not in {
                    "description",
                    "keywords",
                }
                or not isinstance(content, str)
            ):
                continue

            if not metadata[normalized_name]:
                metadata[normalized_name] = " ".join(
                    content.split()
                )

        return metadata
