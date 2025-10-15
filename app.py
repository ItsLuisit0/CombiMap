from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
import re
import math
import json
import urllib.request

# --- Configuración de la Aplicación ---
app = Flask(__name__)

# Configuración de la base de datos
DB_USER = 'root'
DB_PASS = 'root'
DB_HOST = 'localhost'
DB_PORT = '3306'
DB_NAME = 'MiCombiBackend'

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Modelos de la Base de Datos (SQLAlchemy) ---

ruta_paradas_association = db.Table('ruta_paradas',
    db.Model.metadata,
    db.Column('ruta_id', db.Integer, db.ForeignKey('rutas.id')), 
    db.Column('parada_id', db.Integer, db.ForeignKey('paradas.id'))
)

class Base(db.Model):
    __tablename__ = 'bases'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    latitud = db.Column(db.Numeric(10, 8), nullable=False)
    longitud = db.Column(db.Numeric(11, 8), nullable=False)
    descripcion = db.Column(db.Text)
    imagenes = db.Column(db.JSON)
    color = db.Column(db.String(7))
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

class RutaCoordenadas(db.Model):
    __tablename__ = 'ruta_coordenadas'
    id = db.Column(db.Integer, primary_key=True)
    ruta_id = db.Column(db.Integer, db.ForeignKey('rutas.id'), nullable=False)
    latitud = db.Column(db.Numeric(10, 8), nullable=False)
    longitud = db.Column(db.Numeric(11, 8), nullable=False)
    orden = db.Column(db.Integer, nullable=False)

class Parada(db.Model):
    __tablename__ = 'paradas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    latitud = db.Column(db.Numeric(10, 8), nullable=False)
    longitud = db.Column(db.Numeric(11, 8), nullable=False)
    descripcion = db.Column(db.Text)
    tipo = db.Column(db.Enum('principal', 'secundaria'), default='secundaria')
    imagenes = db.Column(db.JSON)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

class Ruta(db.Model):
    __tablename__ = 'rutas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), nullable=False)
    base_inicio_id = db.Column(db.Integer, db.ForeignKey('bases.id'))
    base_fin_id = db.Column(db.Integer, db.ForeignKey('bases.id'))
    horario_inicio = db.Column(db.Time, nullable=True)
    horario_fin = db.Column(db.Time, nullable=True)
    costo = db.Column(db.Numeric(6, 2), nullable=True)
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    coordenadas = db.relationship('RutaCoordenadas', backref='ruta', lazy=True, order_by='RutaCoordenadas.orden')
    paradas = db.relationship('Parada', secondary=ruta_paradas_association, lazy='subquery', backref=db.backref('rutas', lazy=True))

