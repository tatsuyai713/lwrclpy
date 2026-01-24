#!/usr/bin/env python3
"""Demonstration of Context management features.

This example shows:
- Creating context with domain_id
- Getting domain ID
- Proper shutdown handling
- try_shutdown() for graceful termination
"""

import rclpy
from lwrclpy.context import Context


def main():
    print("=== Context Management Demo ===\n")
    
    # 1. Default context
    print("--- Default Context ---")
    rclpy.init()
    
    context = rclpy.get_default_context()
    print(f"Context OK: {context.ok()}")
    print(f"Domain ID: {context.get_domain_id()}")
    
    node = rclpy.create_node("default_context_node")
    print(f"Created node: {node.get_name()}")
    
    node.destroy_node()
    rclpy.shutdown()
    print(f"After shutdown, context OK: {context.ok()}")
    print()
    
    # 2. Custom domain ID
    print("--- Custom Domain ID ---")
    
    custom_context = Context()
    custom_context.init(domain_id=42)
    
    print(f"Custom context OK: {custom_context.ok()}")
    print(f"Custom domain ID: {custom_context.get_domain_id()}")
    
    custom_context.shutdown()
    print(f"After shutdown: {custom_context.ok()}")
    print()
    
    # 3. try_shutdown (graceful)
    print("--- try_shutdown ---")
    
    context2 = Context()
    context2.init()
    
    print(f"Before try_shutdown: {context2.ok()}")
    
    # try_shutdown returns True if shutdown happened, False if already shut down
    result1 = context2.try_shutdown()
    print(f"First try_shutdown returned: {result1}")
    
    result2 = context2.try_shutdown()
    print(f"Second try_shutdown returned: {result2} (already shut down)")
    print()
    
    # 4. Multiple contexts (isolated communication)
    print("--- Multiple Isolated Contexts ---")
    
    ctx_a = Context()
    ctx_a.init(domain_id=10)
    
    ctx_b = Context()
    ctx_b.init(domain_id=20)
    
    print(f"Context A domain: {ctx_a.get_domain_id()}")
    print(f"Context B domain: {ctx_b.get_domain_id()}")
    print("Nodes in different domains cannot communicate directly")
    
    ctx_a.shutdown()
    ctx_b.shutdown()
    print()
    
    # 5. Demonstrating atexit behavior
    print("--- Automatic Cleanup ---")
    print("lwrclpy registers atexit handlers for automatic cleanup")
    print("When the Python process exits, all contexts are automatically shut down")
    print()
    
    # 6. Proper shutdown pattern
    print("--- Recommended Shutdown Pattern ---")
    print("""
    # Always use try/finally for proper cleanup:
    
    try:
        rclpy.init()
        node = rclpy.create_node('my_node')
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.destroy_node()
        rclpy.shutdown()
    """)
    
    print("=== Demo Complete ===")


if __name__ == "__main__":
    main()
