
#!/usr/bin/env python3

"""检查 ParadexSubkey 的实际 API"""



from paradex_py import ParadexSubkey

import inspect



print("=" * 60)

print("ParadexSubkey 类的所有公开方法:")

print("=" * 60)



methods = [m for m in dir(ParadexSubkey) if not m.startswith('_')]

for method in sorted(methods):

    try:

        attr = getattr(ParadexSubkey, method)

        if callable(attr):

            sig = inspect.signature(attr)

            print(f"\n✅ {method}{sig}")

            

            # 获取文档字符串

            if attr.__doc__:

                doc_lines = attr.__doc__.strip().split('\n')

                if doc_lines:

                    print(f"   ���� {doc_lines[0]}")

    except Exception as e:

        print(f"\n��❌ {method}: {e}")



# 检查 account 对象的方法

print("\n\n" + "=" * 60)

print("如果 client.account 存在，它可能有这些方法:")

print("=" * 60)

print("(需要实际连接后才能查看)")



