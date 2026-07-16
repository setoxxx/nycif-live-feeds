from __future__ import annotations
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .http_client import AtlasHttpClient

def discover(url: str, client=None):
    client = client or AtlasHttpClient()
    r, meta = client.get(url)
    soup = BeautifulSoup(r.text, 'lxml')
    links = []
    for tag in soup.find_all(['a','link'], href=True):
        href = urljoin(r.url, tag['href'])
        rel = ' '.join(tag.get('rel',[]))
        typ = tag.get('type','')
        if href.endswith('.ics') or typ == 'text/calendar' or 'alternate' in rel or 'api.w.org' in rel:
            links.append({'href':href,'rel':rel,'type':typ})
    return {
        'url': r.url,
        'jsonld_blocks': len(soup.find_all('script', attrs={'type':'application/ld+json'})),
        'candidate_feeds': links,
        'wordpress_api': next((x['href'] for x in links if 'api.w.org' in x['rel']), None),
        'meta': meta,
    }
