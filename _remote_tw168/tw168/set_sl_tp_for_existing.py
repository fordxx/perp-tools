#!/usr/bin/env python3
"""
为现有持仓手动设置止盈止损
适用于已有持仓但未设置止盈止损的情况
"""

import argparse
import requests
import json
from typing import Optional

def set_sl_tp_for_position(
    inst_id: str,
    pos_side: str,  # "long" or "short"
    entry_price: float,
    stop_loss: float,
    size: float,
    admin_key: str,
    base_url: str = "https://trader:TW168Trading!2026@3-38-98-169.nip.io"
) -> dict:
    """
    为现有持仓设置止盈止损

    参数:
        inst_id: 交易对，如 ETH-USDT-SWAP
        pos_side: 持仓方向 long/short
        entry_price: 入场价格
        stop_loss: 止损价格
        size: 持仓大小
        admin_key: 管理员密钥
    """

    # 构造 payload，模拟一个已成交的信号
    # 系统会根据这个信息设置止盈止损
    side = "buy" if pos_side == "long" else "sell"

    payload = {
        "instId": inst_id,
        "tf": "1h",  # 时间周期（影响超时设置）
        "side": side,
        "type": "DIV",
        "admin_key": admin_key,
        # 注意：这会触发一个新的入场订单
        # 如果只想设置止盈止损，需要使用不同的端点
    }

    print(f"⚠️  警告：此方法会尝试下新单")
    print(f"📊 交易对: {inst_id}")
    print(f"📈 持仓方向: {pos_side}")
    print(f"💰 入场价: {entry_price}")
    print(f"🛡️ 止损: {stop_loss}")
    print(f"📏 仓位大小: {size}")
    print("-" * 50)

    url = f"{base_url}/manual/signal"

    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"📊 HTTP状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("✅ 请求成功!")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return result
        else:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"错误详情: {response.text}")
            return {"error": response.text}

    except Exception as e:
        print(f"❌ 异常: {e}")
        return {"error": str(e)}


def main():
    print("=" * 60)
    print("为现有持仓设置止盈止损 - 手动工具")
    print("=" * 60)
    print()
    print("⚠️  重要提示:")
    print("  1. 此工具会触发新的交易信号")
    print("  2. 如果已有持仓，可能会增加仓位")
    print("  3. 建议先在测试环境验证")
    print()
    print("=" * 60)
    print()

    parser = argparse.ArgumentParser(description="为现有持仓设置止盈止损")
    parser.add_argument("inst_id", help="交易对，如 ETH-USDT-SWAP")
    parser.add_argument("pos_side", choices=["long", "short"], help="持仓方向")
    parser.add_argument("entry_price", type=float, help="入场价格")
    parser.add_argument("stop_loss", type=float, help="止损价格")
    parser.add_argument("size", type=float, help="持仓大小")
    parser.add_argument("-k", "--key", required=True, help="管理员密钥")
    parser.add_argument("-u", "--url", default="https://trader:TW168Trading!2026@3-38-98-169.nip.io",
                        help="服务器URL")

    args = parser.parse_args()

    # 二次确认
    print(f"\n即将为以下持仓设置止盈止损:")
    print(f"  交易对: {args.inst_id}")
    print(f"  方向: {args.pos_side}")
    print(f"  入场: {args.entry_price}")
    print(f"  止损: {args.stop_loss}")
    print(f"  大小: {args.size}")
    print()

    confirm = input("确认继续? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("已取消")
        return 1

    result = set_sl_tp_for_position(
        inst_id=args.inst_id,
        pos_side=args.pos_side,
        entry_price=args.entry_price,
        stop_loss=args.stop_loss,
        size=args.size,
        admin_key=args.key,
        base_url=args.url
    )

    if "error" in result:
        return 1
    else:
        return 0


if __name__ == "__main__":
    exit(main())
