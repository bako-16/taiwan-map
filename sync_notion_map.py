import os
import json
import base64
import requests
import time
from geopy.geocoders import ArcGIS

# --- CONFIGURATION (Via Variables d'environnement pour la s\u00e9curit\u00e9) ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")
# Pour GitHub Actions, on utilise le jeton local ou le jeton de l'action
GITHUB_TOKEN = os.environ.get("GH_TOKEN") 
REPO_NAME = "taiwan-map"
GITHUB_USER = "bako-16"
FILENAME = "index.html" # On revient sur index.html car le cache sera g\u00e9r\u00e9 par GitHub
# ---------------------

geolocator = ArcGIS()

def get_coords(address):
    if not address or len(address) < 3: return None
    try:
        # Nettoyage
        clean_addr = address.replace("Ta\u00efwan", "Taiwan")
        loc = geolocator.geocode(clean_addr)
        if loc: return [loc.latitude, loc.longitude]
    except Exception: pass
    return None

def fetch_notion():
    print("--- Recuperation Notion...")
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
    r = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers)
    if r.status_code != 200: 
        print(f"Erreur Notion : {r.text}")
        return []
    
    locations = []
    results = r.json().get("results", [])
    print(f"--- {len(results)} pages trouv\u00e9es dans Notion.")
    
    for page in results:
        p = page.get("properties", {})
        
        # Nom
        name_obj = p.get("Name", {}).get("title", [])
        name = name_obj[0].get("plain_text", "Sans nom") if name_obj else "Sans nom"
        
        # Adresse
        addr_obj = p.get("Address", {}).get("rich_text", [])
        addr = "".join([t.get("plain_text", "") for t in addr_obj])
        
        # Ville
        loc_p = p.get("Location", {})
        city = loc_p.get("select", {}).get("name", "Ta\u00efwan") if loc_p and isinstance(loc_p, dict) and loc_p.get("select") else "Ta\u00efwan"
        
        # Description
        desc_obj = p.get("Description", {}).get("rich_text", [])
        desc = "".join([t.get("plain_text", "") for t in desc_obj])[:150]
        # Nettoyage Unicode pour JS
        desc = "".join(c for c in desc if ord(c) < 65536)

        if addr:
            print(f"--- Localisation de {name}...")
            coords = get_coords(addr)
            if coords:
                locations.append({"name": name, "city": city, "coords": coords, "desc": desc})
                time.sleep(0.5)
    return locations

def update_github_file(content):
    """Met \u00e0 jour index.html sur GitHub via API"""
    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{FILENAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # R\u00e9cup\u00e9rer le SHA actuel
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    
    encoded = base64.b64encode(content.encode("utf-8", "replace")).decode("utf-8")
    data = {"message": "Auto-sync from Notion via GitHub Action", "content": encoded}
    if sha: data["sha"] = sha
    
    res = requests.put(url, headers=headers, json=data)
    if res.status_code in [200, 201]:
        print("--- GitHub mis \u00e0 jour !")
    else:
        print(f"--- Erreur GitHub : {res.text}")

def main():
    if not NOTION_TOKEN or not DATABASE_ID:
        print("Erreur : Environnement manquant (NOTION_TOKEN ou DATABASE_ID)")
        return

    locs = fetch_notion()
    if not locs:
        print("--- Aucun lieu localisable trouv\u00e9.")
        return

    # Generation HTML
    html_json = json.dumps(locs, ensure_ascii=False)
    html = """<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
    <title>Taiwan Live Map</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root { --p: #ff4757; --bg: #0f1116; --g: rgba(255, 255, 255, 0.1); }
        body, html { margin: 0; padding: 0; height: 100%; font-family: 'Outfit'; background: var(--bg); color: white; overflow: hidden; }
        #map { height: 100vh; width: 100%; z-index: 1; }
        .overlay { position: absolute; top: 15px; left: 15px; z-index: 1000; width: 280px; max-height: calc(100vh - 30px); background: rgba(15,17,22,0.9); backdrop-filter: blur(10px); border-radius: 15px; padding: 15px; display: flex; flex-direction: column; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { margin: 0; font-size: 18px; color: var(--p); }
        .search { width: 100%; padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--g); border-radius: 8px; color: white; margin: 10px 0; outline: none; }
        .list { flex-grow: 1; overflow-y: auto; }
        .item { padding: 8px; border-bottom: 1px solid var(--g); cursor: pointer; transition: 0.2s; }
        .item:hover { background: rgba(255,255,255,0.05); }
        .tag { display: inline-block; padding: 2px 5px; font-size: 9px; background: #57606f; border-radius: 4px; margin-top: 3px; }
        .tag-taipei { background: #57606f; } .tag-kaohsiung { background: #ffa502; } .tag-alishan { background: #2ed573; }
        .leaflet-popup-content-wrapper { background: #0f1116; color: white; border-radius: 8px; }
        .leaflet-popup-tip { background: #0f1116; }
        ::-webkit-scrollbar { width: 3px; } ::-webkit-scrollbar-thumb { background: var(--g); }
    </style></head>
    <body><div class="overlay"><h1>\ud83c\uddf9\ud83c\uddfc Taiwan Travel Map</h1><p style="font-size: 10px; color: #aaa;">Sync : """ + time.strftime("%H:%M") + """</p>
    <input type="text" class="search" placeholder="Rechercher..." id="s"><div class="list" id="l"></div></div><div id="map"></div>
    <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const color = { "Ta\u00efpei": "#57606f", "Kaohsiung": "#ffa502", "Alishan": "#2ed573" };
        const map = L.map('map', {attributionControl: false, zoomControl: false}).setView([23.9, 120.9], 8);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(map);
        const data = """ + html_json + """;
        const container = document.getElementById('l');
        data.forEach(x => {
            const m = L.circleMarker(x.coords, { radius: 6, fillColor: color[x.city] || "red", color: "white", weight: 1, fillOpacity: 0.8 }).addTo(map);
            m.bindPopup("<strong>"+x.name+"</strong><br><small>"+x.desc+"</small>");
            const div = document.createElement('div'); div.className = 'item';
            div.innerHTML = "<div>"+x.name+"</div><span class='tag tag-"+x.city.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, "")+"'>"+x.city+"</span>";
            div.onclick = () => { map.flyTo(x.coords, 14); m.openPopup(); }; container.appendChild(div);
        });
        document.getElementById('s').oninput = (e) => {
            const v = e.target.value.toLowerCase();
            document.querySelectorAll('.item').forEach(i => { i.style.display = i.innerText.toLowerCase().includes(v) ? 'block' : 'none'; });
        };
    </script></body></html>"""

    update_github_file(html)

if __name__ == "__main__":
    main()
