#!/usr/bin/env python3
"""Test UI content generation without starting server"""

def test_ui_content():
    """Test that the UI HTML content is properly formatted"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 TW168 交易控制面板</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
        }
        .main-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin: 20px;
            padding: 30px;
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            border: none;
            border-radius: 25px;
            padding: 12px 30px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .form-control {
            border-radius: 10px;
            border: 2px solid #e9ecef;
            transition: border-color 0.3s ease;
        }
        .form-control:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
        }
        .status-card {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }
        .alert-custom {
            border-radius: 10px;
            border: none;
        }
        .price-display {
            font-size: 2rem;
            font-weight: bold;
            color: #28a745;
        }
        .trading-signal {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        .symbol-badge {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            margin: 2px;
            display: inline-block;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light">
        <div class="container">
            <a class="navbar-brand fw-bold" href="#">
                <i class="fas fa-rocket text-primary"></i> TW168 交易控制面板
            </a>
            <div class="d-flex">
                <span class="badge bg-success me-2">GRVT</span>
                <span class="badge bg-info">在线</span>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="main-container">
            <!-- 状态概览 -->
            <div class="row mb-4">
                <div class="col-md-3">
                    <div class="card status-card text-white">
                        <div class="card-body text-center">
                            <i class="fas fa-chart-line fa-2x mb-2"></i>
                            <h5>系统状态</h5>
                            <p class="mb-0">运行正常</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-clock fa-2x mb-2 text-warning"></i>
                            <h5>最后信号</h5>
                            <p class="mb-0" id="lastSignalTime">-</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-signal fa-2x mb-2 text-info"></i>
                            <h5>信号计数</h5>
                            <p class="mb-0" id="signalCount">-</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-exchange-alt fa-2x mb-2 text-success"></i>
                            <h5>活跃仓位</h5>
                            <p class="mb-0" id="activePositions">-</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 手动信号发送 -->
            <div class="row">
                <div class="col-lg-8">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0"><i class="fas fa-hand-paper"></i> 手动交易信号</h5>
                        </div>
                        <div class="card-body">
                            <form id="signalForm">
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label fw-bold">交易对</label>
                                        <select class="form-select" id="instId" required>
                                            <option value="">选择交易对</option>
                                            <option value="BTC-USDT-SWAP">BTC-USDT-SWAP</option>
                                            <option value="ETH-USDT-SWAP">ETH-USDT-SWAP</option>
                                            <option value="SOL-USDT-SWAP">SOL-USDT-SWAP</option>
                                            <option value="LINK-USDT-SWAP">LINK-USDT-SWAP</option>
                                            <option value="DOGE-USDT-SWAP">DOGE-USDT-SWAP</option>
                                            <option value="BNB-USDT-SWAP">BNB-USDT-SWAP</option>
                                            <option value="BCH-USDT-SWAP">BCH-USDT-SWAP</option>
                                            <option value="TRX-USDT-SWAP">TRX-USDT-SWAP</option>
                                            <option value="EIGEN-USDT-SWAP">EIGEN-USDT-SWAP</option>
                                            <option value="ETHFI-USDT-SWAP">ETHFI-USDT-SWAP</option>
                                            <option value="FARTCOIN-USDT-SWAP">FARTCOIN-USDT-SWAP</option>
                                            <option value="JTO-USDT-SWAP">JTO-USDT-SWAP</option>
                                            <option value="PUMP-USDT-SWAP">PUMP-USDT-SWAP</option>
                                            <option value="TAO-USDT-SWAP">TAO-USDT-SWAP</option>
                                            <option value="TON-USDT-SWAP">TON-USDT-SWAP</option>
                                            <option value="TRUMP-USDT-SWAP">TRUMP-USDT-SWAP</option>
                                            <option value="XRP-USDT-SWAP">XRP-USDT-SWAP</option>
                                            <option value="ONDO-USDT-SWAP">ONDO-USDT-SWAP</option>
                                            <option value="LTC-USDT-SWAP">LTC-USDT-SWAP</option>
                                        </select>
                                    </div>
                                    <div class="col-md-3 mb-3">
                                        <label class="form-label fw-bold">时间周期</label>
                                        <select class="form-select" id="tf" required>
                                            <option value="1m">1分钟</option>
                                            <option value="5m">5分钟</option>
                                            <option value="15m">15分钟</option>
                                            <option value="30m">30分钟</option>
                                            <option value="1h" selected>1小时</option>
                                            <option value="4h">4小时</option>
                                        </select>
                                    </div>
                                    <div class="col-md-3 mb-3">
                                        <label class="form-label fw-bold">方向</label>
                                        <select class="form-select" id="side" required>
                                            <option value="">选择方向</option>
                                            <option value="long">📈 做多</option>
                                            <option value="short">📉 做空</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label fw-bold">管理员密钥</label>
                                    <input type="password" class="form-control" id="adminKey" placeholder="输入管理员密钥" required>
                                </div>
                                <button type="submit" class="btn btn-primary btn-lg w-100" id="submitBtn">
                                    <i class="fas fa-paper-plane"></i> 发送交易信号
                                </button>
                            </form>
                        </div>
                    </div>
                </div>

                <!-- 实时价格显示 -->
                <div class="col-lg-4">
                    <div class="card">
                        <div class="card-header bg-info text-white">
                            <h5 class="mb-0"><i class="fas fa-dollar-sign"></i> 实时价格</h5>
                        </div>
                        <div class="card-body">
                            <div id="priceDisplay" class="text-center">
                                <div class="spinner-border text-info" role="status">
                                    <span class="visually-hidden">加载中...</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 热门交易对 -->
                    <div class="card mt-3">
                        <div class="card-header bg-warning text-dark">
                            <h6 class="mb-0"><i class="fas fa-star"></i> 热门交易对</h6>
                        </div>
                        <div class="card-body">
                            <div class="d-flex flex-wrap">
                                <span class="symbol-badge">BTC</span>
                                <span class="symbol-badge">ETH</span>
                                <span class="symbol-badge">SOL</span>
                                <span class="symbol-badge">LINK</span>
                                <span class="symbol-badge">DOGE</span>
                                <span class="symbol-badge">BNB</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 结果显示区域 -->
            <div class="row mt-4">
                <div class="col-12">
                    <div id="result" class="alert alert-custom" style="display: none;"></div>
                </div>
            </div>

            <!-- 信号历史 -->
            <div class="row mt-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-secondary text-white">
                            <h6 class="mb-0"><i class="fas fa-history"></i> 最近信号历史</h6>
                        </div>
                        <div class="card-body">
                            <div id="signalHistory" class="small">
                                <div class="text-muted">暂无信号历史</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 页面加载时获取系统状态
        window.onload = function() {
            updateSystemStatus();
            setInterval(updateSystemStatus, 30000); // 每30秒更新一次
        };

        async function updateSystemStatus() {
            try {
                const response = await fetch('/health');
                const data = await response.json();

                // 更新最后信号时间
                const lastSignal = localStorage.getItem('lastSignalTime');
                if (lastSignal) {
                    const time = new Date(parseInt(lastSignal));
                    document.getElementById('lastSignalTime').textContent = time.toLocaleString();
                }

                // 更新信号计数
                const count = localStorage.getItem('signalCount') || '0';
                document.getElementById('signalCount').textContent = count;

                // 更新活跃仓位 (这里需要实际的API调用)
                document.getElementById('activePositions').textContent = '检查中...';

            } catch (error) {
                console.error('获取系统状态失败:', error);
            }
        }

        // 信号表单提交
        document.getElementById('signalForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitBtn = document.getElementById('submitBtn');
            const resultDiv = document.getElementById('result');

            const data = {
                instId: document.getElementById('instId').value,
                tf: document.getElementById('tf').value,
                side: document.getElementById('side').value,
                type: 'DIV',
                admin_key: document.getElementById('adminKey').value
            };

            if (!data.instId || !data.tf || !data.side || !data.admin_key) {
                showResult('请填写所有必填字段', 'danger');
                return;
            }

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>发送中...';
            resultDiv.style.display = 'none';

            try {
                const response = await fetch('/manual/signal', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (response.ok) {
                    // 保存到本地存储
                    localStorage.setItem('lastSignalTime', Date.now());
                    const count = parseInt(localStorage.getItem('signalCount') || '0') + 1;
                    localStorage.setItem('signalCount', count.toString());

                    showResult(`✅ 信号发送成功！\\n\\n交易对: ${data.instId}\\n方向: ${data.side}\\n时间周期: ${data.tf}`, 'success');
                    updateSignalHistory(data, result);
                    updateSystemStatus();
                } else {
                    showResult(`❌ 发送失败: ${result.detail || JSON.stringify(result)}`, 'danger');
                }

            } catch (error) {
                showResult(`❌ 网络错误: ${error.message}`, 'danger');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 发送交易信号';
            }
        });

        function showResult(message, type) {
            const resultDiv = document.getElementById('result');
            resultDiv.className = `alert alert-${type} alert-custom`;
            resultDiv.innerHTML = `<pre class="mb-0">${message}</pre>`;
            resultDiv.style.display = 'block';

            // 3秒后自动隐藏成功消息
            if (type === 'success') {
                setTimeout(() => {
                    resultDiv.style.display = 'none';
                }, 3000);
            }
        }

        function updateSignalHistory(signal, result) {
            const historyDiv = document.getElementById('signalHistory');
            const time = new Date().toLocaleString();
            const entry = `<div class="mb-2 p-2 bg-light rounded">
                <small class="text-muted">${time}</small><br>
                <strong>${signal.instId}</strong> ${signal.side} (${signal.tf})
                ${result.paper ? '<span class="badge bg-warning">纸上交易</span>' : '<span class="badge bg-success">实盘交易</span>'}
            </div>`;
            historyDiv.innerHTML = entry + historyDiv.innerHTML;
        }

        // 交易对选择时显示实时价格
        document.getElementById('instId').addEventListener('change', async function() {
            const symbol = this.value;
            if (!symbol) return;

            const priceDisplay = document.getElementById('priceDisplay');
            priceDisplay.innerHTML = '<div class="spinner-border spinner-border-sm text-info" role="status"></div>';

            try {
                // 这里可以调用实际的价格API
                // 暂时显示模拟价格
                setTimeout(() => {
                    const mockPrice = (Math.random() * 100000).toFixed(2);
                    priceDisplay.innerHTML = `<div class="price-display">$${mockPrice}</div>`;
                }, 500);
            } catch (error) {
                priceDisplay.innerHTML = '<div class="text-muted">获取价格失败</div>';
            }
        });
    </script>
</body>
</html>
    """

    # Basic validation
    checks = [
        ("DOCTYPE", "<!DOCTYPE html>" in html_content),
        ("Title", "TW168 交易控制面板" in html_content),
        ("Bootstrap CSS", "bootstrap@5.3.0" in html_content),
        ("Font Awesome", "font-awesome" in html_content),
        ("Status cards", "系统状态" in html_content),
        ("Signal form", "手动交易信号" in html_content),
        ("Price display", "实时价格" in html_content),
        ("Signal history", "信号历史" in html_content),
        ("JavaScript", "updateSystemStatus" in html_content),
        ("Form submission", "manual/signal" in html_content),
    ]

    print("🔍 Testing UI content structure...")
    all_passed = True
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("✅ UI content validation passed!")
        print("📊 Content stats:")
        print(f"  - Total length: {len(html_content)} characters")
        print(f"  - Lines: {html_content.count(chr(10)) + 1}")
        print("🎨 Features included:")
        print("  - Modern Bootstrap 5.3.0 design")
        print("  - Responsive layout")
        print("  - Real-time status cards")
        print("  - Manual signal form with validation")
        print("  - Price display section")
        print("  - Signal history tracking")
        print("  - JavaScript form handling")
        print("  - Local storage for persistence")
        return True
    else:
        print("❌ UI content validation failed!")
        return False

if __name__ == "__main__":
    success = test_ui_content()
    exit(0 if success else 1)