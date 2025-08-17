from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from fake_useragent import UserAgent
from twisted.internet.error import DNSLookupError, TimeoutError
from twisted.web.client import ResponseFailed


class AlkotekaSpiderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        spider.logger.debug(f"Received response for {response.url} with status {response.status}")
        return None

    def process_spider_output(self, response, result, spider):
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        spider.logger.error(f"Spider exception for {response.url}: {exception}")
        return None

    async def process_start(self, start):
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info(f"Spider opened: {spider.name}")


class AlkotekaDownloaderMiddleware:
    def __init__(self):
        self.ua = UserAgent()
        self.max_retries = 20  # Увеличиваем до 20

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        request.headers['User-Agent'] = self.ua.random
        spider.logger.debug(f"Request {request.url} with User-Agent: {request.headers['User-Agent']}")
        # Прокси отключены
        return None

    def process_response(self, request, response, spider):
        if response.status in [429, 500, 502, 503, 504]:
            spider.logger.warning(f"Received {response.status} for {response.url}")
            retries = request.meta.get('retry_times', 0) + 1
            if retries <= self.max_retries:
                retry_after = response.headers.get('Retry-After', 10)
                wait_time = int(retry_after) if isinstance(retry_after, str) else (30 * retries)
                new_request = request.copy()
                new_request.meta['retry_times'] = retries
                new_request.dont_filter = True
                spider.logger.info(
                    f"Retrying {request.url} (attempt {retries}/{self.max_retries}) after {wait_time} seconds")
                return new_request.replace(dont_filter=True, meta={'retry_times': retries},
                                           callback=self._schedule_retry, cb_kwargs={'wait_time': wait_time})
            else:
                spider.logger.error(f"Max retries ({self.max_retries}) reached for {request.url}")
                raise IgnoreRequest(f"Max retries reached for {request.url}")
        return response

    def _schedule_retry(self, request, wait_time):
        from twisted.internet import reactor
        from scrapy.utils.defer import maybe_deferred_to_future
        deferred = maybe_deferred_to_future(reactor.callLater(wait_time, lambda: request))
        return deferred

    def process_exception(self, request, exception, spider):
        if isinstance(exception, (DNSLookupError, TimeoutError, ResponseFailed)):
            retries = request.meta.get('retry_times', 0) + 1
            if retries <= self.max_retries:
                new_request = request.copy()
                new_request.meta['retry_times'] = retries
                new_request.dont_filter = True
                spider.logger.warning(
                    f"Exception {type(exception).__name__} for {request.url}, retrying (attempt {retries}/{self.max_retries})")
                return new_request
            else:
                spider.logger.error(f"Max retries ({self.max_retries}) reached for {request.url}: {exception}")
                raise IgnoreRequest(f"Max retries reached for {request.url}")
        return None

    def spider_opened(self, spider):
        spider.logger.info(f"Spider opened: {spider.name}")
