import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const base='recepcion/app/static/';
const src=fs.readFileSync(base+'azur_readonly_config.js','utf8');
const billing=fs.readFileSync(base+'billing_advanced.js','utf8');
const endpoints=[];
const output={textContent:'',className:''};
const token={value:'sk_live_synthetic_mock_not_real_012345'};
const save={disabled:false}, test={disabled:false};
const pill={textContent:'',classList:{toggle() {}}};
const tenant={textContent:''};
const lookups={'#azurReadKey':token,'#azurReadSave':save,'#azurReadTest':test,'#azurReadPill':pill,'#azurReadResult':output,'#azurReadTenant':tenant};
const ctx={
 window:{},
 document:{readyState:'loading',addEventListener(){},querySelector:s=>lookups[s]||null},
 api:async(url,opt={})=>{endpoints.push({url,opt});if(url.endsWith('/config'))return {ok:true,configured:true,read_only:true,environment:'PRODUCCIÓN',tenant:'ejemplo.azur.com.ec'};if(url.endsWith('/status'))return {configured:true,read_only:true,environment:'PRODUCCIÓN',tenant:'ejemplo.azur.com.ec'};if(url.endsWith('/test'))return {ok:true,environment:'PRODUCCIÓN',message:'Consulta validada'};if(url.endsWith('/verify-invoice'))return {ok:true,printed:false,azur_id:10,message:'Coincide'};throw Error('Unexpected API '+url);},
 setTimeout(){},alert(){},console,
};
vm.runInNewContext(src,ctx,{filename:'azur_readonly_config.js'});
assert.equal(typeof ctx.window.saveAzurReadKey,'function');
assert.equal(typeof ctx.window.testAzurReadKey,'function');
assert.equal(typeof ctx.window.verifyAzurPosInvoice,'function');
await ctx.window.saveAzurReadKey();
assert.equal(token.value,'','The secret must clear after saving');
assert.equal(endpoints[0].url,'/api/azur/readonly/config');
assert.equal(endpoints[0].opt.method,'POST');
assert.match(endpoints[0].opt.body,/sk_live_synthetic_mock_not_real/);
assert.doesNotMatch(output.textContent,/synthetic_mock/,'Never display the API key in messages');
await ctx.window.testAzurReadKey();
assert.equal(endpoints[1].url,'/api/azur/readonly/test');
assert.doesNotMatch(output.textContent,/synthetic_mock/);
assert.match(billing,/rpBillingVerifySelected\(\)/);
assert.match(billing,/window\.rpBillingVerifySelected/);
assert.doesNotMatch(src,/\/api\/billing\/(approve|emit)/);
assert.doesNotMatch(src,/setInterval\s*\(/,'Never poll AZUR in background');
console.log('AZUR_V2_READONLY_UI_LOCAL_SAFE_4846_OK');
