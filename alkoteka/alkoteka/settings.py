# Scrapy settings for alkoteka project
BOT_NAME = "alkoteka"

SPIDER_MODULES = ["alkoteka.spiders"]
NEWSPIDER_MODULE = "alkoteka.spiders"

ADDONS = {}

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Concurrency and throttling settings
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 30.0  # Увеличиваем до 30 секунд

# Enable AutoThrottle for dynamic delay
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 30.0
AUTOTHROTTLE_MAX_DELAY = 600.0  # До 10 минут
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.02  # Ещё ниже
AUTOTHROTTLE_DEBUG = True

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en",
    "Content-Type": "application/json",
}

# Enable or disable downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    "alkoteka.middlewares.AlkotekaDownloaderMiddleware": 543,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
}

# Enable and configure HTTP caching
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [429]
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

# Дополнительные параметры для устойчивости
RETRY_ENABLED = True
RETRY_TIMES = 20  # Увеличиваем до 20
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]
RETRY_BACKOFF = 5