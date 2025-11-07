from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import urllib.request
import json
import jwt
import datetime
from functools import wraps
import os
from xml.etree import ElementTree as ET
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'combimap_secret_key_2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root@localhost/MiCombiBackend'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'kml', 'kmz'}

# Crear carpeta de uploads si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# --- Modelos de la Base de Datos ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Base(db.Model):
    __tablename__ = 'bases'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    latitud = db.Column(db.Numeric(10, 8), nullable=False)
    longitud = db.Column(db.Numeric(11, 8), nullable=False)
    descripcion = db.Column(db.Text)
    imagenes = db.Column(db.JSON)
    color = db.Column(db.String(7))

class Ruta(db.Model):
    __tablename__ = 'rutas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), nullable=False)
    base_inicio_id = db.Column(db.Integer, db.ForeignKey('bases.id'))
    base_fin_id = db.Column(db.Integer, db.ForeignKey('bases.id'))
    horario_inicio = db.Column(db.Time)
    horario_fin = db.Column(db.Time)
    costo = db.Column(db.Numeric(6, 2))
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, default=True)
    
    base_inicio = db.relationship('Base', foreign_keys=[base_inicio_id])
    base_fin = db.relationship('Base', foreign_keys=[base_fin_id])
    coordenadas = db.relationship('RutaCoordenada', backref='ruta', order_by='RutaCoordenada.orden', cascade="all, delete-orphan")
    paradas = db.relationship('RutaParada', backref='ruta', order_by='RutaParada.orden', cascade="all, delete-orphan")

class Parada(db.Model):
    __tablename__ = 'paradas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    latitud = db.Column(db.Numeric(10, 8), nullable=False)
    longitud = db.Column(db.Numeric(11, 8), nullable=False)
    descripcion = db.Column(db.Text)
    tipo = db.Column(db.Enum('principal', 'secundaria'), default='secundaria')
    imagenes = db.Column(db.JSON)

class RutaCoordenada(db.Model):
    __tablename__ = 'ruta_coordenadas'
    id = db.Column(db.Integer, primary_key=True)
    ruta_id = db.Column(db.Integer, db.ForeignKey('rutas.id', ondelete='CASCADE'), nullable=False)
    latitud = db.Column(db.Numeric(10, 8), nullable=False)
    longitud = db.Column(db.Numeric(11, 8), nullable=False)
    orden = db.Column(db.Integer, nullable=False)

class RutaParada(db.Model):
    __tablename__ = 'ruta_paradas'
    id = db.Column(db.Integer, primary_key=True)
    ruta_id = db.Column(db.Integer, db.ForeignKey('rutas.id', ondelete='CASCADE'), nullable=False)
    parada_id = db.Column(db.Integer, db.ForeignKey('paradas.id', ondelete='CASCADE'), nullable=False)
    orden = db.Column(db.Integer, nullable=False)
    parada = db.relationship('Parada')

