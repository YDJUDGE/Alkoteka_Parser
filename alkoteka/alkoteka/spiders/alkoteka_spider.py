import scrapy
import time
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterable, Any
from alkoteka.items import AlkotekaItem
import json


class AlkotekaSpider(scrapy.Spider):
    """Парсинг товаров"""
    name = "AlkotekaSpiderSpider"
    allowed_domains = ["alkoteka.com"]
    CITY_ID = "1461"  # BITRIX_SM_CITY_ID for Krasnodar
    CITY_UUID = "4a70f9e0-46ae-11e7-83ff-00155d026416"  # City UUID for Krasnodar
    BASE_API_URL = "https://alkoteka.com/web-api/v1/product"
    processed_items = []

    def _normalize_meta_key(self, key: str) -> str:
        """Приводим ключи к читаемому виду"""
        mapping = {
            "obem": "Объем",
            "cvet": "Цвет",
            "strana": "Страна",
            "kod-tovara": "Код товара",
            "soderzanie-saxara": "Содержание сахара",
            "categories": None  # не учитываем Categories
        }
        k = key.strip().lower()
        return mapping.get(k, k.replace("-", " ").capitalize())

    def _clean_description(self, text: str) -> str:
        """Очищаем описание товара"""
        if not text:
            return ""
        txt = re.sub(r"<[^>]+>", "", text)
        txt = re.sub(r"\r\n|\r", "\n", txt)
        txt = re.sub(r"(?i)^\s*Описание\s*:?.*?\n?", "", txt).strip()
        txt = re.sub(r"\n{2,}", "\n", txt)
        txt = re.sub(r"[ \t]{2,}", " ", txt)
        return txt.strip()

    def _extract_color_from_text(self, text: str) -> str:
        """Извлекаем цвет напитка"""
        if not text:
            return ""
        m = re.search(r"(?mi)^\s*Цвет[:\s\-–—]*([^\.\n\r]{1,60})", text) or \
            re.search(r"(?i)\bцвет[:\s\-–—]*([^\.,\n]{1,60})", text)
        return m.group(1).strip().rstrip('.,;:') if m else ""

    def start_requests(self) -> Iterable[Any]:
        """Точка входа парсера"""
        categories_file = Path(__file__).parent / 'categories.txt'
        if not categories_file.exists():
            self.logger.error("categories.txt file not found.")
            return
        with open(categories_file, encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        for url in urls:
            parsed = urlparse(url)
            parts = [p for p in parsed.path.split('/') if p]
            slug = parts[1] if len(parts) >= 2 and parts[0] == "catalog" else ""
            if not slug:
                continue
            api_url = f"{self.BASE_API_URL}?city_uuid={self.CITY_UUID}&root_category_slug={slug}&page=1&per_page=200"
            self.logger.info(f"Starting with category: {slug}, URL: {api_url}")
            yield scrapy.Request(
                api_url,
                callback=self.parse_api,
                meta={"category_slug": slug, "page": 1},
                cookies={"BITRIX_SM_CITY_ID": self.CITY_ID},
                dont_filter=True
            )

    def parse_api(self, response):
        """Парсит API ответ по товарам"""
        try:
            data = response.json()
        except ValueError:
            self.logger.error(f"Failed to parse JSON from {response.url}")
            return

        products = data.get("results") or data.get("products") or []
        if not products:
            self.logger.warning(f"No products found in {response.url}")
            return

        meta_info = data.get("meta", {})
        total = int(meta_info.get("total", 0))
        per_page = int(meta_info.get("per_page", 200))
        page = int(meta_info.get("current_page", response.meta.get("page", 1)))
        self.logger.info(
            f"Processing page {page} for {response.meta['category_slug']}, total: {total}, per_page: {per_page}")

        max_pages = (total + per_page - 1) // per_page
        has_more_pages = page < max_pages

        slug = response.meta.get("category_slug", "")
        section = []
        first_cat = (
            products[0].get("category")
            if products and isinstance(products[0].get("category"), dict)
            else None
        )
        if first_cat:
            parent = first_cat.get("parent", {})
            if parent.get("name"):
                section.append(parent["name"])
            if first_cat.get("name"):
                section.append(first_cat["name"])
        elif slug:
            section = [slug.replace("-", " ").capitalize()]

        for p in products:
            timestamp = int(time.time())
            uuid = p.get("uuid") or p.get("id") or ""
            name = p.get("name") or p.get("title") or ""
            product_url = p.get("product_url") or p.get("url") or ""
            if product_url.startswith("/"):
                product_url = response.urljoin(product_url)

            description = self._clean_description(p.get("description") or "")
            filters = p.get("filter_labels") if isinstance(p.get("filter_labels"), list) else []
            self.logger.debug(f"Filters for product {uuid}: {filters}")  # Отладочный вывод
            volume = next((fl.get("title") for fl in filters if (fl.get("filter") or fl.get("code")) == "obem"), "")
            title = name.strip()
            if volume and volume.lower() not in name.lower():
                title += f", {volume}"
            color = next((fl.get("title") for fl in filters if (fl.get("filter") or fl.get("code")) == "cvet"),
                         self._extract_color_from_text(description))
            if color and color.lower() not in title.lower():
                title += f", {color}"

            metadata = {"__description": description}
            if p.get("country"):
                metadata["Страна"] = p["country"]
            if p.get("vendor_code") is not None:
                metadata["Код товара"] = str(p["vendor_code"])
            if p.get("rate") is not None:  # рейтинг
                metadata["Рейтинг"] = p["rate"]

            for fl in filters:
                key = fl.get("filter") or fl.get("code")
                values = fl.get("values", {})
                if isinstance(values, str):
                    val = values
                elif isinstance(values, dict):
                    val = values.get("value", next(iter(values.values()), fl.get("title")))
                else:
                    val = next((v.get("name") for v in values if v.get("enabled", False)), fl.get("title"))
                if not key or not val:
                    continue
                normalized_key = self._normalize_meta_key(key)
                if normalized_key:
                    metadata[normalized_key] = val
                else:
                    self.logger.warning(f"Unrecognized key skipped: {key} with value {val}")

            current_price = float(p.get("price") or 0.0)
            original_price = float(p.get("prev_price") or current_price)
            sale_tag = f"Скидка {int(round((original_price - current_price) / original_price * 100))}%" if original_price > current_price else ""

            imgs = list({response.urljoin(i) for i in (p.get("images") or [p.get("image_url")] or []) if i})
            main_image = imgs[0] if imgs else ""

            in_stock = bool(p.get("available", p.get("in_stock", False)))
            stock_count = int(p.get("quantity_total", 0) or 0)
            marketing_tags = [a.get("title") for a in (p.get("action_labels") or []) if a.get("title")]

            # Добавляем спецтеги
            if p.get("new"):
                marketing_tags.append("Новинка")
            if p.get("recomended"):
                marketing_tags.append("Рекомендуем")

            variants = int(p.get("variants_count") or p.get("variants") or 1)

            item = AlkotekaItem(
                timestamp=timestamp,
                RPC=uuid,
                url=product_url,
                title=title,
                marketing_tags=marketing_tags,
                brand="",
                section=section,
                price_data={
                    "current": current_price,
                    "original": original_price,
                    "sale_tag": sale_tag
                },
                stock={
                    "in_stock": in_stock,
                    "count": stock_count
                },
                assets={
                    "main_image": main_image,
                    "set_images": imgs,
                    "view360": [],
                    "video": []
                },
                metadata=metadata,
                variants=variants
            )
            self.processed_items.append(dict(item))
            yield item

        if has_more_pages:
            page = response.meta.get("page", 1) + 1
            next_api = f"{self.BASE_API_URL}?city_uuid={self.CITY_UUID}&root_category_slug={slug}&page={page}&per_page=200"
            self.logger.info(f"Requesting next page {page} for {slug}")
            yield scrapy.Request(
                next_api,
                callback=self.parse_api,
                meta={"category_slug": slug, "page": page},
                cookies={"BITRIX_SM_CITY_ID": self.CITY_ID},
                dont_filter=True,
                errback=self.errback_httpbin
            )

    def errback_httpbin(self, failure):
        """Обрабатываем ошибки запросов(если такие есть)"""
        self.logger.error(f"Request failed: {failure.request.url} - {failure.value}")
        if failure.check(429):
            self.logger.warning(
                f"429 encountered for {failure.request.url}, consider checking proxy or increasing delay")

    def close_spider(self, spider):
        """Сохраняем все данные в словарь"""
        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(self.processed_items, f, ensure_ascii=False, indent=2)
