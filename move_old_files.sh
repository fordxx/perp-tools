#!/bin/bash

# 移动旧测试文件
echo "📦 移动旧测试文件到 archive/old_tests/"
mv test_okx.py test_extended.py test_paradex.py test_hyperliquid.py \
   test_bitget.py test_backpack.py test_edgex.py test_grvt.py \
   test_lighter.py test_aster.py test_all_exchanges.py \
   test_live_exchanges_simple.py test_websocket_feeds.py test_ws_simple.py \
   test_paradex_websocket.py test_paradex_limit_order.py test_tp_sl_complete.py \
   test_live_exchange_functions.py test_remaining_features.py \
   test_close_position.py test_position_aggregator.py test_exchange_integration.py \
   validate_perpbot_v2.py archive/old_tests/ 2>/dev/null || true

echo "✅ 已移动 $(ls archive/old_tests/ | wc -l) 个旧测试文件"

# 移动旧文档文件
echo ""
echo "📄 移动旧文档文件到 archive/old_docs/"
mv QUICK_START_TESTNET.md TESTNET_CONNECTION_GUIDE.md TESTNET_DOCS_INDEX.md \
   TESTNET_READY_REPORT.md EXTENDED_TEST_PLAN.md LIGHTER_TEST_PLAN.md \
   MANUAL_TESTING_GUIDE.md EXCHANGE_TESTING_STATUS.md EXCHANGE_MOCK_MODE_SUMMARY.md \
   UNIT_TESTING_SUMMARY.md PERFORMANCE_TESTING_SUMMARY.md PARADEX_TEST_SUMMARY.md \
   archive/old_docs/ 2>/dev/null || true

echo "✅ 已移动 $(ls archive/old_docs/ | wc -l) 个旧文档文件"

echo ""
echo "✅ 归档完成！"
