"""
Fee Comparison Demo - 交易所费率对比演示

展示：
1. 所有交易所的 Maker/Taker 费率
2. 费率分级（S/A/B/C）
3. 不同交易所组合的套利成本对比
4. 负费率的收益优势
"""

import logging
from perpbot.scoring import FeeModel


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """打印分隔线"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def demo_1_fee_overview():
    """Demo 1: 费率总览"""
    print_section("Demo 1: 所有交易所费率总览")

    fee_model = FeeModel()

    # 按等级分组
    tiers = {
        "S 级（负费）": ["grvt", "extended"],
        "A 级（零费）": ["paradex"],
        "B 级（低费）": ["edgex", "aster", "hyperliquid"],
        "C 级（中费）": ["backpack", "bybit"],
        "行情参考": ["binance", "okx"],
    }

    for tier_name, exchanges in tiers.items():
        print(f"\n--- {tier_name} ---")
        print(f"{'交易所':<15} | {'Maker (bps)':<12} | {'Taker (bps)':<12} | {'费率优势'}")
        print("-" * 80)

        for exchange in exchanges:
            maker_fee = fee_model.get_fee(exchange, "BTC-USDT", "buy", "maker")
            taker_fee = fee_model.get_fee(exchange, "BTC-USDT", "buy", "taker")

            maker_bps = maker_fee * 10000
            taker_bps = taker_fee * 10000

            # 判断优势
            if maker_fee < 0:
                advantage = "✅ Maker 返佣"
            elif maker_fee == 0:
                advantage = "✅ Maker 免费"
            elif maker_fee < 0.0001:
                advantage = "✅ Maker 极低"
            else:
                advantage = "⚠️ 中等费率"

            print(f"{exchange:<15} | {maker_bps:>+10.2f} | {taker_bps:>+10.2f} | {advantage}")

    print("\n✅ Demo 1 完成：费率总览")


def demo_2_arbitrage_cost_comparison():
    """Demo 2: 套利成本对比"""
    print_section("Demo 2: 不同交易所组合的套利成本对比")

    fee_model = FeeModel()
    notional = 10000.0  # 10000 USDT

    # 定义几种典型的套利组合
    pairs = [
        # S 级配对
        ("grvt", "paradex", "S+A 级：负费+零费（最优）"),
        ("extended", "paradex", "S+A 级：零费+零费"),

        # A 级配对
        ("paradex", "edgex", "A+B 级：零费+低费"),
        ("paradex", "aster", "A+B 级：零费+极低费"),

        # B 级配对
        ("edgex", "aster", "B+B 级：低费+极低费"),
        ("hyperliquid", "edgex", "B+B 级：负费+低费"),

        # C 级配对（对比基准）
        ("binance", "okx", "传统交易所（仅供参考）"),
    ]

    print(f"套利金额: {notional:.0f} USDT\n")
    print(f"{'组合':<35} | {'Buy Maker':<10} | {'Sell Maker':<10} | {'总费用':<10} | {'ROI影响':<10}")
    print("-" * 100)

    for buy_exchange, sell_exchange, desc in pairs:
        # 假设都用 Maker 订单（最优情况）
        buy_fee = notional * fee_model.get_fee(buy_exchange, "BTC-USDT", "buy", "maker")
        sell_fee = notional * fee_model.get_fee(sell_exchange, "BTC-USDT", "sell", "maker")
        total_fee = buy_fee + sell_fee

        roi_impact = (total_fee / notional) * 100

        print(f"{desc:<35} | {buy_fee:>+9.4f} | {sell_fee:>+9.4f} | {total_fee:>+9.4f} | {roi_impact:>+8.3f}%")

    print("\n✅ Demo 2 完成：套利成本对比")


def demo_3_maker_vs_taker():
    """Demo 3: Maker vs Taker 成本差异"""
    print_section("Demo 3: Maker vs Taker 成本差异")

    fee_model = FeeModel()
    notional = 10000.0

    print(f"订单金额: {notional:.0f} USDT\n")
    print(f"{'交易所':<15} | {'Maker 成本':<12} | {'Taker 成本':<12} | {'节省':<10} | {'节省率'}")
    print("-" * 80)

    exchanges = ["grvt", "extended", "paradex", "edgex", "aster", "hyperliquid", "backpack", "binance"]

    for exchange in exchanges:
        maker_cost = notional * fee_model.get_fee(exchange, "BTC-USDT", "buy", "maker")
        taker_cost = notional * fee_model.get_fee(exchange, "BTC-USDT", "buy", "taker")

        saving = taker_cost - maker_cost
        saving_pct = (saving / taker_cost * 100) if taker_cost != 0 else 0

        # 特殊标记
        if maker_cost < 0:
            note = " 🔥 返佣"
        elif saving_pct > 80:
            note = " ✅ 巨大优势"
        elif saving_pct > 50:
            note = " ✅ 显著优势"
        else:
            note = ""

        print(f"{exchange:<15} | {maker_cost:>+10.4f} | {taker_cost:>+10.4f} | {saving:>+8.4f} | {saving_pct:>6.1f}%{note}")

    print("\n✅ Demo 3 完成：Maker vs Taker 成本差异")


def demo_4_negative_fee_revenue():
    """Demo 4: 负费率收益演示"""
    print_section("Demo 4: 负费率收益演示（刷量返现）")

    fee_model = FeeModel()

    # 测试不同交易量下的负费收益
    volumes = [10000, 50000, 100000, 500000, 1000000]  # USDT

    print("负费率交易所的刷量收益计算\n")

    negative_fee_exchanges = ["grvt", "hyperliquid"]

    for exchange in negative_fee_exchanges:
        maker_fee = fee_model.get_fee(exchange, "BTC-USDT", "buy", "maker")

        print(f"\n--- {exchange.upper()} (Maker: {maker_fee*10000:.4f} bps) ---")
        print(f"{'交易量 (USDT)':<20} | {'Maker 收益':<15} | {'月化收益 (30x)':<15}")
        print("-" * 60)

        for volume in volumes:
            # 负费率 = 收益
            revenue = abs(volume * maker_fee) if maker_fee < 0 else 0
            monthly_revenue = revenue * 30  # 假设每天刷一次

            print(f"{volume:>18,} | {revenue:>+13.4f} | {monthly_revenue:>+13.2f}")

    print("\n✅ Demo 4 完成：负费率收益演示")


def demo_5_hybrid_mode_optimization():
    """Demo 5: HYBRID 模式费用优化"""
    print_section("Demo 5: HYBRID 模式费用优化（对冲腿 Taker + 返佣腿 Maker）")

    fee_model = FeeModel()
    notional = 10000.0

    print(f"场景：跨交易所套利，金额 {notional:.0f} USDT\n")

    # 定义几种组合
    scenarios = [
        # 场景1: 传统方案（双边 Taker）
        {
            "name": "传统方案（双边 Taker）",
            "buy_exchange": "binance",
            "sell_exchange": "okx",
            "buy_type": "taker",
            "sell_type": "taker",
        },
        # 场景2: HYBRID 优化（Binance Taker + GRVT Maker）
        {
            "name": "HYBRID 优化（Binance Taker + GRVT Maker）",
            "buy_exchange": "binance",
            "sell_exchange": "grvt",
            "buy_type": "taker",
            "sell_type": "maker",
        },
        # 场景3: 最优方案（Paradex Taker + GRVT Maker）
        {
            "name": "最优方案（Paradex Taker + GRVT Maker）",
            "buy_exchange": "paradex",
            "sell_exchange": "grvt",
            "buy_type": "taker",
            "sell_type": "maker",
        },
        # 场景4: 极致优化（Paradex Taker + Extended Maker）
        {
            "name": "极致优化（Paradex Taker + Extended Maker）",
            "buy_exchange": "paradex",
            "sell_exchange": "extended",
            "buy_type": "taker",
            "sell_type": "maker",
        },
    ]

    print(f"{'方案':<45} | {'开仓费用':<12} | {'平仓费用':<12} | {'总费用':<10} | {'相比传统'}")
    print("-" * 100)

    baseline_cost = None

    for scenario in scenarios:
        buy_cost = notional * fee_model.get_fee(
            scenario["buy_exchange"],
            "BTC-USDT",
            "buy",
            scenario["buy_type"]
        )

        sell_cost = notional * fee_model.get_fee(
            scenario["sell_exchange"],
            "BTC-USDT",
            "sell",
            scenario["sell_type"]
        )

        total_cost = buy_cost + sell_cost

        if baseline_cost is None:
            baseline_cost = total_cost
            comparison = "基准"
        else:
            saving = baseline_cost - total_cost
            saving_pct = (saving / baseline_cost * 100) if baseline_cost != 0 else 0
            comparison = f"节省 {saving:+.4f} ({saving_pct:+.1f}%)"

        print(f"{scenario['name']:<45} | {buy_cost:>+10.4f} | {sell_cost:>+10.4f} | {total_cost:>+8.4f} | {comparison}")

    print("\n✅ Demo 5 完成：HYBRID 模式费用优化")


def main():
    """运行所有演示"""
    print_section("交易所费率对比完整演示")

    demos = [
        demo_1_fee_overview,
        demo_2_arbitrage_cost_comparison,
        demo_3_maker_vs_taker,
        demo_4_negative_fee_revenue,
        demo_5_hybrid_mode_optimization,
    ]

    for demo in demos:
        demo()

    print_section("所有演示完成！")

    print("\n关键结论：")
    print("✅ 1. S 级交易所（GRVT/EXTENDED）提供负费率，刷量即赚钱")
    print("✅ 2. A 级交易所（Paradex）零手续费，最适合做对冲腿")
    print("✅ 3. HYBRID 模式（Taker+Maker）相比双边 Taker 可节省 70%+ 费用")
    print("✅ 4. 最优组合：Paradex (Taker) + GRVT (Maker) → 负总费用！")
    print("✅ 5. 刷量优先级：GRVT > EXTENDED > Paradex > EdgeX > Aster")


if __name__ == "__main__":
    main()
