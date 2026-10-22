#!/usr/bin/env python3
"""One-time idempotent R2 bucket+7d rule provisioning using existing GitHub Actions CF token.

Does not touch the WhatsApp worker, cloud messaging secrets, KV, Neon or patients.
Does not expose account ID, credentials, worker secrets, or existing bucket names.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request

ACCOUNT=os.getenv("CLOUDFLARE_ACCOUNT_ID","").strip()
TOKEN=os.getenv("CLOUDFLARE_API_TOKEN","").strip()
BUCKET="dr-revelo-clinical-2026"
RULE_ID="revelo-clinical-temp-expire-7d"
BASE=f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets"
SEVEN_DAYS=7*24*60*60

def call(method, path, body=None):
    url=BASE+path
    headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"}
    req=urllib.request.Request(url,method=method,headers=headers,
                               data=(json.dumps(body,separators=(",",":")).encode() if body is not None else None))
    try:
        # Retry read-only calls only; never blindly repeat bucket creation or rule edits.
        attempts=3 if method=="GET" else 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(req,timeout=12) as response:
                    result=json.load(response)
                break
            except TimeoutError:
                if attempt + 1 >= attempts:
                    raise RuntimeError("R2_PROVIDER_TIMEOUT_REPEATED") from None
                print(f"R2_GET_TIMEOUT_RETRY_{attempt+1}")
    except urllib.error.HTTPError as exc:
        # Do not surface tokens, raw request headers or private account identifiers.
        code=int(exc.code)
        if code in (401,403):
            try:
                body=json.loads(exc.read().decode("utf-8","replace"))
                codes=",".join(str(e.get("code",""))[:12] for e in body.get("errors",[]) if isinstance(e,dict))
            except Exception:
                codes="unavailable"
            # Only numeric Cloudflare error identifiers; never emit provider messages or tokens.
            raise RuntimeError(f"R2_ACCESS_DENIED_HTTP_{code}_CODES_{codes}") from None
        if code in (402,424):
            raise RuntimeError("R2_BILLING_REQUIRED: account needs R2 plan/billing activated") from None
        raise RuntimeError(f"R2_API_HTTP_{code} while executing {method}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError("R2_NETWORK_ERROR") from None
    if result.get("success") is not True:
        errors=result.get("errors") or []
        codes=[str(e.get("code",""))[:10] for e in errors if isinstance(e,dict)]
        raise RuntimeError("R2_API_ERROR_CODES: "+",".join(codes))
    return result.get("result")

def run():
    if not ACCOUNT or not TOKEN:
        raise RuntimeError("R2_NO_GITHUB_SECRETS: missing Cloudflare token/account id")
    print("CLOUDFLARE_CREDENTIALS_PRESENT")
    # Never alter arbitrary existing buckets.
    try:
        existing=call("GET","/"+BUCKET)
    except RuntimeError as exc:
        # Treat only 404 as absent; all other errors are fatal.
        if str(exc)!="R2_API_HTTP_404 while executing GET":
            raise
        existing=None
    if existing is None:
        call("POST","",{"name":BUCKET,"storageClass":"Standard"})
        print("R2_NEW_PRIVATE_STANDARD_BUCKET_CREATED")
    else:
        print("R2_PRIVATE_CLINICAL_BUCKET_EXISTS")
    result=call("GET","/"+BUCKET+"/lifecycle") or {}
    rules=list(result.get("rules") or [])
    new_rule={"id":RULE_ID,"enabled":True,"conditions":{"prefix":"clinical-temp/"},
              "deleteObjectsTransition":{"condition":{"type":"Age","maxAge":SEVEN_DAYS}}}
    matches=[x for x in rules if str(x.get("id"))==RULE_ID]
    if len(matches)>1:
        raise RuntimeError("R2_DUPLICATE_LIFECYCLE_ID")
    clean=[r for r in rules if str(r.get("id"))!=RULE_ID]
    if matches != [new_rule]:
        call("PUT","/"+BUCKET+"/lifecycle",{"rules":clean+[new_rule]})
        print("R2_SEVEN_DAY_RETENTION_SET")
    verify=call("GET","/"+BUCKET+"/lifecycle") or {}
    actual=[r for r in verify.get("rules") or [] if r.get("id")==RULE_ID]
    if len(actual)!=1:raise RuntimeError("R2_RETENTION_RULE_MISSING")
    cond=(actual[0].get("deleteObjectsTransition") or {}).get("condition") or {}
    if not(actual[0].get("enabled") is True and (actual[0].get("conditions") or {}).get("prefix")=="clinical-temp/"
           and cond.get("type")=="Age" and cond.get("maxAge")==SEVEN_DAYS):
        raise RuntimeError("R2_RETENTION_RULE_MISMATCH")
    print("R2_PRIVATE_STANDARD_BUCKET_AND_7D_LIFECYCLE_VERIFIED")
    print("R2_BUCKET_NAME="+BUCKET)
    print("R2_S3_APPLICATION_CREDENTIALS_NOT_PROVISIONED_BY_THIS_JOB")
    print("R2_META_TEMPLATES_NOT_PROVISIONED_BY_THIS_JOB")

if __name__=="__main__":
    run()
