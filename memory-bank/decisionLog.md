# Decision Log

This file records architectural and implementation decisions using a list format.
2025-05-17 13:41:54 - Log of updates made.

-

## Decision

-

## Rationale

-

## Implementation Details

- ***
- ***

## Decision

[2025-05-18 16:12:00] - Extended proxy usage in `Fetcher.scrape_pdf_link`.

## Rationale

To ensure consistent network behavior and benefit from proxy rotation/management for all external calls, the `scrape_pdf_link` method was modified. Previously, it made direct requests to Unpaywall and publisher sites.

## Implementation Details

- The Unpaywall API request within `scrape_pdf_link` now uses `self.proxy_manager.get_proxy()` and includes retry logic with proxy success/failure reporting.
- The subsequent request to the publisher's page (obtained from Unpaywall's `doi_url`) is now made using `await self.fetch_page(paper_url)`. The `fetch_page` method already incorporates the proxy manager and its associated logic (sticky proxy, retries, CAPTCHA handling).
- Corrected type hint for `request_args_unpaywall` to `Dict[str, Any]` and ensured `Any` is imported from `typing`.
- Ensured `timeout` for `aiohttp.ClientSession.get` is passed as a separate keyword argument, not as part of the `**request_args_unpaywall` dictionary, to resolve Pylance errors.
- ***

## Decision

[2025-05-18 16:00:00] - Modified `ProxyManager` to use a "sticky" proxy strategy.

## Rationale

The previous strategy of selecting a random proxy for each request could lead to rapid IP cycling and potentially quicker blacklisting or CAPTCHA triggers. A "sticky" proxy strategy, where the same IP is used until it encounters an issue (like being blacklisted), aims to reduce the frequency of IP changes, potentially improving stability and reducing the likelihood of triggering anti-bot measures.

## Implementation Details

- Added `self.current_proxy: Optional[str]` to `ProxyManager` to store the active proxy.
- Renamed `get_random_proxy()` to `get_proxy()`.
- `get_proxy()` logic:
  - Returns `self.current_proxy` if it's set and not blacklisted.
  - If `self.current_proxy` is invalid or becomes blacklisted, it selects a new proxy from the available pool, sets it as `self.current_proxy`, and returns it.
- `remove_proxy(proxy)` now sets `self.current_proxy` to `None` if the blacklisted proxy was the current one.
- `Fetcher` was updated to call `self.proxy_manager.get_proxy()` instead of `get_random_proxy()`.

## Decision

[2025-05-17 16:45:00] - Adopted a specific pattern for `pytest-asyncio` fixtures due to issues with `yield`.

## Rationale

Standard `async def` fixtures using `yield` were not correctly injecting the yielded value into tests (tests received the generator object). It was discovered that `async def` fixtures that `return` a value, when `await`ed by the test function, work correctly in the current `uv` + `pytest` + `pytest-asyncio` environment.

## Implementation Details

- `async def` fixtures should `return` the fixture object (e.g., a `DataHandler` instance).
- Test functions using such fixtures must be `async def`, decorated with `@pytest.mark.asyncio`.
- Inside the test function, the fixture parameter (which will be a coroutine) must be `await`ed to get the actual fixture object.
  Example:

  ```python
  @pytest.fixture
  async def my_fixture():
      obj = MyObject()
      await obj.async_setup()
      return obj

  @pytest.mark.asyncio
  async def test_using_fixture(my_fixture):
      actual_obj = await my_fixture
      await actual_obj.do_work()
  ```

- This pattern was applied to `test_data_handler.py`.
- Teardown for such fixtures must be managed by means that don't rely on code after a `yield` (e.g., context managers like `tempfile.TemporaryDirectory` or `pytest`'s `addfinalizer`). In the `DataHandler` case, `tmp_path` handles teardown.
