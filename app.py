# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request
import urllib.request
import json
import os
import xml.etree.ElementTree as ET
import math

app = Flask(__name__)

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371 # Earth radius in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2) * math.sin(dLon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def parse_kml(file_path):
    """Parses a KML file to extract route name, coordinates, and stops."""
    ns = {
        'kml': 'http://www.opengis.net/kml/2.2',
        'gx': 'http://www.google.com/kml/ext/2.2'
    }
    
    try:
        parser = ET.XMLParser(encoding='utf-8')
        tree = ET.parse(file_path, parser)
        root = tree.getroot()
        
        route_name = os.path.splitext(os.path.basename(file_path))[0].replace('_', ' ').replace('-', ' ').title()
        
        route_coordinates = []
        track_coords_elements = root.findall('.//gx:Track/gx:coord', ns)
        if not track_coords_elements:
            track_coords_elements = root.findall('.//kml:Placemark[.//kml:LineString]/kml:LineString/kml:coordinates', ns)
            if track_coords_elements:
                coords_text = track_coords_elements[0].text.strip()
                for coord_pair in coords_text.split():
                    parts = coord_pair.split(',')
                    if len(parts) >= 2:
                        lon, lat = map(float, parts[:2])
                        route_coordinates.append([lat, lon])
        else:
            for coord in track_coords_elements:
                parts = coord.text.split()
                if len(parts) >= 2:
                    lon, lat = map(float, parts[:2])
                    route_coordinates.append([lat, lon])

        stops = []
        for placemark in root.findall('.//kml:Placemark', ns):
            name_elem = placemark.find('kml:name', ns)
            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            
            if name_elem is not None and name_elem.text and point_elem is not None:
                if 'ida' not in name_elem.text.lower() and 'regreso' not in name_elem.text.lower():
                    coords = point_elem.text.strip().split(',')
                    if len(coords) >= 2:
                        stops.append({
                            'name': name_elem.text.strip(),
                            'lat': float(coords[1]),
                            'lon': float(coords[0])
                        })
        
        # Sort stops based on their proximity to the route coordinates
        if stops and route_coordinates:
            sorted_stops_with_order = []
            for stop in stops:
                min_dist = float('inf')
                closest_coord_index = -1
                for i, coord in enumerate(route_coordinates):
                    dist = haversine_distance(stop['lat'], stop['lon'], coord[0], coord[1])
                    if dist < min_dist:
                        min_dist = dist
                        closest_coord_index = i
                if closest_coord_index != -1:
                    sorted_stops_with_order.append({'stop': stop, 'order': closest_coord_index})
            
            sorted_stops_with_order.sort(key=lambda x: x['order'])
            stops = [item['stop'] for item in sorted_stops_with_order]

        return {
            'name': route_name,
            'coordinates': route_coordinates,
            'stops': stops
        }

    except Exception as e:
        print(f"  -> ERROR: Ocurrió un error al procesar {os.path.basename(file_path)}: {e}")
        return None

def load_kml_data():
    """Loads all KML files from the assets directory and assigns properties."""
    print("--- Iniciando la carga de datos KML ---")
    kml_dir = os.path.join('assets', 'kml')
    all_routes = []
    route_id_counter = 1
    
    colors = ['#FF0A0A', '#0A0AFF', '#0AFFA0', '#FFA00A', '#A00AFFA', '#FF00FF']

    if not os.path.exists(kml_dir):
        print(f"ADVERTENCIA: El directorio KML no existe en: {kml_dir}")
        return []

    for root_dir, _, files in os.walk(kml_dir):
        print(f"Escaneando directorio: {root_dir}")
        for file in sorted(files):
            if file.endswith('.kml'):
                file_path = os.path.join(root_dir, file)
                print(f"Procesando archivo KML: {file_path}")
                route_data = parse_kml(file_path)
                if route_data and route_data['coordinates']:
                    print(f"  -> Éxito: Ruta '{route_data['name']}' cargada con {len(route_data['coordinates'])} coordenadas y {len(route_data['stops'])} paradas.")
                    route_data['id'] = route_id_counter
                    route_data['color'] = colors[(route_id_counter - 1) % len(colors)]
                    route_data['cost'] = 8.00
                    route_data['schedule'] = "06:00 - 22:00"
                    route_data['description'] = f"Ruta {route_data['name']}"
                    all_routes.append(route_data)
                    route_id_counter += 1
                else:
                    print(f"  -> ADVERTENCIA: No se pudieron extraer datos o coordenadas de la ruta para el archivo: {file}")
    
    print(f"--- Carga KML finalizada. {len(all_routes)} rutas cargadas. ---")
    return all_routes

KML_ROUTES = load_kml_data()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/map')
def map_app():
    return render_template('map.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/api/routes')
def get_kml_routes():
    if not KML_ROUTES:
        return jsonify({"error": "No KML routes loaded."}), 404
    return jsonify(KML_ROUTES)

@app.route('/api/stops')
def get_all_stops_from_kml():
    all_stops = []
    seen_stops = set()
    stop_id_counter = 1
    for route in KML_ROUTES:
        for stop in route.get('stops', []):
            stop_identifier = (stop['name'], stop['lat'], stop['lon'])
            if stop_identifier not in seen_stops:
                all_stops.append({
                    'id': stop_id_counter,
                    'name': stop['name'],
                    'lat': stop['lat'],
                    'lon': stop['lon']
                })
                seen_stops.add(stop_identifier)
                stop_id_counter += 1
    return jsonify(all_stops)

@app.route('/api/reverse-geocode')
def reverse_geocode_api():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({"error": "Latitud y longitud son requeridas"}), 400

    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
    req = urllib.request.Request(url, headers={'User-Agent': 'CombiMapApp/1.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.load(response)
            address = data.get('display_name', 'Ubicación no encontrada')
            return jsonify({"address": address})
    except Exception as e:
        print(f"Error con la API de Nominatim: {e}")
        return jsonify({"error": "No se pudo obtener la dirección"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)