from __future__ import annotations

import argparse
import logging
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from perpbot.exchanges.base import provision_exchanges
from perpbot.integrations.tradingview.router import create_tradingview_router


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>tv168</title>
    <style>
      body { font-family: Arial, sans-serif; background:#0b1021; color:#e9edf5; margin:0; padding:20px; }
      .card { background:#11182f; border:1px solid #1b2647; border-radius:10px; padding:14px; max-width:860px; }
      label { display:block; margin:8px 0 4px; color:#9aa5c2; font-size:12px; }
      select,input,button { background:#0f172a; border:1px solid #1f2a52; color:#fff; padding:8px; border-radius:8px; }
      button { cursor:pointer; background:#2f80ed; border:none; margin-right:8px; }
      button.secondary { background:#6c7a99; }
      .row { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
      pre { background:#0f172a; border:1px solid #1f2a52; padding:10px; border-radius:8px; white-space:pre-wrap; word-break:break-word; }
      .muted { color:#9aa5c2; font-size:12px; }
      a { color:#7ea8ff; }
    </style>
  </head>
  <body>
    <div class="card">
      <h2 style="margin-top:0">tv168（TradingView Webhook）</h2>
      <div class="muted">
        Endpoint: <code>/webhook/tradingview</code> · Health: <code>/health/tradingview</code> · Options: <code>/api/tv168/options</code>
      </div>
      <div class="row" style="margin-top:10px">
        <div>
          <label>交易所（exchange）</label>
          <select id="ex"></select>
        </div>
        <div>
          <label>交易对（instId/canonical）</label>
          <select id="sym"></select>
        </div>
      </div>
      <div class="row">
        <div>
          <label>周期（tf）</label>
          <input id="tf" value="1m" />
        </div>
        <div>
          <label>ZONE</label>
          <select id="zone">
            <option value="OVERSOLD">OVERSOLD</option>
            <option value="OVERBOUGHT">OVERBOUGHT</option>
          </select>
        </div>
      </div>
      <label>过滤</label>
      <input id="q" placeholder="BTC / SOL / USDT..." />
      <label>Secret（不会从服务端读取，请手动填）</label>
      <input id="secret" type="password" placeholder="PERPBOT_TV_WEBHOOK_SECRET" />
      <div style="margin-top:12px">
        <button class="secondary" id="genZone">生成 ZONE JSON</button>
        <button class="secondary" id="genDiv">生成 DIV JSON</button>
        <button id="sendZone">发送 ZONE</button>
        <button id="sendDiv">发送 DIV</button>
      </div>
      <div class="muted" id="source" style="margin-top:8px"></div>
      <pre id="payload">加载中...</pre>
      <pre id="resp"></pre>
      <div class="muted">提示：默认 paper，不会下单；要执行下单需要设置 <code>PERPBOT_TV_TRADING_ENABLED=true</code>。</div>
    </div>
    <script>
      const $ = (id) => document.getElementById(id);
      const render = (id, obj) => { $(id).textContent = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2); };
      const build = (type) => {
        const payload = {
          secret: $('secret').value || 'CHANGE_ME',
          type,
          exchange: $('ex').value,
          instId: $('sym').value,
          tf: $('tf').value || '1m',
          t: new Date().toISOString(),
        };
        if (type === 'ZONE') payload.zone = $('zone').value || 'OVERSOLD';
        return payload;
      };
      const send = async (payload) => {
        render('payload', payload);
        render('resp', '');
        const resp = await fetch('/webhook/tradingview', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) render('resp', { error: true, status: resp.status, data });
        else render('resp', data);
      };

      async function loadMarkets(exchange, q) {
        const resp = await fetch(`/api/tv168/markets?exchange=${encodeURIComponent(exchange)}`);
        const data = await resp.json().catch(() => ({}));
        if (!data.ok || !data.markets) return { ok:false, markets:[] };
        let markets = data.markets;
        if (q) {
          const qq = q.toUpperCase();
          markets = markets.filter(m => (m.symbol||'').toUpperCase().includes(qq) || (m.raw||'').toUpperCase().includes(qq));
        }
        return { ok:true, markets, quote: data.quote };
      }

      async function init() {
        const opts = await fetch('/api/tv168/options').then(r => r.json());
        const exList = (opts.exchanges_supported_markets && opts.exchanges_supported_markets.length) ? opts.exchanges_supported_markets : [opts.default_exchange || 'okx'];
        $('ex').innerHTML = '';
        exList.forEach(ex => {
          const o = document.createElement('option'); o.value = ex; o.textContent = ex; $('ex').appendChild(o);
        });
        $('ex').value = opts.default_exchange || $('ex').value;

        async function refreshSymbols() {
          const q = ($('q').value || '').trim();
          const ex = $('ex').value;
          const out = await loadMarkets(ex, q);
          $('sym').innerHTML = '';
          if (out.ok && out.markets.length) {
            $('source').textContent = `交易对来源：markets（${out.markets.length}） quote=${out.quote || ''}`;
            out.markets.slice(0, 800).forEach(m => {
              const o = document.createElement('option');
              o.value = m.symbol;
              o.textContent = `${m.symbol} (${m.raw})`;
              $('sym').appendChild(o);
            });
          } else {
            $('source').textContent = '交易对来源：allowlist（markets 拉取失败/为空）';
            const syms = opts.symbols_allowlist || [];
            const aliases = opts.symbol_aliases || {};
            syms.forEach(s => {
              const o = document.createElement('option'); o.value = s; o.textContent = s; $('sym').appendChild(o);
            });
            Object.entries(aliases).forEach(([k,v]) => {
              const o = document.createElement('option'); o.value = k; o.textContent = `${k} → ${v}`; $('sym').appendChild(o);
            });
          }
          render('payload', build('ZONE'));
        }

        $('ex').addEventListener('change', refreshSymbols);
        $('q').addEventListener('input', refreshSymbols);

        $('genZone').addEventListener('click', () => render('payload', build('ZONE')));
        $('genDiv').addEventListener('click', () => render('payload', build('DIV')));
        $('sendZone').addEventListener('click', () => send(build('ZONE')));
        $('sendDiv').addEventListener('click', () => send(build('DIV')));

        await refreshSymbols();
      }

      init().catch(e => render('payload', { error: String(e) }));
    </script>
  </body>
</html>
"""


def create_app() -> FastAPI:
    exchanges = provision_exchanges()
    service = SimpleNamespace(
        exchanges=exchanges,
        state=SimpleNamespace(trading_enabled=True),
    )
    app = FastAPI(title="tv168", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def _index() -> str:
        return _INDEX_HTML

    app.include_router(create_tradingview_router(service))
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="tv168 TradingView webhook service (standalone)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
