#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para importar datos desde archivos KML al sistema CombiMap
Autor: CombiMap Team
Descripción: Este script lee archivos KML y extrae rutas, coordenadas y paradas
             para importarlas automáticamente a la base de datos.
"""

import sys
import os
from pathlib import Path
from xml.etree import ElementTree as ET
import re
import mysql.connector
from mysql.connector import Error
import json
from datetime import time

# Configuración de la base de datos
DB_CONFIG = {
    'host': 'localhost',
    'database': 'MiCombiBackend',
    'user': 'root',
    'password': ''  # Sin contraseña para phpMyAdmin
}

# Namespace para KML
KML_NAMESPACE = {
    'kml': 'http://www.opengis.net/kml/2.2',
    'gx': 'http://www.google.com/kml/ext/2.2'
}


class KMLImporter:
    """Clase para importar datos desde archivos KML"""
    
    def __init__(self, db_config):
        """Inicializa el importador con la configuración de BD"""
        self.db_config = db_config
        self.connection = None
        self.cursor = None
        
    def connect_db(self):
        """Conecta a la base de datos"""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            if self.connection.is_connected():
                self.cursor = self.connection.cursor()
                print(f"✓ Conectado a MySQL: {self.db_config['database']}")
                return True
        except Error as e:
            print(f"✗ Error al conectar a MySQL: {e}")
            return False
            
    def disconnect_db(self):
        """Desconecta de la base de datos"""
        if self.connection and self.connection.is_connected():
            self.cursor.close()
            self.connection.close()
            print("✓ Desconectado de MySQL")
    
    def parse_color_from_kml(self, kml_color):
        """
        Convierte color KML (aabbggrr) a formato web (#rrggbb)
        KML usa formato: aabbggrr (alpha, blue, green, red)
        Web usa: #rrggbb
        """
        if not kml_color or len(kml_color) < 6:
            return '#FF0000'  # Rojo por defecto
        
        # Extraer componentes (últimos 6 caracteres, invertir orden)
        try:
            # KML: aabbggrr -> extraer bb, gg, rr
            bb = kml_color[-2:]   # Azul
            gg = kml_color[-4:-2] # Verde
            rr = kml_color[-6:-4] # Rojo
            return f'#{rr}{gg}{bb}'.upper()
        except:
            return '#FF0000'
    
    def parse_coordinates(self, coord_string):
        """
        Parsea una cadena de coordenadas KML
        Formato: lon,lat,alt lon,lat,alt ...
        Retorna: [[lat, lon], [lat, lon], ...]
        """
        coordinates = []
        coord_string = coord_string.strip()
        
        # Dividir por espacios o saltos de línea
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
    
    def extract_placemarks(self, kml_file):
        """
        Extrae placemarks (rutas y puntos) del archivo KML
        """
        try:
            tree = ET.parse(kml_file)
            root = tree.getroot()
            
            placemarks = []
            
            # Buscar todos los Placemark
            for placemark in root.findall('.//kml:Placemark', KML_NAMESPACE):
                data = {
                    'name': None,
                    'description': None,
                    'style_url': None,
                    'color': '#FF0000',
                    'type': None,  # 'LineString' o 'Point'
                    'coordinates': []
                }
                
                # Nombre
                name_elem = placemark.find('kml:name', KML_NAMESPACE)
                if name_elem is not None:
                    data['name'] = name_elem.text
                
                # Descripción
                desc_elem = placemark.find('kml:description', KML_NAMESPACE)
                if desc_elem is not None:
                    data['description'] = desc_elem.text
                
                # Estilo (para obtener color)
                style_url = placemark.find('kml:styleUrl', KML_NAMESPACE)
                if style_url is not None:
                    data['style_url'] = style_url.text
                
                # Color desde Style inline
                line_style = placemark.find('.//kml:LineStyle/kml:color', KML_NAMESPACE)
                if line_style is not None:
                    data['color'] = self.parse_color_from_kml(line_style.text)
                
                # Color desde PolyStyle (para polígonos)
                poly_style = placemark.find('.//kml:PolyStyle/kml:color', KML_NAMESPACE)
                if poly_style is not None:
                    data['color'] = self.parse_color_from_kml(poly_style.text)
                
                # LineString (rutas)
                linestring = placemark.find('.//kml:LineString/kml:coordinates', KML_NAMESPACE)
                if linestring is not None:
                    data['type'] = 'LineString'
                    data['coordinates'] = self.parse_coordinates(linestring.text)
                
                # Point (paradas)
                point = placemark.find('.//kml:Point/kml:coordinates', KML_NAMESPACE)
                if point is not None:
                    data['type'] = 'Point'
                    coords = self.parse_coordinates(point.text)
                    if coords:
                        data['coordinates'] = coords[0]  # Solo un punto
                
                # MultiGeometry (puede contener múltiples líneas o puntos)
                multi_geom = placemark.find('.//kml:MultiGeometry', KML_NAMESPACE)
                if multi_geom is not None:
                    all_coords = []
                    for line in multi_geom.findall('.//kml:LineString/kml:coordinates', KML_NAMESPACE):
                        all_coords.extend(self.parse_coordinates(line.text))
                    if all_coords:
                        data['type'] = 'LineString'
                        data['coordinates'] = all_coords
                
                if data['name'] and data['coordinates']:
                    placemarks.append(data)
            
            return placemarks
            
        except Exception as e:
            print(f"✗ Error al parsear KML: {e}")
            return []
    
    def import_route(self, route_data):
        """
        Importa una ruta a la base de datos
        """
        try:
            # Insertar ruta
            insert_route = """
                INSERT INTO rutas (nombre, color, descripcion, costo, activa)
                VALUES (%s, %s, %s, %s, %s)
            """
            self.cursor.execute(insert_route, (
                route_data['name'],
                route_data['color'],
                route_data.get('description', ''),
                8.00,  # Costo por defecto
                True
            ))
            
            route_id = self.cursor.lastrowid
            
            # Insertar coordenadas
            if route_data['coordinates']:
                insert_coord = """
                    INSERT INTO ruta_coordenadas (ruta_id, latitud, longitud, orden)
                    VALUES (%s, %s, %s, %s)
                """
                for i, coord in enumerate(route_data['coordinates']):
                    self.cursor.execute(insert_coord, (
                        route_id,
                        coord[0],  # latitud
                        coord[1],  # longitud
                        i
                    ))
            
            self.connection.commit()
            print(f"  ✓ Ruta importada: {route_data['name']} (ID: {route_id})")
            return route_id
            
        except Error as e:
            print(f"  ✗ Error al importar ruta '{route_data['name']}': {e}")
            self.connection.rollback()
            return None
    
    def import_stop(self, stop_data):
        """
        Importa una parada a la base de datos
        """
        try:
            # Verificar si ya existe una parada cercana (dentro de 10 metros)
            check_query = """
                SELECT id, nombre FROM paradas 
                WHERE ABS(latitud - %s) < 0.0001 AND ABS(longitud - %s) < 0.0001
                LIMIT 1
            """
            self.cursor.execute(check_query, (
                stop_data['coordinates'][0],
                stop_data['coordinates'][1]
            ))
            
            existing = self.cursor.fetchone()
            if existing:
                print(f"  ⚠ Parada ya existe cerca: {existing[1]} (ID: {existing[0]})")
                return existing[0]
            
            # Insertar parada
            insert_stop = """
                INSERT INTO paradas (nombre, latitud, longitud, descripcion, tipo)
                VALUES (%s, %s, %s, %s, %s)
            """
            self.cursor.execute(insert_stop, (
                stop_data['name'],
                stop_data['coordinates'][0],  # latitud
                stop_data['coordinates'][1],  # longitud
                stop_data.get('description', ''),
                'secundaria'  # Tipo por defecto
            ))
            
            stop_id = self.cursor.lastrowid
            self.connection.commit()
            print(f"  ✓ Parada importada: {stop_data['name']} (ID: {stop_id})")
            return stop_id
            
        except Error as e:
            print(f"  ✗ Error al importar parada '{stop_data['name']}': {e}")
            self.connection.rollback()
            return None
    
    def import_from_kml(self, kml_file, import_type='auto'):
        """
        Importa datos desde un archivo KML
        import_type: 'auto', 'routes', 'stops'
        """
        print(f"\n{'='*60}")
        print(f"Importando desde: {kml_file}")
        print(f"{'='*60}\n")
        
        if not os.path.exists(kml_file):
            print(f"✗ Archivo no encontrado: {kml_file}")
            return False
        
        # Parsear KML
        placemarks = self.extract_placemarks(kml_file)
        
        if not placemarks:
            print("✗ No se encontraron elementos para importar en el archivo KML")
            return False
        
        print(f"✓ Se encontraron {len(placemarks)} elementos\n")
        
        routes_imported = 0
        stops_imported = 0
        
        for placemark in placemarks:
            if placemark['type'] == 'LineString' and import_type in ['auto', 'routes']:
                if self.import_route(placemark):
                    routes_imported += 1
                    
            elif placemark['type'] == 'Point' and import_type in ['auto', 'stops']:
                if self.import_stop(placemark):
                    stops_imported += 1
        
        print(f"\n{'='*60}")
        print(f"Importación completada:")
        print(f"  • Rutas importadas: {routes_imported}")
        print(f"  • Paradas importadas: {stops_imported}")
        print(f"{'='*60}\n")
        
        return True
    
    def list_existing_routes(self):
        """Lista las rutas existentes en la base de datos"""
        try:
            query = """
                SELECT r.id, r.nombre, r.color, r.activa, 
                       COUNT(DISTINCT rc.id) as num_coordenadas,
                       COUNT(DISTINCT rp.id) as num_paradas
                FROM rutas r
                LEFT JOIN ruta_coordenadas rc ON r.id = rc.ruta_id
                LEFT JOIN ruta_paradas rp ON r.id = rp.ruta_id
                GROUP BY r.id
                ORDER BY r.id
            """
            self.cursor.execute(query)
            routes = self.cursor.fetchall()
            
            if routes:
                print(f"\n{'='*60}")
                print("Rutas existentes en la base de datos:")
                print(f"{'='*60}")
                for route in routes:
                    status = "✓" if route[3] else "✗"
                    print(f"{status} ID: {route[0]:3d} | {route[1]:30s} | Color: {route[2]} | Coords: {route[4]:3d} | Paradas: {route[5]:3d}")
                print(f"{'='*60}\n")
            else:
                print("\n⚠ No hay rutas en la base de datos\n")
                
        except Error as e:
            print(f"✗ Error al listar rutas: {e}")


def main():
    """Función principal"""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         CombiMap - Importador de Archivos KML             ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # Crear instancia del importador
    importer = KMLImporter(DB_CONFIG)
    
    # Conectar a la base de datos
    if not importer.connect_db():
        sys.exit(1)
    
    try:
        if len(sys.argv) < 2:
            print("Uso:")
            print("  python import_kml.py <archivo.kml> [tipo]")
            print("\nTipos de importación:")
            print("  auto   - Importar todo (rutas y paradas) [por defecto]")
            print("  routes - Importar solo rutas")
            print("  stops  - Importar solo paradas")
            print("\nEjemplos:")
            print("  python import_kml.py rutas_teziutlan.kml")
            print("  python import_kml.py paradas.kml stops")
            print("\n")
            importer.list_existing_routes()
        else:
            kml_file = sys.argv[1]
            import_type = sys.argv[2] if len(sys.argv) > 2 else 'auto'
            
            # Validar tipo
            if import_type not in ['auto', 'routes', 'stops']:
                print(f"✗ Tipo inválido: {import_type}")
                print("Tipos válidos: auto, routes, stops")
                sys.exit(1)
            
            # Importar
            importer.import_from_kml(kml_file, import_type)
            
            # Mostrar resumen
            importer.list_existing_routes()
            
    finally:
        importer.disconnect_db()


if __name__ == "__main__":
    main()

