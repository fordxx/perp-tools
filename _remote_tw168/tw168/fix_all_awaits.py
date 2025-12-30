#!/usr/bin/env python3
"""
Fix all missing awaits for Lighter adapter async methods
"""
import re

# Read the file
with open("app/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# List of exchange methods that need await
exchange_methods = [
    "place_order",
    "place_algo_order",
    "get_order",
    "cancel_order",
    "get_open_orders",
    "get_position",
    "get_last_price",
    "get_instrument_info",
]

# Pattern to match exchange method calls without await
patterns = []
for method in exchange_methods:
    # Match: exchange.method( but not: await exchange.method(
    pattern = r'(?<!await\s)(?<!await\s\s)(?<!await\s\s\s)(?<!await\s\s\s\s)(exchange\.' + method + r'\()'
    patterns.append((pattern, f"await \\1"))

# Apply replacements
modified = content
changes = 0
for pattern, replacement in patterns:
    new_content = re.sub(pattern, replacement, modified)
    if new_content != modified:
        count = len(re.findall(pattern, modified))
        changes += count
        # Extract method name from pattern
        method_name = pattern.split('.')[1].split(r'\(')[0]
        print(f"Added await to {count} calls of '{method_name}'")
        modified = new_content

if changes > 0:
    with open("app/main.py", "w", encoding="utf-8") as f:
        f.write(modified)
    print(f"\nTotal: Added {changes} await keywords")
else:
    print("No changes needed")
