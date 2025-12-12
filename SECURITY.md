# PerpBot V2 安全指南

**版本**: V2 Event-Driven  
**最后更新**: 2025-12-12

> **⚠️ 警告**: 本文档包含关键安全信息，请务必仔细阅读并遵循所有安全建议。

---

## 目录

- [安全概述](#安全概述)
- [威胁模型](#威胁模型)
- [API 密钥管理](#api-密钥管理)
- [加密存储方案](#加密存储方案)
- [网络安全](#网络安全)
- [权限最小化](#权限最小化)
- [审计与监控](#审计与监控)
- [应急响应](#应急响应)
- [安全检查清单](#安全检查清单)

---

## 安全概述

### 核心原则

1. **密钥隔离**: 私钥永不明文存储
2. **权限最小化**: API 只开启必需权限
3. **网络隔离**: IP 白名单 + VPN
4. **实时审计**: 所有敏感操作记录
5. **多重验证**: 关键操作需要多签

### 风险等级

| 风险 | 影响 | 概率 | 等级 | 防护措施 |
|------|------|------|------|----------|
| 私钥泄露 | 极高 | 中 | 🔴 严重 | 加密存储 + 定期轮换 |
| API 滥用 | 高 | 中 | 🟠 高 | IP 白名单 + 限流 |
| 未授权访问 | 高 | 低 | 🟠 高 | 认证 + 审计 |
| 资金被盗 | 极高 | 极低 | 🔴 严重 | 禁用提现 + 多签 |
| DDoS 攻击 | 中 | 中 | 🟡 中 | CDN + 限流 |

---

## 威胁模型

### 场景 1: 私钥泄露

**攻击者目标**: 获取私钥，控制账户

**攻击途径**:
- 代码泄露到 GitHub
- 服务器被入侵
- 钓鱼攻击
- 内部人员

**防护措施**:
```python
# ❌ 错误：明文存储
PRIVATE_KEY = "0x1234567890abcdef..."

# ✅ 正确：加密存储
from perpbot.security import SecureCredentialManager
cred_manager = SecureCredentialManager(master_key=os.getenv('MASTER_KEY'))
private_key = cred_manager.get_credential('PARADEX_PRIVATE_KEY')
```

### 场景 2: API 密钥滥用

**攻击者目标**: 使用泄露的 API 密钥下单或提现

**攻击途径**:
- 密钥泄露
- 中间人攻击
- 日志泄露

**防护措施**:
1. **权限限制**: API 密钥**禁止提现**
2. **IP 白名单**: 只允许固定 IP
3. **Subkey**: 使用子密钥，主密钥离线存储

```bash
# 在交易所后台设置
API Key: your_api_key
Permissions: [✅ Read, ✅ Trade, ❌ Withdraw]
IP Whitelist: [123.45.67.89, 123.45.67.90]
```

### 场景 3: 服务器被入侵

**攻击者目标**: 控制服务器，窃取密钥或篡改代码

**攻击途径**:
- SSH 弱密码
- 未打补丁的漏洞
- 恶意软件

**防护措施**:
1. **SSH 密钥登录**: 禁用密码登录
```bash
# /etc/ssh/sshd_config
PasswordAuthentication no
PubkeyAuthentication yes
```

2. **防火墙**: 只开放必要端口
```bash
# UFW 配置
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp  # SSH
ufw allow 8000/tcp  # Web Console (仅允许特定 IP)
ufw enable
```

3. **定期更新**: 自动安全补丁
```bash
# 自动更新
apt install unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

---

## API 密钥管理

### 1. 密钥类型

#### DEX 私钥（Starknet）

**Paradex / Extended**:
```bash
# .env
PARADEX_PRIVATE_KEY=0x...  # STARK 私钥
PARADEX_ACCOUNT=0x...      # 账户地址

EXTENDED_STARK_KEY=0x...
EXTENDED_VAULT_NUMBER=12345
```

**特点**:
- 完全控制账户
- 无法撤销（除非转移资金）
- 需要妥善保管

**最佳实践**:
1. 使用 **Subkey**（子密钥）
2. 主密钥冷存储
3. Subkey 定期轮换

#### CEX API 密钥（OKX / Binance）

```bash
# .env
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...

BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

**特点**:
- 可撤销
- 权限可配置
- IP 白名单

### 2. Subkey（子密钥）方案

#### 什么是 Subkey？

Subkey 是从主密钥派生的子密钥，具有**有限权限**：
- ✅ 可以交易
- ❌ 不能提现
- ✅ 可随时撤销

#### 如何创建 Subkey？

**Paradex**:
```python
from starknet_py.net.signer.stark_curve_signer import KeyPair

# 1. 生成新的 Subkey
subkey = KeyPair.generate()
print(f"Subkey Private: {hex(subkey.private_key)}")
print(f"Subkey Public: {hex(subkey.public_key)}")

# 2. 在 Paradex UI 中注册
# 前往 Settings > API Keys > Add Subkey
# 输入 Public Key

# 3. 使用 Subkey 签名
from paradex_sdk import ParadexClient
client = ParadexClient(private_key=subkey.private_key)
```

**Extended**:
```python
# Extended 也支持 Subkey
# 在 API Management 页面生成
```

#### Subkey 轮换

```bash
# 每月轮换一次
1. 生成新 Subkey
2. 在交易所注册
3. 更新 .env
4. 重启服务
5. 撤销旧 Subkey
```

### 3. 密钥存储层级

```
┌─────────────────────────────────────────┐
│  Tier 1: 冷钱包（主密钥）                │
│  • 硬件钱包 (Ledger / Trezor)           │
│  • 纸钱包（加密保管箱）                  │
│  • 不联网，仅用于转账和创建 Subkey       │
└─────────────────────────────────────────┘
               ↓ (派生 Subkey)
┌─────────────────────────────────────────┐
│  Tier 2: 热钱包（Subkey）                │
│  • 加密存储在服务器                      │
│  • 仅交易权限                            │
│  • 定期轮换                              │
└─────────────────────────────────────────┘
               ↓ (使用)
┌─────────────────────────────────────────┐
│  Tier 3: 会话密钥（Session Key）        │
│  • 短期有效（如 24 小时）                │
│  • JWT Token                            │
│  • 自动过期                              │
└─────────────────────────────────────────┘
```

---

## 加密存储方案

### 方案 1: Fernet 对称加密（推荐）

```python
from cryptography.fernet import Fernet
import os

class SecureCredentialManager:
    def __init__(self, master_key: str = None):
        """
        master_key: 从环境变量或 AWS Secrets Manager 获取
        """
        if master_key is None:
            master_key = os.getenv('MASTER_KEY')
            if not master_key:
                # 首次运行生成主密钥
                master_key = Fernet.generate_key().decode()
                print(f"⚠️ 请保存 MASTER_KEY: {master_key}")
                print("建议存储在环境变量或 AWS Secrets Manager")
        
        self.cipher = Fernet(master_key.encode())
        self.env_file = '.env.encrypted'
    
    def encrypt_credential(self, key: str, value: str):
        """加密并保存凭据"""
        encrypted = self.cipher.encrypt(value.encode()).decode()
        
        # 追加到加密文件
        with open(self.env_file, 'a') as f:
            f.write(f"{key}={encrypted}\n")
        
        print(f"✅ {key} 已加密存储")
    
    def get_credential(self, key: str) -> str:
        """解密并获取凭据"""
        if not os.path.exists(self.env_file):
            raise FileNotFoundError("加密文件不存在")
        
        with open(self.env_file, 'r') as f:
            for line in f:
                if line.startswith(key):
                    encrypted_value = line.split('=')[1].strip()
                    return self.cipher.decrypt(encrypted_value.encode()).decode()
        
        raise KeyError(f"凭据 {key} 不存在")
    
    def rotate_master_key(self, new_master_key: str):
        """轮换主密钥（重新加密所有凭据）"""
        # 1. 用旧密钥解密所有凭据
        credentials = {}
        with open(self.env_file, 'r') as f:
            for line in f:
                key, encrypted_value = line.strip().split('=')
                decrypted = self.cipher.decrypt(encrypted_value.encode()).decode()
                credentials[key] = decrypted
        
        # 2. 使用新密钥重新加密
        self.cipher = Fernet(new_master_key.encode())
        with open(self.env_file, 'w') as f:
            for key, value in credentials.items():
                encrypted = self.cipher.encrypt(value.encode()).decode()
                f.write(f"{key}={encrypted}\n")
        
        print("✅ 主密钥已轮换")

# 使用示例
if __name__ == "__main__":
    # 首次运行：初始化并加密密钥
    manager = SecureCredentialManager()
    
    # 加密存储
    manager.encrypt_credential('PARADEX_PRIVATE_KEY', '0x1234...')
    manager.encrypt_credential('EXTENDED_STARK_KEY', '0xabcd...')
    
    # 运行时获取
    paradex_key = manager.get_credential('PARADEX_PRIVATE_KEY')
    
    # 定期轮换主密钥
    manager.rotate_master_key(new_master_key=Fernet.generate_key().decode())
```

### 方案 2: AWS Secrets Manager（生产环境）

```python
import boto3
import json

class AWSSecretsManager:
    def __init__(self, region_name='us-east-1'):
        self.client = boto3.client('secretsmanager', region_name=region_name)
    
    def store_secret(self, secret_name: str, secret_value: dict):
        """存储密钥到 AWS"""
        try:
            self.client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(secret_value)
            )
            print(f"✅ {secret_name} 已存储到 AWS Secrets Manager")
        except self.client.exceptions.ResourceExistsException:
            # 更新现有密钥
            self.client.update_secret(
                SecretId=secret_name,
                SecretString=json.dumps(secret_value)
            )
    
    def get_secret(self, secret_name: str) -> dict:
        """从 AWS 获取密钥"""
        response = self.client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])

# 使用示例
aws = AWSSecretsManager()

# 存储
aws.store_secret('perpbot-prod', {
    'PARADEX_PRIVATE_KEY': '0x1234...',
    'EXTENDED_STARK_KEY': '0xabcd...',
    'MASTER_KEY': 'xxx'
})

# 获取
secrets = aws.get_secret('perpbot-prod')
paradex_key = secrets['PARADEX_PRIVATE_KEY']
```

### 方案 3: HashiCorp Vault（企业级）

```python
import hvac

class VaultManager:
    def __init__(self, url='http://127.0.0.1:8200', token=None):
        self.client = hvac.Client(url=url, token=token)
    
    def store_secret(self, path: str, data: dict):
        """存储到 Vault"""
        self.client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=data
        )
    
    def get_secret(self, path: str) -> dict:
        """从 Vault 获取"""
        response = self.client.secrets.kv.v2.read_secret_version(path=path)
        return response['data']['data']

# 使用示例
vault = VaultManager(token=os.getenv('VAULT_TOKEN'))
vault.store_secret('perpbot/prod', {
    'PARADEX_PRIVATE_KEY': '0x1234...'
})
```

---

## 网络安全

### 1. VPS 配置

#### 防火墙规则

```bash
# Ubuntu UFW
ufw default deny incoming
ufw default allow outgoing

# 允许 SSH（仅特定 IP）
ufw allow from 203.0.113.0/24 to any port 22

# 允许 Web Console（内网或 VPN）
ufw allow from 10.0.0.0/8 to any port 8000

# 启用
ufw enable
```

#### SSH 加固

```bash
# /etc/ssh/sshd_config
Port 2222  # 更改默认端口
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2

# 重启 SSH
systemctl restart sshd
```

### 2. HTTPS / TLS

#### 使用 Caddy 自动 HTTPS

```bash
# 安装 Caddy
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install caddy

# Caddyfile
perpbot.yourdomain.com {
    reverse_proxy localhost:8000
    tls your@email.com  # 自动申请 Let's Encrypt 证书
}

# 启动
caddy start
```

#### 或使用 Nginx + Certbot

```bash
# 安装
apt install nginx certbot python3-certbot-nginx

# 配置
# /etc/nginx/sites-available/perpbot
server {
    listen 80;
    server_name perpbot.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# 启用 HTTPS
certbot --nginx -d perpbot.yourdomain.com
```

### 3. VPN（可选）

```bash
# 安装 WireGuard
apt install wireguard

# 生成密钥
wg genkey | tee privatekey | wg pubkey > publickey

# 配置 /etc/wireguard/wg0.conf
[Interface]
PrivateKey = <server_private_key>
Address = 10.0.0.1/24
ListenPort = 51820

[Peer]
PublicKey = <client_public_key>
AllowedIPs = 10.0.0.2/32

# 启动
wg-quick up wg0
```

---

## 权限最小化

### 1. API 权限配置

#### Paradex

```
前往: https://app.paradex.trade/settings/api

创建 API Key:
  Name: PerpBot Production
  Permissions:
    [✅] Read Account
    [✅] Trade
    [❌] Withdraw  # 必须禁用
  IP Whitelist:
    123.45.67.89
    123.45.67.90
```

#### Extended

```
前往: https://extended.exchange/api-management

创建 API Key:
  Name: PerpBot Production
  Permissions:
    [✅] Read
    [✅] Trade
    [❌] Withdraw  # 必须禁用
  IP Whitelist:
    123.45.67.89
```

### 2. 系统用户权限

```bash
# 创建专用用户
useradd -m -s /bin/bash perpbot
passwd perpbot

# 限制权限
chmod 700 /home/perpbot
chown -R perpbot:perpbot /home/perpbot

# 切换用户运行
su - perpbot
cd /home/perpbot/perp-tools
python -m perpbot.cli serve
```

### 3. 文件权限

```bash
# 密钥文件权限
chmod 600 .env.encrypted
chmod 600 config.yaml

# 代码目录
chmod 755 src/

# 日志目录
chmod 750 logs/
```

---

## 审计与监控

### 1. 审计日志

```python
import logging
from datetime import datetime

class SecurityAuditLogger:
    def __init__(self, log_file="security_audit.log"):
        self.logger = logging.getLogger("security_audit")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_api_call(self, exchange: str, endpoint: str, params: dict):
        """记录 API 调用"""
        self.logger.info(
            f"API_CALL | {exchange} | {endpoint} | "
            f"params={self._sanitize(params)}"
        )
    
    def log_order(self, exchange: str, order_id: str, details: dict):
        """记录订单"""
        self.logger.info(
            f"ORDER | {exchange} | {order_id} | {details}"
        )
    
    def log_withdrawal_attempt(self, exchange: str, amount: float, address: str):
        """记录提现尝试（应该被阻止）"""
        self.logger.warning(
            f"⚠️ WITHDRAWAL_ATTEMPT | {exchange} | "
            f"amount={amount} | address={address}"
        )
        # 发送紧急告警
        self._send_alert("检测到提现尝试！")
    
    def log_suspicious_activity(self, activity: str, details: dict):
        """记录可疑活动"""
        self.logger.warning(
            f"⚠️ SUSPICIOUS | {activity} | {details}"
        )
    
    def log_login(self, source_ip: str, success: bool):
        """记录登录"""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"LOGIN | {source_ip} | {status}")
        
        if not success:
            self._check_brute_force(source_ip)
    
    def _sanitize(self, data: dict) -> dict:
        """脱敏（隐藏密钥）"""
        sensitive_keys = ['private_key', 'api_secret', 'passphrase']
        sanitized = data.copy()
        for key in sensitive_keys:
            if key in sanitized:
                sanitized[key] = "***REDACTED***"
        return sanitized
    
    def _check_brute_force(self, ip: str):
        """检测暴力破解"""
        # 实现逻辑...
        pass

# 使用示例
audit = SecurityAuditLogger()

# 记录 API 调用
audit.log_api_call(
    exchange="paradex",
    endpoint="/orders",
    params={"symbol": "BTC-USD-PERP", "side": "BUY"}
)

# 记录订单
audit.log_order(
    exchange="paradex",
    order_id="order_123",
    details={"size": 0.001, "price": 95000}
)
```

### 2. 实时监控

```python
class SecurityMonitor:
    def __init__(self):
        self.failed_logins = {}
        self.api_call_counts = {}
    
    def check_anomalies(self):
        """检测异常"""
        # 1. API 调用频率异常
        for exchange, count in self.api_call_counts.items():
            if count > 200:  # 每分钟超过 200 次
                self.alert(f"{exchange} API 调用异常频繁: {count}/min")
        
        # 2. 余额异常下降
        current_balance = self._get_balance()
        if current_balance < self.last_balance * 0.9:  # 下降 10%
            self.alert(f"余额异常下降: {self.last_balance} → {current_balance}")
        
        # 3. 未知 IP 访问
        recent_ips = self._get_recent_ips()
        for ip in recent_ips:
            if ip not in self.whitelist:
                self.alert(f"未知 IP 访问: {ip}")
    
    def alert(self, message: str):
        """发送告警"""
        print(f"🚨 SECURITY ALERT: {message}")
        # 发送到 Telegram / Email / Lark
```

---

## 应急响应

### 紧急情况处理流程

#### 情况 1: 怀疑密钥泄露

```bash
# 立即执行:
1. 停止所有交易
   pkill -f perpbot

2. 撤销 API 密钥
   前往交易所后台 → API Management → 撤销密钥

3. 转移资金
   从热钱包转移到冷钱包

4. 分析日志
   grep "SUSPICIOUS\|WITHDRAWAL" security_audit.log

5. 轮换所有密钥
   生成新的 Subkey
   更新 .env.encrypted
   重启服务

6. 事后报告
   记录事件经过
   改进安全措施
```

#### 情况 2: 检测到未授权交易

```bash
# 立即执行:
1. 暂停交易
   curl -X POST http://localhost:8000/api/control/pause

2. 平掉所有仓位
   PYTHONPATH=src python -m perpbot.cli emergency_close_all

3. 检查订单历史
   查看是否有异常订单

4. 冻结账户
   联系交易所客服

5. 取证
   保存所有日志和订单记录

6. 报警
   向相关部门报案
```

#### 情况 3: 服务器被入侵

```bash
# 立即执行:
1. 断网
   ifconfig eth0 down

2. 保存现场
   dd if=/dev/sda of=/mnt/usb/disk_image.img

3. 分析入侵
   检查 /var/log/auth.log
   检查异常进程: ps aux | grep -v "\[.*\]"

4. 重装系统
   备份数据
   重装操作系统
   恢复数据

5. 加固安全
   更新所有软件
   更改所有密码
   启用双因素认证
```

---

## 安全检查清单

### 部署前检查

- [ ] **密钥安全**
  - [ ] 所有私钥已加密存储
  - [ ] 主密钥存储在安全位置（环境变量/AWS Secrets Manager）
  - [ ] `.env` 文件已添加到 `.gitignore`
  - [ ] 使用 Subkey 而非主密钥

- [ ] **权限配置**
  - [ ] API 密钥禁用提现权限
  - [ ] API 密钥配置 IP 白名单
  - [ ] 系统用户权限最小化
  - [ ] 文件权限正确设置（600/700）

- [ ] **网络安全**
  - [ ] SSH 密钥登录，禁用密码
  - [ ] 防火墙已配置
  - [ ] Web Console 启用 HTTPS
  - [ ] 考虑使用 VPN

- [ ] **审计与监控**
  - [ ] 审计日志已启用
  - [ ] 实时监控已配置
  - [ ] 告警渠道已测试
  - [ ] 日志定期备份

### 运行中检查（每周）

- [ ] 检查审计日志是否有异常
- [ ] 检查 API 密钥是否仍有效
- [ ] 检查余额是否正常
- [ ] 检查系统是否有未打补丁

### 定期任务（每月）

- [ ] 轮换 Subkey
- [ ] 轮换主密钥（可选）
- [ ] 备份配置和日志
- [ ] 更新系统和依赖
- [ ] 审查权限配置

---

## 总结

安全是一个**持续的过程**，而非一次性任务。请遵循以下原则：

✅ **假设最坏情况**: 假设密钥会泄露，提前做好防护
✅ **纵深防御**: 多层防护，不依赖单点
✅ **最小权限**: 只开启必需的权限
✅ **实时监控**: 及时发现异常
✅ **定期演练**: 定期测试应急响应流程

**记住**:
- 🔐 主密钥 = 资金，务必妥善保管
- 🚫 禁用提现权限
- 🔒 使用 Subkey 而非主密钥
- 📊 启用审计日志
- 🚨 配置实时告警

---

**最后更新**: 2024-12-08  
**文档版本**: v1.0  
**作者**: Claude (Anthropic)

**⚠️ 免责声明**: 本指南仅供参考，不构成安全保证。请根据实际情况调整安全措施。
