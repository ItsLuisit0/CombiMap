from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///combi_map.db' 
db = SQLAlchemy(app)

class Route(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    color = db.Column(db.String(7), nullable=True)
    cost = db.Column(db.Float, default=0.0)
    schedule = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Route {self.name}>'

class Stop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'), nullable=False)
    route = db.relationship('Route', backref='stops')

    def __repr__(self):
        return f'<Stop {self.name}>'

# CRUD operations
def create_db():
    with app.app_context():
        db.create_all()

def create_route(name, color, cost, schedule, description):
    with app.app_context():
        new_route = Route(name=name, color=color, cost=cost, schedule=schedule, description=description)
        db.session.add(new_route)
        db.session.commit()
        return new_route

def read_routes():
    with app.app_context():
        return Route.query.all()

def update_route(id, name=None, color=None, cost=None, schedule=None, description=None):
    with app.app_context():
        route = Route.query.get(id)
        if route:
            if name: route.name = name
            db.session.commit()
            return route
        return None

if __name__ == '__main__':
    create_db()