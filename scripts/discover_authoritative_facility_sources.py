#!/usr/bin/env python3
"""Discover official NYC facility datasets needed by the remaining SHADOW-2 audit."""
from __future__ import annotations
import json, urllib.parse, urllib.request

CATALOG='https://api.us.socrata.com/api/catalog/v1'
QUERIES=(
    'NYC library branches locations',
    'New York Public Library locations',
    'Brooklyn Public Library locations',
    'Queens Public Library locations',
    'NYC DOE school locations',
    'NYC Parks recreation centers',
)

def query(text: str):
    url=CATALOG+'?'+urllib.parse.urlencode({'q':text,'search_context':'data.cityofnewyork.us','limit':20})
    req=urllib.request.Request(url,headers={'User-Agent':'nycif-authoritative-facility-discovery/1.0'})
    with urllib.request.urlopen(req,timeout=60) as response:
        payload=json.load(response)
    out=[]
    for item in payload.get('results',[]):
        resource=item.get('resource') or {}
        metadata=item.get('metadata') or {}
        out.append({
            'id': resource.get('id'),
            'name': resource.get('name'),
            'description': resource.get('description'),
            'type': resource.get('type'),
            'updatedAt': resource.get('updatedAt'),
            'domain': metadata.get('domain'),
            'permalink': item.get('permalink'),
        })
    return out

def main():
    report={q:query(q) for q in QUERIES}
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return 0
if __name__=='__main__': raise SystemExit(main())
