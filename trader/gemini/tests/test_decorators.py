import pytest
import asyncio
from aiohttp import ClientError
from ..decorators import with_retry

# Mock exceptions for testing
class MockClientError(ClientError):
    def __init__(self, message="Mock error"):
        self.message = message

    def __str__(self):
        return self.message

# Test fixtures and helper functions
class CallCounter:
    """Helper class to track number of function calls"""
    def __init__(self):
        self.calls = 0
        self.last_delay = 0

async def create_failing_function(num_failures: int, exception_type=MockClientError):
    """Creates a function that fails num_failures times then succeeds"""
    counter = CallCounter()
    
    @with_retry(max_retries=3, base_delay=0.1)
    async def failing_function():
        counter.calls += 1
        if counter.calls <= num_failures:
            raise exception_type()
        return "success"
    
    return failing_function, counter

# Tests
@pytest.mark.asyncio
async def test_successful_first_try():
    """Test that function succeeds on first try"""
    counter = CallCounter()
    
    @with_retry()
    async def success_function():
        counter.calls += 1
        return "success"
    
    result = await success_function()
    assert result == "success"
    assert counter.calls == 1

@pytest.mark.asyncio
async def test_retry_success():
    """Test that function retries and eventually succeeds"""
    failing_function, counter = await create_failing_function(2)
    
    result = await failing_function()
    assert result == "success"
    assert counter.calls == 3  # Failed twice, succeeded on third try

@pytest.mark.asyncio
async def test_max_retries_exceeded():
    """Test that function fails after max retries"""
    failing_function, counter = await create_failing_function(5)
    
    with pytest.raises(MockClientError):
        await failing_function()
    assert counter.calls == 3  # Should have tried 3 times total

@pytest.mark.asyncio
async def test_custom_exceptions():
    """Test that decorator only catches specified exceptions"""
    counter = CallCounter()
    
    @with_retry(exceptions=(ValueError,))
    async def value_error_function():
        counter.calls += 1
        raise KeyError("Should not be caught")
    
    with pytest.raises(KeyError):
        await value_error_function()
    assert counter.calls == 1  # Should only try once since KeyError isn't caught

@pytest.mark.asyncio
async def test_exponential_backoff():
    """Test exponential backoff timing"""
    counter = CallCounter()
    start_time = asyncio.get_event_loop().time()
    
    @with_retry(
        max_retries=3,
        base_delay=0.1,
        exponential_base=2.0
    )
    async def slow_failing_function():
        counter.calls += 1
        counter.last_delay = asyncio.get_event_loop().time() - start_time
        raise MockClientError()
    
    with pytest.raises(MockClientError):
        await slow_failing_function()
    
    # Should have delays of approximately 0.1 and 0.2 seconds between calls
    assert counter.calls == 3
    assert counter.last_delay >= 0.3  # Total time should be at least 0.3s

@pytest.mark.asyncio
async def test_retry_with_different_exceptions():
    """Test handling of different exception types"""
    counter = CallCounter()
    
    @with_retry(exceptions=(ValueError, KeyError))
    async def multi_error_function():
        counter.calls += 1
        if counter.calls == 1:
            raise ValueError("First error")
        if counter.calls == 2:
            raise KeyError("Second error")
        return "success"
    
    result = await multi_error_function()
    assert result == "success"
    assert counter.calls == 3

@pytest.mark.asyncio
async def test_custom_retry_params():
    """Test custom retry parameters"""
    counter = CallCounter()
    
    @with_retry(max_retries=5, base_delay=0.1)
    async def custom_retry_function():
        counter.calls += 1
        if counter.calls < 4:
            raise MockClientError()
        return "success"
    
    result = await custom_retry_function()
    assert result == "success"
    assert counter.calls == 4  # Should succeed on 4th try 