from __future__ import annotations
import csv, json
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree
from .schema import EXPORT_COLUMNS

def export_csv(records, path):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=EXPORT_COLUMNS); w.writeheader(); w.writerows(records)

def export_txt(records, path):
    with open(path,'w',encoding='utf-8') as f:
        for r in records:
            f.write('='*60+'\n')
            for c in EXPORT_COLUMNS: f.write(f'{c}:\n{r.get(c,"Unknown")}\n\n')

def export_geojson(records, path):
    features=[]
    for r in records:
        if r.get('LATITUDE') in ('','Unknown') or r.get('LONGITUDE') in ('','Unknown'): continue
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[float(r['LONGITUDE']),float(r['LATITUDE'])]},'properties':r})
    Path(path).write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,indent=2),encoding='utf-8')

def export_kml(records, path):
    kml=Element('kml',xmlns='http://www.opengis.net/kml/2.2'); doc=SubElement(kml,'Document')
    for r in records:
        if r.get('LATITUDE') in ('','Unknown') or r.get('LONGITUDE') in ('','Unknown'): continue
        pm=SubElement(doc,'Placemark'); SubElement(pm,'name').text=r['EVENT_NAME']; point=SubElement(pm,'Point'); SubElement(point,'coordinates').text=f"{r['LONGITUDE']},{r['LATITUDE']},0"
    ElementTree(kml).write(path,encoding='utf-8',xml_declaration=True)
