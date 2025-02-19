import asyncio
import logging
import platform

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
from proxybroker import Broker

# Set up logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)


async def find_and_show_proxies(limit, results_queue):
    proxies = asyncio.Queue()
    # judges = ["http://azenv.net/", "https://httpbin.org/get?show_env"]
    broker = Broker(queue=proxies, verify_ssl=True, max_conn=500, max_tries=10)
    # broker = Broker(queue=proxies, verify_ssl=True, max_conn=200, max_tries=3)
    found_count = 0

    try:

        async def process_proxies():
            nonlocal found_count
            find_task = asyncio.create_task(broker.find(types=["HTTP", "HTTPS"]))

            while True:
                if found_count >= limit:
                    break

                try:
                    proxy = await asyncio.wait_for(proxies.get(), timeout=30.0)
                    if proxy is None:
                        break

                    print(f"Found proxy: {proxy}")
                    found_count += 1
                    await results_queue.put(f"{proxy.host}:{proxy.port}")

                except asyncio.TimeoutError:
                    logger.info("Timeout waiting for proxy. Checking if find task is done...")
                    if find_task.done():
                        break
                    else:
                        continue
                except Exception as e:
                    logger.error(f"Error processing proxy: {e}")
            await find_task

        await process_proxies()

    except Exception as e:
        logger.exception(f"An error occurred in find_and_show_proxies: {e}")
    finally:
        broker.stop()
        while not proxies.empty():
            proxies.get_nowait()
        logger.info("Broker stopped and queue cleared.")
        await results_queue.put(None)


async def collect_results(results_queue, proxies_list):
    """Collects results from the queue and appends them to the list."""
    while True:
        proxy_str = await results_queue.get()
        if proxy_str is None:
            break
        proxies_list.append(proxy_str)


async def test_proxy(proxy, working_proxies):
    proxy_url = f"http://{proxy}"
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if proxy.types[0] == "HTTP":
                try:
                    async with session.get("http://scholar.google.com/scholar", proxy=proxy_url) as get_response:
                        get_response.raise_for_status()
                        logger.info(f"Successfully fetched Google using HTTP proxy: {proxy}")
                        working_proxies.append(proxy)
                except Exception as e:
                    logger.error(f"HTTP proxy {proxy} failed: {e}")
            else:
                try:
                    async with session.request("CONNECT", "scholar.google.com/scholar:443", proxy=proxy_url) as conn_response:
                        conn_response.raise_for_status()
                    async with session.get("https://scholar.google.com/scholar") as get_response:
                        get_response.raise_for_status()
                        logger.info(f"Successfully fetched Google using CONNECT proxy: {proxy}")
                        working_proxies.append(proxy)
                except Exception as e:
                    logger.error(f"CONNECT proxy {proxy} failed: {e}")

    except aiohttp.ClientProxyConnectionError as e:
        logger.error(f"Proxy connection error for {proxy}: {e}")
    except aiohttp.ClientError as e:
        logger.error(f"Client error for {proxy}: {e}")
    except asyncio.TimeoutError:
        logger.error(f"Timeout error for {proxy}")
    except Exception as e:
        logger.exception(f"Unexpected error testing proxy {proxy}: {e}")


async def main():
    try:
        results_queue = asyncio.Queue()
        proxies_list = []
        working_proxies = []

        find_task = asyncio.create_task(find_and_show_proxies(limit=50, results_queue=results_queue))
        collect_task = asyncio.create_task(collect_results(results_queue, proxies_list))
        await asyncio.gather(find_task, collect_task)

        print(f"\nTotal proxies found: {len(proxies_list)}")
        for proxy_str in proxies_list:
            print(proxy_str)

        test_tasks = [test_proxy(proxy, working_proxies) for proxy in proxies_list]
        await asyncio.gather(*test_tasks)

        print(f"\nWorking proxies: {len(working_proxies)}")
        for proxy in working_proxies:
            print(proxy)

    except Exception as e:
        logger.exception(f"An error occurred within main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
