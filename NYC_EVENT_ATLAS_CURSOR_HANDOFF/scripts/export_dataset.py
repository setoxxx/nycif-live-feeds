import argparse, csv
from pathlib import Path
from nyc_event_atlas.export import export_csv, export_txt, export_geojson, export_kml
p=argparse.ArgumentParser(); p.add_argument('--input',default='NYC_EVENTS_MASTER_CUMULATIVE.csv'); p.add_argument('--out',default='data/exports'); args=p.parse_args()
with open(args.input,encoding='utf-8-sig',newline='') as f: records=list(csv.DictReader(f))
out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
base=out/'NYC_EVENTS_MASTER_CUMULATIVE'
export_csv(records,str(base)+'.csv'); export_txt(records,str(base)+'.txt'); export_geojson(records,str(base)+'.geojson'); export_kml(records,str(base)+'.kml')
print(base)
