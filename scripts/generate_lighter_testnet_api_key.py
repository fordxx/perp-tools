#!/usr/bin/env python3
"""
Lighter Testnet API Key 生成/注册脚本（最小可用版）

用途：
- 使用你的 L1 钱包私钥（ETH_PRIVATE_KEY）在 Lighter Testnet 上注册/更新某个 api_key_index 的公钥
- 生成对应的 API Key Private Key（用于 perp-tools 里 SignerClient 交易/查余额/查持仓）

安全提示：
- ETH_PRIVATE_KEY 是 L1 钱包私钥（最高权限），仅在本机运行，绝对不要泄露/提交到仓库
- 输出的 LIGHTER_API_KEY_PRIVATE_KEY 也属于敏感信息，只写进本机 .env，不要提交到仓库
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from typing import Optional

import eth_account
import lighter


BASE_URL = "https://testnet.zklighter.elliot.ai"


def _ask_int(prompt: str, default: Optional[int] = None) -> Optional[int]:
    default_str = "" if default is None else f" (默认 {default})"
    raw = input(f"{prompt}{default_str}: ").strip()
    if raw == "":
        return default
    return int(raw, 10)


async def _resolve_account_index(api_client: lighter.ApiClient, eth_private_key: str, override: Optional[int]) -> int:
    if override is not None:
        return int(override)

    eth_acc = eth_account.Account.from_key(eth_private_key)
    eth_address = eth_acc.address

    try:
        response = await lighter.AccountApi(api_client).accounts_by_l1_address(l1_address=eth_address)
    except lighter.ApiException as e:
        if getattr(getattr(e, "data", None), "message", "") == "account not found":
            raise RuntimeError(f"account not found for l1_address={eth_address}") from e
        raise

    if not getattr(response, "sub_accounts", None):
        raise RuntimeError(f"no sub_accounts returned for l1_address={eth_address}")

    if len(response.sub_accounts) > 1:
        indices = [int(a.index) for a in response.sub_accounts]
        master = min(indices)
        print(f"[info] found multiple accounts: {indices} -> using master={master}")
        return master

    return int(response.sub_accounts[0].index)


async def main() -> int:
    print("=== Lighter Testnet API Key 生成/注册（最小可用版）===")
    print(f"[info] BASE_URL={BASE_URL}")
    print("")

    eth_private_key = getpass.getpass("输入 ETH_PRIVATE_KEY（L1 私钥，不回显）: ").strip()
    if not eth_private_key:
        print("[error] ETH_PRIVATE_KEY 不能为空")
        return 1
    if not eth_private_key.startswith("0x"):
        eth_private_key = "0x" + eth_private_key

    api_key_index = _ask_int("输入要写入的 API_KEY_INDEX", default=0)
    if api_key_index is None or api_key_index < 0:
        print("[error] API_KEY_INDEX 必须是 >=0 的整数")
        return 1

    account_index_override = _ask_int("如已知 LIGHTER_ACCOUNT_INDEX 可直接输入（否则回车自动发现）", default=None)

    api_client = lighter.ApiClient(configuration=lighter.Configuration(host=BASE_URL))
    try:
        account_index = await _resolve_account_index(api_client, eth_private_key, account_index_override)
        print(f"[info] resolved account_index={account_index}")

        private_key, public_key, err = lighter.create_api_key()
        if err is not None:
            raise RuntimeError(f"create_api_key failed: {err}")

        tx_client = lighter.SignerClient(
            url=BASE_URL,
            account_index=account_index,
            api_private_keys={int(api_key_index): private_key},
        )
        try:
            resp, err = await tx_client.change_api_key(
                eth_private_key=eth_private_key,
                new_pubkey=public_key,
                api_key_index=int(api_key_index),
            )
            if err is not None:
                raise RuntimeError(f"change_api_key failed: {err}")

            print("[info] change_api_key submitted, waiting 10s for server to reflect...")
            await asyncio.sleep(10)

            err = tx_client.check_client()
            if err is not None:
                raise RuntimeError(f"check_client failed: {err}")

        finally:
            try:
                await tx_client.close()
            except Exception:
                pass

        print("")
        print("=== 复制以下内容到 perp-tools 的 .env（testnet）===")
        print(f"LIGHTER_ENV=testnet")
        print(f"LIGHTER_API_BASE_URL={BASE_URL}")
        print(f"LIGHTER_ACCOUNT_INDEX={account_index}")
        print(f"LIGHTER_API_KEY_INDEX={api_key_index}")
        print(f"LIGHTER_API_KEY_PRIVATE_KEY={private_key}")
        print("=== 完成后运行验证命令 ===")
        print("./run_exchange_test.sh lighter --auto-test --verbose --symbol ETH/USDT")
        return 0
    finally:
        try:
            await api_client.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[info] cancelled")
        sys.exit(130)

