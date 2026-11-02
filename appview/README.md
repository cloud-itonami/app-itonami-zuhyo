# itonami Zuhyo（図表）— appview の公開方式

2026-10-31 から（JUN-700）、この app は **ユーザーのブラウザで動く静的アプリ** として公開する。
app origin（`aya.itonami.app`）ではサーバー処理をしない。workspace の共有契約
「Kotoba end-user apps run in the user's environment」に従う。

## 静的バンドル

`slides-mcp-component/cljs/public/` がそのまま配信物になる。

| ファイル | 役割 |
|---|---|
| `index.html` | 入口。CSP の `connect-src` は `client-runtime.json` から導いた値（今は `'none'`） |
| `client-runtime.json` | `kotoba.app.client-runtime.v1` descriptor。外部操作は 0 件 |
| `.well-known/did.json` | `did:web:aya.itonami.app` の DID 文書（静的） |
| `js/app.js` | UI 本体。`cljs/public/js/app.js` はビルド済みのものがコミットされている。 |

## 公開

IPFS（kotobase blocks）にバンドルを載せ、`_dnslink.aya.itonami.app` の TXT を
`/ipfs/<cid>` に向ける。`*.itonami.app` は DNSLink の名前空間（ADR-2609092600）で、
net-kotobase/ipfs の Worker が配信する。Worker の route をこの app に追加しない。

## 外部操作を足すとき

`client-runtime.json` の `operations` に、service・endpoint・data-categories・
`consent: "each-operation"` を宣言する。実行は共有 broker
（`kotoba-lang/wasm-webcomponent/src/kotoba-client-runtime.js`、`slides-mcp-component/client-runtime.pin.json`
で revision と sha256 を固定）を通し、操作ごとにユーザーの同意を取ってからブラウザが直接呼ぶ。
app origin への API 呼び出しや、app origin 経由のプロキシは使わない。

## 確認

```bash
node slides-mcp-component/scripts/check-client-runtime.mjs <kotoba-client-runtime.js のパス>
```

broker の digest、descriptor の妥当性、app origin の endpoint を拒否すること（負の対照）、
index.html の CSP、did.json の id を確かめる。

## 退役した edge Worker（移行の棚卸し）

- Worker 名: `kotodama-slides-mcp`
- route: `aya-mcp.itonami.app/*`, `aya.itonami.app/*` （JUN-685 で etzhayyim.com から書き換えたもの。itonami.app へは一度もデプロイされていない）
- 役割: `/xrpc/*` を MCP router（`app.itonami.mcp.message`）と dispatcher へ中継し、内部シークレットを付ける BFF。
  `/health`、`/oauth/callback` も持っていた。中継先はどちらも稼働していない（JUN-700 の調査）。
- 最後のソース: `908a2a89ebe256decec3a99c7ebc83fc03515076` の `slides-mcp-component/src/app.ts`、`wrangler.jsonc`、`kotodama.jsonld`（edge actor の manifest）

旧 App services の記録:

- （記録なし）
