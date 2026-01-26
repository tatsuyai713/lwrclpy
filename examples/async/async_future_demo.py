#!/usr/bin/env python3
"""Demonstration of asyncio integration with lwrclpy Future.

This example shows:
- Using Future with async/await
- Adding callbacks to futures
- Combining with asyncio event loop
- Service client with async pattern
"""

import asyncio
import rclpy
from lwrclpy.future import Future
from std_srvs.srv import SetBool


async def future_basics():
    """Demonstrate basic Future functionality."""
    print("=== Future Basics ===\n")
    
    # Create a future
    future = Future()
    
    print(f"Future created: done={future.done()}")
    
    # Add a callback
    results = []
    
    def on_done(fut):
        results.append(f"Callback received result: {fut.result()}")
    
    future.add_done_callback(on_done)
    
    # Set result in a background task
    async def set_result_later():
        await asyncio.sleep(0.5)
        future.set_result("Hello from the future!")
    
    task = asyncio.create_task(set_result_later())
    
    # Wait for the future using await
    print("Awaiting future...")
    result = await future
    
    print(f"Future result: {result}")
    print(f"Future done: {future.done()}")
    print(f"Callback results: {results}")
    
    await task
    print()


async def future_exception():
    """Demonstrate Future exception handling."""
    print("=== Future Exception Handling ===\n")
    
    future = Future()
    
    async def set_exception_later():
        await asyncio.sleep(0.3)
        future.set_exception(ValueError("Something went wrong!"))
    
    task = asyncio.create_task(set_exception_later())
    
    print("Awaiting future that will fail...")
    try:
        result = await future
    except ValueError as e:
        print(f"Caught expected exception: {e}")
    
    print(f"Future has exception: {future.exception() is not None}")
    
    await task
    print()


async def future_cancel():
    """Demonstrate Future cancellation."""
    print("=== Future Cancellation ===\n")
    
    future = Future()
    
    print(f"Before cancel: cancelled={future.cancelled()}")
    
    future.cancel()
    
    print(f"After cancel: cancelled={future.cancelled()}")
    
    # Trying to set result after cancel should fail silently
    # or raise InvalidStateError in strict implementations
    try:
        future.set_result("This won't work")
    except Exception as e:
        print(f"Setting result after cancel raised: {e}")
    
    print()


async def service_client_async_example():
    """Demonstrate async service client pattern."""
    print("=== Async Service Client Pattern ===\n")
    print("(This example shows the pattern - actual service may not be available)")
    
    rclpy.init()
    node = rclpy.create_node("async_client_demo")
    
    # Create a simulated future for demonstration
    future = Future()
    
    # Simulate async service call
    async def simulate_service_call():
        print("Simulating service call...")
        await asyncio.sleep(0.5)
        
        # Create a mock response
        class MockResponse:
            def __init__(self):
                self._success = True
                self._message = "Service completed successfully"
            
            def success(self):
                return self._success
            
            def message(self):
                return self._message
        
        future.set_result(MockResponse())
    
    # Start the simulated call
    task = asyncio.create_task(simulate_service_call())
    
    # Wait for the result
    response = await future
    print(f"Response success: {response.success()}")
    print(f"Response message: {response.message()}")
    
    await task
    
    node.destroy_node()
    rclpy.shutdown()
    print()


async def multiple_futures():
    """Demonstrate waiting for multiple futures."""
    print("=== Multiple Futures ===\n")
    
    futures = [Future() for _ in range(3)]
    
    # Set results at different times
    async def set_results():
        for i, future in enumerate(futures):
            await asyncio.sleep(0.2)
            future.set_result(f"Result {i}")
            print(f"  Set result for future {i}")
    
    task = asyncio.create_task(set_results())
    
    print("Waiting for all futures...")
    
    # Wait for all futures
    results = []
    for i, future in enumerate(futures):
        result = await future
        results.append(result)
        print(f"  Future {i} completed: {result}")
    
    await task
    
    print(f"All results: {results}")
    print()


async def main():
    """Run all async demonstrations."""
    print("=" * 50)
    print("  Async/Await and Future Demo")
    print("=" * 50)
    print()
    
    await future_basics()
    await future_exception()
    await future_cancel()
    await multiple_futures()
    await service_client_async_example()
    
    print("=" * 50)
    print("  Demo Complete")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
