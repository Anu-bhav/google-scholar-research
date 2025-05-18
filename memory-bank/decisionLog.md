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
