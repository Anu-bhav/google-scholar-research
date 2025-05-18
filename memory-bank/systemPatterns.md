# System Patterns _Optional_

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.
2025-05-17 13:42:00 - Log of updates made.

-

## Coding Patterns

-

## Architectural Patterns

-

## Testing Patterns

-
- **Async Fixture Pattern for `pytest-asyncio` (Discovered 2025-05-17):**

  - **Context:** When using `pytest-asyncio` in the project's `uv` environment, standard `async def` fixtures using `yield` did not correctly inject the yielded value into tests. Tests received the async generator object itself.
  - **Pattern:**

    1. Define `async def` fixtures to `return` the required object (e.g., a `DataHandler` instance after its async setup).
    2. Test functions that use these fixtures must also be `async def` and decorated with `@pytest.mark.asyncio`.
    3. Inside the test function, the fixture parameter (which is a coroutine) must be `await`ed to obtain the actual fixture object.

       ```python
       @pytest.fixture
       async def my_async_fixture():
           obj = MyObject()
           await obj.async_setup() # Perform async setup
           return obj

       @pytest.mark.asyncio
       async def test_my_feature(my_async_fixture):
           actual_obj = await my_async_fixture # Await to get the object
           # Now use actual_obj
           assert await actual_obj.some_method()
       ```

  - **Teardown:** Teardown logic that would normally come after `yield` must be handled by other means (e.g., context managers within the fixture like `tempfile.TemporaryDirectory`, or pytest's `tmp_path` for file-based resources, or `request.addfinalizer`).
  - **Rationale:** This pattern ensures reliable injection of async fixture resources in the observed test environment.
