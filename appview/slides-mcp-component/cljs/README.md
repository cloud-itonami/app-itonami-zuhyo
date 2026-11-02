# itonami Zuhyo（図表）appview

Run `npm ci` and `npm run build` here to regenerate the committed production
`public/js/app.js` and manifest from the CLJS sources (Java/Clojure are required
for shadow-cljs). Serve `public/` to verify the static app before publishing.

Run `npm test` with Node 22.18 or later for the Worker request regressions.
These tests import the actual TypeScript Worker using Node's type stripping.
POST XRPC requests retain the MCP router's `tools/call` envelope and caller
authentication; OPTIONS retains the preflight response from the former appview.
GET facade and OAuth routes continue to use the dispatcher.
