import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Run only the active legacy billing tab wrapper in isolation.
// Its 4.8.42 behavior ran a potentially minutes-long AZUR/SRI POST
// before reading the local invoice history.
const source=readFileSync("recepcion/app/core_runtime.py","utf8");
const overlay=source.match(/V476_JS\s*=\s*r"""([\s\S]*?)"""/)?.[1];
assert.ok(overlay,"Missing billing tab wrapper");
const calls={statuses:[],remote:[]};
const win={
  loadBilling:async()=>{},
  setBillingStatus:async state=>{calls.statuses.push(state);},
};
const doc={
  readyState:"loading",
  addEventListener(){},
  querySelector(){return null;},
};
const context={window:win,document:doc,api:async(...args)=>{
  calls.remote.push(args);
  throw new Error("Opening issued invoices must not contact AZUR");
},alert(){}};
new vm.Script(overlay,{filename:"billing-v476-embedded.js"}).runInNewContext(context);
await win.setBillingStatus("EMITIDA");
assert.deepEqual(calls.statuses,["EMITIDA"]);
assert.equal(calls.remote.length,0,"Emitted history must open without POST to SRI");
await win.setBillingStatus("APROBADA");
assert.deepEqual(calls.statuses,["EMITIDA","PENDIENTE"]);
assert.equal(calls.remote.length,0);
const app=readFileSync("recepcion/app/static/app.js","utf8");
assert.match(app,/url='\/api\/billing\/issued-page'/);
assert.match(app,/params\.set\('scope',billingIssuedScope\)/);
assert.match(app,/params\.set\('page',String\(billingIssuedPage\)\)/);
const hist=readFileSync("recepcion/app/reception_billing_history.py","utf8");
assert.match(hist,/ISSUED_PAGE_SIZE\s*=\s*20/);
assert.match(hist,/@app\.get\('\/api\/billing\/issued-page'\)/);
assert.doesNotMatch(overlay,/check-all-status/);
assert.ok(!source.includes("if(text.includes('emitidas')||text.includes('autorizadas'))showAzurLoading()"),
  "Loading banner must not pretend AZUR is queried when opening saved history");
console.log("RECEPTION_BILLING_ISSUED_NONBLOCKING_LOCAL_ONLY_4843_OK");
