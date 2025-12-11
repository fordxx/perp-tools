# Paradex DEX - 依赖说明

## 📦 必需依赖

Paradex 客户端需要以下 Python 库：

### 1. httpx
**用途：** 异步 HTTP 客户端，用于与 Paradex API 通信

```bash
pip install httpx
```

**版本要求：** >= 0.24.0

---

### 2. python-dotenv
**用途：** 从 `.env` 文件加载环境变量

```bash
pip install python-dotenv
```

**版本要求：** >= 1.0.0

---

## 📦 可选依赖

### 1. starknet-py（未来支持）
**用途：** STARK 密钥签名（当前版本不需要）

```bash
# 暂时不需要安装
# pip install starknet-py
```

---

## 🚀 快速安装

### 方法 1: 一键安装（推荐）

```bash
pip install httpx python-dotenv
```

### 方法 2: 使用 requirements.txt

如果项目根目录有 `requirements.txt`：

```bash
pip install -r requirements.txt
```

---

## ✅ 验证安装

运行以下命令验证依赖已正确安装：

```bash
python -c "import httpx; print('✅ httpx:', httpx.__version__)"
python -c "from dotenv import load_dotenv; print('✅ python-dotenv 已安装')"
```

**预期输出：**
```
✅ httpx: 0.24.1
✅ python-dotenv 已安装
```

---

## 🔧 常见问题

### Q1: pip install 失败？

**错误：** `ERROR: Could not find a version that satisfies the requirement httpx`

**解决方法：**
```bash
# 升级 pip
python -m pip install --upgrade pip

# 重新安装
pip install httpx python-dotenv
```

### Q2: 导入失败？

**错误：** `ModuleNotFoundError: No module named 'httpx'`

**解决方法：**
```bash
# 确认使用正确的 Python 版本
python --version  # 应该是 3.10+

# 确认 pip 对应的 Python 版本
pip --version

# 使用 python -m pip 安装
python -m pip install httpx python-dotenv
```

### Q3: 虚拟环境问题？

**建议使用虚拟环境：**

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate

# 安装依赖
pip install httpx python-dotenv

# 运行测试
python test_paradex.py
```

---

## 📚 依赖详细说明

### httpx vs requests

我们使用 `httpx` 而不是 `requests`，因为：

- ✅ 支持 HTTP/2
- ✅ 更好的异步支持
- ✅ 更现代的 API
- ✅ 更好的性能

**如果你已经安装了 requests：**

可以将代码中的 `httpx` 替换为 `requests`，但推荐使用 `httpx`。

---

## 🆘 需要帮助？

如果安装依赖时遇到问题，请：

1. 检查 Python 版本（需要 3.10+）
2. 升级 pip 到最新版本
3. 尝试使用虚拟环境
4. 查看详细错误日志

**仍然无法解决？**
- 在 GitHub 提 Issue
- 附上错误日志和 Python 版本
