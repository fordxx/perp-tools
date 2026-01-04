# TW168 文档目录

本目录包含 TW168 项目的所有文档。

## 📚 文档结构

```
docs/
├── README.md              # 本文件
├── API.md                 # API 接口文档
├── DEPLOYMENT.md          # 部署指南
├── DEVELOPMENT.md         # 开发指南
├── ARCHITECTURE.md        # 系统架构文档
├── TROUBLESHOOTING.md     # 故障排查指南
├── features/              # 特性文档
│   ├── RSI_FILTER.md
│   ├── TWO_LIMIT_ENTRY.md
│   └── LIGHTER_DEX.md
├── guides/                # 使用指南
│   ├── MONITOR_GUIDE.md
│   ├── QUICK_REFERENCE.md
│   └── ASYNC_REFACTOR_GUIDE.md
└── archive/               # 历史文档归档
    ├── BUG_FIXES.md
    ├── DEPLOYMENT_SUCCESS.md
    └── ...
```

## 🚀 快速导航

### 新手入门
1. 阅读根目录的 [README.md](../README.md) 了解项目概况
2. 查看 [DEPLOYMENT.md](DEPLOYMENT.md) 部署服务
3. 参考 [API.md](API.md) 配置 TradingView Webhook

### 开发者
1. [DEVELOPMENT.md](DEVELOPMENT.md) - 开发环境搭建
2. [ARCHITECTURE.md](ARCHITECTURE.md) - 系统架构详解
3. [../DESIGN.md](../DESIGN.md) - 完整设计文档

### 运维人员
1. [DEPLOYMENT.md](DEPLOYMENT.md) - 部署和升级
2. [guides/MONITOR_GUIDE.md](guides/MONITOR_GUIDE.md) - 监控指南
3. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 故障排查

## 📖 文档索引

### 核心文档

#### [API.md](API.md)
API 接口文档，包括：
- Webhook 端点说明
- 请求/响应格式
- 错误码参考
- 使用示例

#### [DEPLOYMENT.md](DEPLOYMENT.md)
部署指南，包括：
- 生产环境部署
- Docker 部署
- 配置说明
- 升级指南

#### [ARCHITECTURE.md](ARCHITECTURE.md)
系统架构文档，包括：
- 整体架构设计
- 模块划分
- 数据流
- 技术选型

#### [DEVELOPMENT.md](DEVELOPMENT.md)
开发指南，包括：
- 开发环境搭建
- 代码结构
- 贡献指南
- 测试说明

#### [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
故障排查，包括：
- 常见问题
- 错误诊断
- 解决方案
- 日志分析

### 特性文档

#### [features/RSI_FILTER.md](features/RSI_FILTER.md)
RSI 智能过滤器：
- K-means 聚类阈值
- 动态阈值配置
- 使用场景

#### [features/TWO_LIMIT_ENTRY.md](features/TWO_LIMIT_ENTRY.md)
双限价入场模式：
- 梯度建仓原理
- 配置参数
- 适用场景

#### [features/LIGHTER_DEX.md](features/LIGHTER_DEX.md)
Lighter DEX 集成：
- DEX 交易原理
- 订单管理
- WebSocket 集成

### 使用指南

#### [guides/MONITOR_GUIDE.md](guides/MONITOR_GUIDE.md)
监控指南：
- 监控脚本使用
- 关键指标
- 告警配置

#### [guides/QUICK_REFERENCE.md](guides/QUICK_REFERENCE.md)
快速参考：
- 常用命令
- 配置速查
- 故障快速修复

#### [guides/ASYNC_REFACTOR_GUIDE.md](guides/ASYNC_REFACTOR_GUIDE.md)
异步重构指南：
- Lighter 异步适配器
- 性能优化
- 迁移步骤

### 历史文档

[archive/](archive/) 目录包含历史版本的文档，主要用于归档和参考：
- Bug 修复记录
- 测试报告
- 实现计划
- 部署记录

## 🔄 文档更新

### 更新频率
- 核心文档：随版本更新
- 特性文档：功能开发时更新
- 指南文档：根据用户反馈更新
- 历史文档：仅作归档，不再更新

### 贡献文档
欢迎贡献文档改进！请遵循以下规范：

1. **文档格式**
   - 使用 Markdown 格式
   - 中英文之间加空格
   - 代码块指定语言

2. **文档结构**
   - 清晰的标题层级
   - 目录导航 (长文档)
   - 示例代码
   - 相关链接

3. **提交流程**
   - Fork 项目
   - 创建文档分支
   - 提交 PR
   - 等待审核

## 📝 文档版本

| 文档 | 版本 | 最后更新 |
|------|------|----------|
| API.md | 2.0 | 2025-01-01 |
| DEPLOYMENT.md | 2.0 | 2025-01-01 |
| ARCHITECTURE.md | 2.0 | 2025-01-01 |
| DEVELOPMENT.md | 1.0 | 2025-01-01 |

## 📞 获取帮助

- **问题反馈:** [GitHub Issues](https://github.com/your-repo/issues)
- **功能建议:** [GitHub Discussions](https://github.com/your-repo/discussions)
- **文档问题:** 在相应文档页面提交 Issue

---

**维护者:** TW168 Team
**最后更新:** 2025-01-01