# --- Decorador de Autenticación ---

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']

        if not token:
            return jsonify({'message': 'Token es requerido'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
        except Exception as e:
            return jsonify({'message': 'Token es inválido', 'error': str(e)}), 401

        return f(current_user, *args, **kwargs)
    return decorated

# --- Rutas de la Aplicación ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/map')
def map_app():
    return render_template('map.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/admin/login')
def admin_login_page():
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
def admin_dashboard_page():
    return render_template('admin/dashboard.html')

@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')
    print(f"New contact form submission:\nName: {name}\nEmail: {email}\nMessage: {message}")
    return "Message received!", 200

# --- API para Ciudadanos ---

@app.route('/api/routes')
def get_routes():
    rutas = Ruta.query.filter_by(activa=True).all()
    rutas_data = []
    for ruta in rutas:
        coordenadas = [[float(c.latitud), float(c.longitud)] for c in ruta.coordenadas]
        
        # Obtener paradas asociadas a la ruta
        paradas = [{
            'name': p.parada.nombre,
            'lat': float(p.parada.latitud),
            'lon': float(p.parada.longitud)
        } for p in ruta.paradas]
        
        # Si no hay paradas pero sí coordenadas, crear paradas virtuales desde las coordenadas
        if not paradas and coordenadas:
            # Parada de inicio (primera coordenada)
            if len(coordenadas) > 0:
                paradas.append({
                    'name': f'Inicio: {ruta.nombre}',
                    'lat': coordenadas[0][0],
                    'lon': coordenadas[0][1]
                })
            # Parada de fin (última coordenada)
            if len(coordenadas) > 1:
                paradas.append({
                    'name': f'Final: {ruta.nombre}',
                    'lat': coordenadas[-1][0],
                    'lon': coordenadas[-1][1]
                })
        
        rutas_data.append({
            'id': ruta.id,
            'name': ruta.nombre,
            'color': ruta.color,
            'costo': float(ruta.costo) if ruta.costo else None,
            'horario': f"{ruta.horario_inicio.strftime('%H:%M')} - {ruta.horario_fin.strftime('%H:%M')}" if ruta.horario_inicio and ruta.horario_fin else None,
            'descripcion': ruta.descripcion,
            'coordinates': coordenadas,
            'stops': paradas
        })
    return jsonify(rutas_data)

@app.route('/api/stops')
def get_all_stops():
    paradas = Parada.query.all()
    paradas_data = [{
        'id': p.id,
        'name': p.nombre,
        'lat': float(p.latitud),
        'lon': float(p.longitud)
    } for p in paradas]
    return jsonify(paradas_data)

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

# --- API para Administradores ---

@app.route('/api/login', methods=['POST'])
def login():
    auth = request.json
    if not auth or not auth.get('username') or not auth.get('password'):
        return jsonify({'message': 'No se pudo verificar'}), 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    user = User.query.filter_by(username=auth.get('username')).first()

    if not user or not user.check_password(auth.get('password')):
        return jsonify({'message': 'No se pudo verificar'}), 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({'token': token})

@app.route('/api/admin/routes', methods=['POST'])
@token_required
def create_route(current_user):
    data = request.get_json()
    if not data or not data.get('name') or not data.get('color'):
        return jsonify({'message': 'Missing data'}), 400

    new_route = Ruta(
        nombre=data['name'],
        color=data['color'],
        descripcion=data.get('description'),
        costo=data.get('cost'),
        horario_inicio=datetime.time.fromisoformat(data['schedule_start']) if data.get('schedule_start') else None,
        horario_fin=datetime.time.fromisoformat(data['schedule_end']) if data.get('schedule_end') else None,
        activa=data.get('active', True)
    )
    db.session.add(new_route)
    db.session.commit()

    if data.get('coordinates'):
        for i, coord in enumerate(data['coordinates']):
            new_coord = RutaCoordenada(
                ruta_id=new_route.id,
                latitud=coord[0],
                longitud=coord[1],
                orden=i
            )
            db.session.add(new_coord)
    
    db.session.commit()

    return jsonify({'message': 'New route created!', 'id': new_route.id}), 201

@app.route('/api/admin/routes', methods=['GET'])
@token_required
def get_admin_routes(current_user):
    rutas = Ruta.query.all()
    rutas_data = []
    for ruta in rutas:
        rutas_data.append({
            'id': ruta.id,
            'name': ruta.nombre,
            'color': ruta.color,
            'active': ruta.activa
        })
    return jsonify(rutas_data)

@app.route('/api/admin/routes/<int:route_id>', methods=['GET'])
@token_required
def get_admin_route(current_user, route_id):
    ruta = Ruta.query.get_or_404(route_id)
    coordenadas = [[float(c.latitud), float(c.longitud)] for c in ruta.coordenadas]
    paradas = [{
        'id': p.parada.id,
        'name': p.parada.nombre,
        'lat': float(p.parada.latitud),
        'lon': float(p.parada.longitud)
    } for p in ruta.paradas]

    route_data = {
        'id': ruta.id,
        'name': ruta.nombre,
        'color': ruta.color,
        'cost': float(ruta.costo) if ruta.costo else None,
        'schedule_start': ruta.horario_inicio.isoformat() if ruta.horario_inicio else None,
        'schedule_end': ruta.horario_fin.isoformat() if ruta.horario_fin else None,
        'description': ruta.descripcion,
        'active': ruta.activa,
        'coordinates': coordenadas,
        'stops': paradas
    }
    return jsonify(route_data)

@app.route('/api/admin/routes/<int:route_id>', methods=['PUT'])
@token_required
def update_route(current_user, route_id):
    ruta = Ruta.query.get_or_404(route_id)
    data = request.get_json()

    ruta.nombre = data.get('name', ruta.nombre)
    ruta.color = data.get('color', ruta.color)
    ruta.descripcion = data.get('description', ruta.descripcion)
    ruta.costo = data.get('cost', ruta.costo)
    ruta.horario_inicio = datetime.time.fromisoformat(data['schedule_start']) if data.get('schedule_start') else ruta.horario_inicio
    ruta.horario_fin = datetime.time.fromisoformat(data['schedule_end']) if data.get('schedule_end') else ruta.horario_fin
    ruta.activa = data.get('active', ruta.activa)

    if 'coordinates' in data:
        # Delete old coordinates
        RutaCoordenada.query.filter_by(ruta_id=ruta.id).delete()
        # Add new coordinates
        for i, coord in enumerate(data['coordinates']):
            new_coord = RutaCoordenada(
                ruta_id=ruta.id,
                latitud=coord[0],
                longitud=coord[1],
                orden=i
            )
            db.session.add(new_coord)

    db.session.commit()
    return jsonify({'message': 'Route updated!'})

@app.route('/api/admin/routes/<int:route_id>', methods=['DELETE'])
@token_required
def delete_route(current_user, route_id):
    ruta = Ruta.query.get_or_404(route_id)
    db.session.delete(ruta)
    db.session.commit()
    return jsonify({'message': 'Route deleted!'})

@app.route('/api/admin/stops', methods=['POST'])
@token_required
def create_stop(current_user):
    data = request.get_json()
    if not data or not data.get('name') or not data.get('lat') or not data.get('lon'):
        return jsonify({'message': 'Missing data'}), 400

    new_stop = Parada(
        nombre=data['name'],
        latitud=data['lat'],
        longitud=data['lon'],
        descripcion=data.get('description'),
        tipo=data.get('type', 'secundaria')
    )
    db.session.add(new_stop)
    db.session.commit()

    return jsonify({'message': 'New stop created!', 'id': new_stop.id}), 201

@app.route('/api/admin/stops/<int:stop_id>', methods=['PUT'])
@token_required
def update_stop(current_user, stop_id):
    stop = Parada.query.get_or_404(stop_id)
    data = request.get_json()

    stop.nombre = data.get('name', stop.nombre)
    stop.latitud = data.get('lat', stop.latitud)
    stop.longitud = data.get('lon', stop.longitud)
    stop.descripcion = data.get('description', stop.descripcion)
    stop.tipo = data.get('type', stop.tipo)

    db.session.commit()
    return jsonify({'message': 'Stop updated!'})

@app.route('/api/admin/stops/<int:stop_id>', methods=['DELETE'])
@token_required
def delete_stop(current_user, stop_id):
    stop = Parada.query.get_or_404(stop_id)
    db.session.delete(stop)
    db.session.commit()
    return jsonify({'message': 'Stop deleted!'})

@app.route('/api/admin/routes/<int:route_id>/stops', methods=['POST'])
@token_required
def add_stop_to_route(current_user, route_id):
    data = request.get_json()
    if not data or not data.get('stop_id') or not data.get('order'):
        return jsonify({'message': 'Missing data'}), 400

    route = Ruta.query.get_or_404(route_id)
    stop = Parada.query.get_or_404(data['stop_id'])

    route_stop = RutaParada(
        ruta_id=route.id,
        parada_id=stop.id,
        orden=data['order']
    )
    db.session.add(route_stop)
    db.session.commit()

    return jsonify({'message': 'Stop added to route!'})

@app.route('/api/admin/routes/<int:route_id>/stops/<int:stop_id>', methods=['DELETE'])
@token_required
def remove_stop_from_route(current_user, route_id, stop_id):
    route_stop = RutaParada.query.filter_by(ruta_id=route_id, parada_id=stop_id).first_or_404()
    db.session.delete(route_stop)
    db.session.commit()
    return jsonify({'message': 'Stop removed from route!'})

# --- Funciones Auxiliares para KML ---

def allowed_file(filename):
    """Verifica si el archivo tiene una extensión permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def parse_color_from_kml(kml_color):
    """Convierte color KML (aabbggrr) a formato web (#rrggbb)"""
    if not kml_color or len(kml_color) < 6:
        return '#FF0000'
    try:
        bb = kml_color[-2:]
        gg = kml_color[-4:-2]
        rr = kml_color[-6:-4]
        return f'#{rr}{gg}{bb}'.upper()
    except:
        return '#FF0000'

def parse_coordinates(coord_string):
    """Parsea cadena de coordenadas KML"""
    coordinates = []
    coord_string = coord_string.strip()
    points = re.split(r'\s+', coord_string)
    
    for point in points:
        if not point:
            continue
        parts = point.split(',')
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coordinates.append([lat, lon])
            except ValueError:
                continue
    
    return coordinates

def extract_placemarks_from_kml(kml_file_path):
    """Extrae placemarks del archivo KML"""
    KML_NAMESPACE = {
        'kml': 'http://www.opengis.net/kml/2.2',
        'gx': 'http://www.google.com/kml/ext/2.2'
    }
    
    try:
        tree = ET.parse(kml_file_path)
        root = tree.getroot()
        placemarks = []
        
        for placemark in root.findall('.//kml:Placemark', KML_NAMESPACE):
            data = {
                'name': None,
                'description': None,
                'color': '#FF0000',
                'type': None,
                'coordinates': []
            }
            
            # Nombre
            name_elem = placemark.find('kml:name', KML_NAMESPACE)
            if name_elem is not None and name_elem.text:
                data['name'] = name_elem.text.strip()
            
            # Descripción
            desc_elem = placemark.find('kml:description', KML_NAMESPACE)
            if desc_elem is not None and desc_elem.text:
                data['description'] = desc_elem.text.strip()
            
            # Color desde LineStyle
            line_style = placemark.find('.//kml:LineStyle/kml:color', KML_NAMESPACE)
            if line_style is not None and line_style.text:
                data['color'] = parse_color_from_kml(line_style.text)
            
            # Color desde PolyStyle
            poly_style = placemark.find('.//kml:PolyStyle/kml:color', KML_NAMESPACE)
            if poly_style is not None and poly_style.text:
                data['color'] = parse_color_from_kml(poly_style.text)
            
            # LineString (rutas de Google My Maps)
            linestring = placemark.find('.//kml:LineString/kml:coordinates', KML_NAMESPACE)
            if linestring is not None and linestring.text:
                data['type'] = 'LineString'
                data['coordinates'] = parse_coordinates(linestring.text)
            
            # gx:Track (rutas de GPS Tracker como Geo Tracker)
            gx_track = placemark.find('.//gx:Track', KML_NAMESPACE)
            if gx_track is not None and not data['coordinates']:
                track_coords = []
                for coord_elem in gx_track.findall('gx:coord', KML_NAMESPACE):
                    if coord_elem.text:
                        parts = coord_elem.text.strip().split()
                        if len(parts) >= 2:
                            try:
                                lon = float(parts[0])
                                lat = float(parts[1])
                                track_coords.append([lat, lon])
                            except ValueError:
                                continue
                if track_coords:
                    data['type'] = 'LineString'
                    data['coordinates'] = track_coords
            
            # MultiTrack (para tracks GPS con múltiples segmentos)
            multi_track = placemark.find('.//gx:MultiTrack', KML_NAMESPACE)
            if multi_track is not None and not data['coordinates']:
                all_track_coords = []
                for track in multi_track.findall('.//gx:Track', KML_NAMESPACE):
                    for coord_elem in track.findall('gx:coord', KML_NAMESPACE):
                        if coord_elem.text:
                            parts = coord_elem.text.strip().split()
                            if len(parts) >= 2:
                                try:
                                    lon = float(parts[0])
                                    lat = float(parts[1])
                                    all_track_coords.append([lat, lon])
                                except ValueError:
                                    continue
                if all_track_coords:
                    data['type'] = 'LineString'
                    data['coordinates'] = all_track_coords
            
            # Point (paradas)
            point = placemark.find('.//kml:Point/kml:coordinates', KML_NAMESPACE)
            if point is not None and point.text:
                data['type'] = 'Point'
                coords = parse_coordinates(point.text)
                if coords:
                    data['coordinates'] = coords[0]
            
            # MultiGeometry
            multi_geom = placemark.find('.//kml:MultiGeometry', KML_NAMESPACE)
            if multi_geom is not None and not data['coordinates']:
                all_coords = []
                for line in multi_geom.findall('.//kml:LineString/kml:coordinates', KML_NAMESPACE):
                    if line.text:
                        all_coords.extend(parse_coordinates(line.text))
                if all_coords:
                    data['type'] = 'LineString'
                    data['coordinates'] = all_coords
            
            if data['name'] and data['coordinates']:
                placemarks.append(data)
        
        return placemarks
    except Exception as e:
        print(f"Error al parsear KML: {e}")
        return []

def process_kml_data(placemarks):
    """Procesa los placemarks y los guarda en la base de datos"""
    results = {
        'routes_imported': 0,
        'stops_imported': 0,
        'routes': [],
        'stops': [],
        'errors': []
    }
    
    try:
        # Separar rutas y paradas
        routes = [p for p in placemarks if p['type'] == 'LineString']
        stops = [p for p in placemarks if p['type'] == 'Point']
        
        # Primero importar rutas
        route_id_map = {}
        for placemark in routes:
            try:
                new_route = Ruta(
                    nombre=placemark['name'],
                    color=placemark['color'],
                    descripcion=placemark.get('description', ''),
                    costo=8.00,
                    activa=True
                )
                db.session.add(new_route)
                db.session.flush()
                
                # Guardar el ID de la ruta para asociarla con paradas
                route_id_map[placemark['name']] = new_route.id
                
                # Agregar coordenadas
                for i, coord in enumerate(placemark['coordinates']):
                    new_coord = RutaCoordenada(
                        ruta_id=new_route.id,
                        latitud=coord[0],
                        longitud=coord[1],
                        orden=i
                    )
                    db.session.add(new_coord)
                
                db.session.commit()
                results['routes_imported'] += 1
                results['routes'].append({
                    'id': new_route.id,
                    'name': new_route.nombre,
                    'color': new_route.color
                })
            except Exception as e:
                db.session.rollback()
                results['errors'].append(f"Error al importar ruta '{placemark['name']}': {str(e)}")
        
        # Luego importar paradas y asociarlas
        stop_id_map = {}
        for orden, placemark in enumerate(stops):
            try:
                # Verificar si ya existe una parada cercana (mismo nombre o coordenadas similares)
                existing_stop = Parada.query.filter(
                    db.or_(
                        Parada.nombre == placemark['name'],
                        db.and_(
                            db.func.abs(Parada.latitud - placemark['coordinates'][0]) < 0.0001,
                            db.func.abs(Parada.longitud - placemark['coordinates'][1]) < 0.0001
                        )
                    )
                ).first()
                
                if existing_stop:
                    # Usar la parada existente
                    stop_id_map[placemark['name']] = existing_stop.id
                    results['errors'].append(f"Parada '{placemark['name']}' ya existe (ID: {existing_stop.id}), se reutilizará")
                else:
                    # Crear nueva parada
                    new_stop = Parada(
                        nombre=placemark['name'],
                        latitud=placemark['coordinates'][0],
                        longitud=placemark['coordinates'][1],
                        descripcion=placemark.get('description', ''),
                        tipo='secundaria'
                    )
                    db.session.add(new_stop)
                    db.session.flush()
                    
                    stop_id_map[placemark['name']] = new_stop.id
                    results['stops_imported'] += 1
                    results['stops'].append({
                        'id': new_stop.id,
                        'name': new_stop.nombre
                    })
                
                # Asociar parada con TODAS las rutas del KML
                for route_name, route_id in route_id_map.items():
                    # Verificar que no exista ya la asociación
                    existing_relation = RutaParada.query.filter_by(
                        ruta_id=route_id,
                        parada_id=stop_id_map[placemark['name']]
                    ).first()
                    
                    if not existing_relation:
                        ruta_parada = RutaParada(
                            ruta_id=route_id,
                            parada_id=stop_id_map[placemark['name']],
                            orden=orden
                        )
                        db.session.add(ruta_parada)
                
                db.session.commit()
                
            except Exception as e:
                db.session.rollback()
                results['errors'].append(f"Error al importar parada '{placemark['name']}': {str(e)}")
        
        return results
    except Exception as e:
        results['errors'].append(f"Error general: {str(e)}")
        return results

# --- API para Importar KML ---

@app.route('/api/admin/import-kml', methods=['POST'])
@token_required
def import_kml(current_user):
    """Endpoint para subir y procesar archivos KML"""
    if 'file' not in request.files:
        return jsonify({'message': 'No se envió ningún archivo'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'message': 'No se seleccionó ningún archivo'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'message': 'Tipo de archivo no permitido. Solo KML o KMZ'}), 400
    
    try:
        # Guardar archivo
        filename = secure_filename(file.filename)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extraer datos del KML
        placemarks = extract_placemarks_from_kml(filepath)
        
        if not placemarks:
            os.remove(filepath)
            return jsonify({'message': 'No se encontraron elementos válidos en el archivo KML'}), 400
        
        # Procesar datos
        results = process_kml_data(placemarks)
        
        # Opcional: eliminar archivo después de procesar
        # os.remove(filepath)
        
        return jsonify({
            'message': 'Archivo KML procesado exitosamente',
            'routes_imported': results['routes_imported'],
            'stops_imported': results['stops_imported'],
            'routes': results['routes'],
            'stops': results['stops'],
            'errors': results['errors']
        }), 200
    
    except Exception as e:
        return jsonify({'message': f'Error al procesar el archivo: {str(e)}'}), 500

# ===================================================
# ENDPOINT TEMPORAL: Asociar paradas existentes con rutas
# ===================================================

@app.route('/api/admin/fix-route-stops', methods=['POST'])
@token_required
def fix_route_stops(current_user):
    """Asocia las paradas existentes con las rutas (arregla importaciones anteriores)"""
    try:
        # Obtener todas las rutas y paradas
        rutas = Ruta.query.all()
        paradas = Parada.query.all()
        
        results = {
            'associations_created': 0,
            'details': []
        }
        
        # Para cada ruta, asociar TODAS las paradas en orden
        for ruta in rutas:
            # Verificar si ya tiene paradas asociadas
            existing_count = RutaParada.query.filter_by(ruta_id=ruta.id).count()
            
            if existing_count > 0:
                results['details'].append(f"Ruta '{ruta.nombre}' ya tiene {existing_count} paradas, saltando...")
                continue
            
            # Asociar todas las paradas con esta ruta
            for orden, parada in enumerate(paradas):
                ruta_parada = RutaParada(
                    ruta_id=ruta.id,
                    parada_id=parada.id,
                    orden=orden
                )
                db.session.add(ruta_parada)
                results['associations_created'] += 1
            
            results['details'].append(f"Ruta '{ruta.nombre}' asociada con {len(paradas)} paradas")
        
        db.session.commit()
        
        return jsonify({
            'message': 'Asociaciones creadas exitosamente',
            'associations_created': results['associations_created'],
            'details': results['details']
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Error: {str(e)}'}), 500

# ===================================================
# SECCIÓN: PANEL DE ADMINISTRACIÓN CRUD (Rutas y Puntos)
# ===================================================

@app.route('/ver_rutas')
def ver_rutas():
    """Paso 1 READ: Listar todas las rutas"""
    rutas = Ruta.query.all()
    return render_template('rutas.html', rutas=rutas)

@app.route('/nueva_ruta', methods=['GET', 'POST'])
def nueva_ruta():
    """Paso 2 CREATE: Crear nueva ruta"""
    if request.method == 'POST':
        # Obtener datos del formulario
        nombre = request.form.get('nombre')
        color = request.form.get('color')
        descripcion = request.form.get('descripcion', '')
        horario_inicio = request.form.get('horario_inicio')
        horario_fin = request.form.get('horario_fin')
        costo = request.form.get('costo')
        activa = request.form.get('activa') == '1'
        
        # Crear nueva ruta
        nueva = Ruta(
            nombre=nombre,
            color=color,
            descripcion=descripcion if descripcion else None,
            horario_inicio=horario_inicio if horario_inicio else None,
            horario_fin=horario_fin if horario_fin else None,
            costo=float(costo) if costo else None,
            activa=activa
        )
        
        # Guardar en la base de datos
        db.session.add(nueva)
        db.session.commit()
        
        # Redirigir a la página de edición para agregar puntos
        return redirect(url_for('editar_ruta', id=nueva.id))
    
    # GET: Mostrar formulario
    return render_template('formulario_ruta.html')

@app.route('/editar_ruta/<int:id>', methods=['GET', 'POST'])
def editar_ruta(id):
    """Paso 3 UPDATE: Vista Maestro-Detalle para editar ruta"""
    ruta = Ruta.query.get_or_404(id)
    
    if request.method == 'POST':
        # Actualizar datos de la ruta
        ruta.nombre = request.form.get('nombre')
        ruta.color = request.form.get('color')
        ruta.descripcion = request.form.get('descripcion', '')
        
        horario_inicio = request.form.get('horario_inicio')
        horario_fin = request.form.get('horario_fin')
        costo = request.form.get('costo')
        
        ruta.horario_inicio = horario_inicio if horario_inicio else None
        ruta.horario_fin = horario_fin if horario_fin else None
        ruta.costo = float(costo) if costo else None
        ruta.activa = request.form.get('activa') == '1'
        
        # Guardar cambios
        db.session.commit()
        
        # Redirigir a la misma página
        return redirect(url_for('editar_ruta', id=id))
    
    # GET: Mostrar formulario de edición con puntos
    return render_template('editar_ruta.html', ruta=ruta)

@app.route('/agregar_punto/<int:id_ruta>', methods=['POST'])
def agregar_punto(id_ruta):
    """Paso 4 CREATE: Agregar punto de trazado a una ruta"""
    # Obtener datos del formulario
    latitud = request.form.get('latitud')
    longitud = request.form.get('longitud')
    orden = request.form.get('orden')
    
    # Crear nuevo punto
    nuevo_punto = RutaCoordenada(
        ruta_id=id_ruta,
        latitud=float(latitud),
        longitud=float(longitud),
        orden=int(orden)
    )
    
    # Guardar en la base de datos
    db.session.add(nuevo_punto)
    db.session.commit()
    
    # Redirigir de vuelta a la edición de la ruta
    return redirect(url_for('editar_ruta', id=id_ruta))

@app.route('/borrar_punto/<int:id_punto>', methods=['POST'])
def borrar_punto(id_punto):
    """Paso 4 DELETE: Borrar punto de trazado"""
    # Obtener el punto a borrar
    punto = RutaCoordenada.query.get_or_404(id_punto)
    
    # Guardar el id_ruta antes de borrar
    id_ruta = punto.ruta_id
    
    # Borrar y commit
    db.session.delete(punto)
    db.session.commit()
    
    # Redirigir de vuelta a la edición de la ruta
    return redirect(url_for('editar_ruta', id=id_ruta))

# FIN SECCIÓN CRUD

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin')
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print("Usuario 'admin' con contraseña 'admin' creado.")
    app.run(debug=True, port=5000)