# --- Lógica de Búsqueda y Helpers ---

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2) * math.sin(dLon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_nearest_stop(lat, lon):
    all_stops = Parada.query.all()
    if not all_stops:
        return None
    return min(all_stops, key=lambda stop: haversine_distance(lat, lon, float(stop.latitud), float(stop.longitud)))

# --- Rutas de la API y la Aplicación ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/map')
def map_app():
    return render_template('map.html')

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/api/stops')
def get_all_stops():
    try:
        stops = Parada.query.order_by(Parada.nombre).all()
        stops_data = [{
            'id': stop.id,
            'name': stop.nombre,
            'lat': float(stop.latitud),
            'lon': float(stop.longitud)
        } for stop in stops]
        return jsonify(stops_data)
    except Exception as e:
        print(f"ERROR en /api/stops: {e}")
        return jsonify({"error": str(e)}), 500

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

@app.route('/api/route/<int:route_id>/nearest-stop')
def find_nearest_stop_for_route(route_id):
    lat_str = request.args.get('lat')
    lon_str = request.args.get('lon')
    if not lat_str or not lon_str:
        return jsonify({"error": "Latitud y longitud son requeridas"}), 400

    try:
        user_lat, user_lon = float(lat_str), float(lon_str)
        ruta = Ruta.query.get_or_404(route_id)
        
        if not ruta.paradas:
            return jsonify({"error": "La ruta no tiene paradas registradas"}), 404

        nearest_parada = min(ruta.paradas, key=lambda parada: haversine_distance(user_lat, user_lon, float(parada.latitud), float(parada.longitud)))
        
        return jsonify({
            'id': nearest_parada.id,
            'name': nearest_parada.nombre,
            'lat': float(nearest_parada.latitud),
            'lon': float(nearest_parada.longitud)
        })

    except Exception as e:
        print(f"Error en nearest-stop: {e}")
        return jsonify({"error": "Error interno al procesar la solicitud"}), 500

@app.route('/api/routes')
def get_db_routes():
    try:
        rutas_from_db = Ruta.query.order_by(Ruta.id).all()
        routes_data = []
        for ruta in rutas_from_db:
            coords_list = [[float(c.latitud), float(c.longitud)] for c in ruta.coordenadas]
            stops_list = [{'name': p.nombre, 'lat': float(p.latitud), 'lon': float(p.longitud)} for p in ruta.paradas]
            costo_val = float(ruta.costo) if ruta.costo is not None else None
            schedule_val = 'No disponible'
            if ruta.horario_inicio and ruta.horario_fin:
                schedule_val = f'{ruta.horario_inicio.strftime("%H:%M")} - {ruta.horario_fin.strftime("%H:%M")}'

            routes_data.append({
                'id': ruta.id, 'name': ruta.nombre, 'color': ruta.color, 'cost': costo_val,
                'schedule': schedule_val, 'description': ruta.descripcion,
                'coordinates': coords_list, 'stops': stops_list
            })
        return jsonify(routes_data)
    except Exception as e:
        print(f"ERROR en /api/routes: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/search')
def search_routes_api():
    origin_query = request.args.get('origin', '').strip()
    dest_query = request.args.get('destination', '').strip()

    if not origin_query or not dest_query:
        return jsonify({"error": "Origen y destino son requeridos"}), 400

    origin_stops = []
    geo_match = re.match(r"Mi ubicación \((.+), (.+)\)", origin_query)
    if geo_match:
        lat, lon = float(geo_match.group(1)), float(geo_match.group(2))
        nearest_stop = find_nearest_stop(lat, lon)
        if nearest_stop:
            origin_stops.append(nearest_stop)
    else:
        origin_stops = Parada.query.filter(Parada.nombre.like(f"%{origin_query}%")).all()

    dest_stops = Parada.query.filter(Parada.nombre.like(f"%{dest_query}%")).all()

    if not origin_stops or not dest_stops:
        return jsonify([])

    origin_stop_ids = [p.id for p in origin_stops]
    dest_stop_ids = [p.id for p in dest_stops]

    matching_routes = Ruta.query.filter(
        Ruta.paradas.any(Parada.id.in_(origin_stop_ids))
    ).filter(
        Ruta.paradas.any(Parada.id.in_(dest_stop_ids))
    ).all()

    routes_data = []
    for ruta in matching_routes:
        coords_list = [[float(c.latitud), float(c.longitud)] for c in ruta.coordenadas]
        stops_list = [{'name': p.nombre, 'lat': float(p.latitud), 'lon': float(p.longitud)} for p in ruta.paradas]
        costo_val = float(ruta.costo) if ruta.costo is not None else None
        schedule_val = 'No disponible'
        if ruta.horario_inicio and ruta.horario_fin:
            schedule_val = f'{ruta.horario_inicio.strftime("%H:%M")} - {ruta.horario_fin.strftime("%H:%M")}'

        routes_data.append({
            'id': ruta.id, 'name': ruta.nombre, 'color': ruta.color, 'cost': costo_val,
            'schedule': schedule_val, 'description': ruta.descripcion,
            'coordinates': coords_list, 'stops': stops_list
        })

    return jsonify(routes_data)

# --- Punto de Entrada de la Aplicación ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)