#!/usr/bin/env python3
"""Demonstration of Duration class features.

This example shows:
- Creating Duration objects
- Arithmetic operations (add, subtract, multiply, divide)
- Comparison operations
- Converting to/from nanoseconds and messages
- Using Duration with timers and clocks
"""

import rclpy
from lwrclpy.duration import Duration


def main():
    print("=== Duration Class Demo ===\n")
    
    # 1. Creating durations
    print("--- Creating Durations ---")
    
    # From seconds and nanoseconds
    d1 = Duration(seconds=5, nanoseconds=500_000_000)  # 5.5 seconds
    print(f"5 seconds + 500ms: {d1}")
    print(f"  nanoseconds: {d1.nanoseconds}")
    
    # From nanoseconds only
    d2 = Duration(nanoseconds=2_500_000_000)  # 2.5 seconds
    print(f"\n2.5 billion ns: {d2}")
    print(f"  nanoseconds: {d2.nanoseconds}")
    
    # Zero duration
    d_zero = Duration()
    print(f"\nZero duration: {d_zero}")
    
    # 2. Arithmetic operations
    print("\n--- Arithmetic Operations ---")
    
    a = Duration(seconds=10)
    b = Duration(seconds=3, nanoseconds=500_000_000)
    
    print(f"a = {a}")
    print(f"b = {b}")
    
    # Addition
    result = a + b
    print(f"\na + b = {result}")
    print(f"  = {result.nanoseconds / 1e9:.1f} seconds")
    
    # Subtraction
    result = a - b
    print(f"\na - b = {result}")
    print(f"  = {result.nanoseconds / 1e9:.1f} seconds")
    
    # Multiplication by scalar
    result = b * 2
    print(f"\nb * 2 = {result}")
    print(f"  = {result.nanoseconds / 1e9:.1f} seconds")
    
    result = 3 * b
    print(f"\n3 * b = {result}")
    print(f"  = {result.nanoseconds / 1e9:.1f} seconds")
    
    # Division by scalar
    result = a / 4
    print(f"\na / 4 = {result}")
    print(f"  = {result.nanoseconds / 1e9:.2f} seconds")
    
    # Division by Duration (returns float ratio)
    ratio = a / b
    print(f"\na / b = {ratio:.4f}")
    
    # 3. Comparison operations
    print("\n--- Comparison Operations ---")
    
    short = Duration(seconds=1)
    medium = Duration(seconds=5)
    long_dur = Duration(seconds=10)
    same = Duration(seconds=5)
    
    print(f"short = {short}")
    print(f"medium = {medium}")
    print(f"long = {long_dur}")
    print(f"same = {same}")
    
    print(f"\nshort < medium: {short < medium}")
    print(f"medium <= same: {medium <= same}")
    print(f"long > medium: {long_dur > medium}")
    print(f"medium >= same: {medium >= same}")
    print(f"medium == same: {medium == same}")
    print(f"short != medium: {short != medium}")
    
    # 4. Negative duration
    print("\n--- Negative Duration ---")
    
    neg = Duration(seconds=-5)
    print(f"Negative: {neg}")
    print(f"  nanoseconds: {neg.nanoseconds}")
    
    # Adding negative
    result = Duration(seconds=10) + neg
    print(f"10s + (-5s) = {result.nanoseconds / 1e9:.0f}s")
    
    # 5. Converting to message
    print("\n--- Message Conversion ---")
    
    d = Duration(seconds=42, nanoseconds=123456789)
    msg = d.to_msg()
    if msg:
        print(f"Original: {d}")
        print(f"Message: sec={msg.sec()}, nanosec={msg.nanosec()}")
    else:
        print("Duration message type not available")
    
    # 6. Hashing (for use in sets/dicts)
    print("\n--- Hashing ---")
    
    d1 = Duration(seconds=5)
    d2 = Duration(seconds=5)
    d3 = Duration(seconds=10)
    
    duration_set = {d1, d2, d3}
    print(f"Set from [5s, 5s, 10s]: {len(duration_set)} unique durations")
    
    duration_dict = {
        Duration(seconds=1): "one second",
        Duration(seconds=60): "one minute",
        Duration(seconds=3600): "one hour",
    }
    print(f"Dict lookup for 60s: '{duration_dict[Duration(seconds=60)]}'")
    
    # 7. Practical usage
    print("\n--- Practical Usage ---")
    
    rclpy.init()
    node = rclpy.create_node("duration_demo")
    
    # Create timer with Duration
    period = Duration(seconds=0, nanoseconds=500_000_000)  # 500ms
    print(f"Timer period: {period.nanoseconds / 1e9:.1f}s")
    
    # Use with clock
    from lwrclpy.clock import Clock
    clock = Clock()
    
    start_time = clock.now()
    print(f"Start time: {start_time}")
    
    target = start_time + period
    print(f"Target time (start + 500ms): {target}")
    
    node.destroy_node()
    rclpy.shutdown()
    
    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
