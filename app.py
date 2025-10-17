from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import urllib.request
import json
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = '¡cambia_este_secreto_por_algo_seguro!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/MiCombiBackend'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
        paradas = [{
            'name': p.parada.nombre,
            'lat': float(p.parada.latitud),
            'lon': float(p.parada.longitud)
        } for p in ruta.paradas]
        
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
