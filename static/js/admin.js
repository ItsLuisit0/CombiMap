const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            map: null,
            routes: [],
            stops: [],
            showCreateRouteModal: false,
            showCreateStopModal: false,
            showEditRouteModal: false,
            showEditStopModal: false,
            isPlacingStop: false,
            drawControl: null,
            newRoute: {
                name: '',
                color: '#FF0000',
                coordinates: [],
            },
            newStop: {
                name: '',
                lat: 0,
                lon: 0,
            },
            editingRoute: null,
            editingStop: null,
        }
    },
    mounted() {
        this.checkAuth();
        this.initMap();
        this.fetchRoutes();
        this.fetchStops();
    },
    methods: {
        checkAuth() {
            const token = localStorage.getItem('token');
            if (!token) {
                window.location.href = '/admin/login';
            }
        },
        logout() {
            localStorage.removeItem('token');
            window.location.href = '/admin/login';
        },
        initMap() {
            this.map = L.map('map').setView([19.8151, -97.3594], 13);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
            }).addTo(this.map);

            const drawnItems = new L.FeatureGroup();
            this.map.addLayer(drawnItems);

            this.drawControl = new L.Control.Draw({
                edit: {
                    featureGroup: drawnItems
                },
                draw: {
                    polygon: false,
                    marker: false,
                    circle: false,
                    rectangle: false,
                    circlemarker: false,
                }
            });
            this.map.addControl(this.drawControl);

            this.map.on(L.Draw.Event.CREATED, (event) => {
                const layer = event.layer;
                drawnItems.addLayer(layer);

                const latlngs = layer.getLatLngs();
                this.newRoute.coordinates = latlngs.map(latlng => [latlng.lat, latlng.lng]);
                this.showCreateRouteModal = true;
            });

            this.map.on('click', (e) => {
                if (this.isPlacingStop) {
                    this.newStop.lat = e.latlng.lat;
                    this.newStop.lon = e.latlng.lng;
                    this.showCreateStopModal = true;
                    this.isPlacingStop = false;
                    L.DomUtil.removeClass(this.map._container, 'crosshair-cursor');
                }
            });
        },
        enterDrawMode() {
            new L.Draw.Polyline(this.map, this.drawControl.options.draw.polyline).enable();
        },
        enterPlaceStopMode() {
            this.isPlacingStop = true;
            L.DomUtil.addClass(this.map._container, 'crosshair-cursor');
        },
        async fetchRoutes() {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch('/api/admin/routes', {
                    headers: {
                        'x-access-token': token
                    }
                });
                if (response.ok) {
                    this.routes = await response.json();
                } else {
                    console.error('Error al obtener las rutas');
                }
            } catch (error) {
                console.error('Error obteniendo rutas:', error);
            }
        },
        async fetchStops() {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch('/api/stops', { // Using the public endpoint for now
                    headers: {
                        'x-access-token': token
                    }
                });
                if (response.ok) {
                    this.stops = await response.json();
                } else {
                    console.error('Error al obtener las paradas');
                }
            } catch (error) {
                console.error('Error obteniendo paradas:', error);
            }
        },
        async createRoute() {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch('/api/admin/routes', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-access-token': token,
                    },
                    body: JSON.stringify(this.newRoute),
                });

                if (response.ok) {
                    this.fetchRoutes();
                    this.showCreateRouteModal = false;
                    this.newRoute = { name: '', color: '#FF0000', coordinates: [] };
                } else {
                    console.error('Error al crear la ruta');
                }
            } catch (error) {
                console.error('Error creando la ruta:', error);
            }
        },
        async createStop() {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch('/api/admin/stops', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-access-token': token,
                    },
                    body: JSON.stringify(this.newStop),
                });

                if (response.ok) {
                    this.fetchStops();
                    this.showCreateStopModal = false;
                    this.newStop = { name: '', lat: 0, lon: 0 };
                } else {
                    console.error('Error al crear la parada');
                }
            } catch (error) {
                console.error('Error creando la parada:', error);
            }
        },
        async deleteRoute(routeId) {
            if (!confirm('¿Estás seguro de que quieres eliminar esta ruta?')) {
                return;
            }
            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`/api/admin/routes/${routeId}`, {
                    method: 'DELETE',
                    headers: {
                        'x-access-token': token
                    }
                });
                if (response.ok) {
                    this.fetchRoutes();
                } else {
                    console.error('Error al eliminar la ruta');
                }
            } catch (error) {
                console.error('Error eliminando la ruta:', error);
            }
        },
        async deleteStop(stopId) {
            if (!confirm('¿Estás seguro de que quieres eliminar esta parada?')) {
                return;
            }
            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`/api/admin/stops/${stopId}`, {
                    method: 'DELETE',
                    headers: {
                        'x-access-token': token
                    }
                });
                if (response.ok) {
                    this.fetchStops();
                } else {
                    console.error('Error al eliminar la parada');
                }
            } catch (error) {
                console.error('Error eliminando la parada:', error);
            }
        },
        editRoute(route) {
            this.editingRoute = { ...route };
            this.showEditRouteModal = true;
        },
        async updateRoute() {
            if (!this.editingRoute) return;
            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`/api/admin/routes/${this.editingRoute.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-access-token': token,
                    },
                    body: JSON.stringify(this.editingRoute),
                });

                if (response.ok) {
                    this.fetchRoutes();
                    this.showEditRouteModal = false;
                    this.editingRoute = null;
                } else {
                    console.error('Error al actualizar la ruta');
                }
            } catch (error) {
                console.error('Error actualizando la ruta:', error);
            }
        },
        editStop(stop) {
            this.editingStop = { ...stop };
            this.showEditStopModal = true;
        },
        async updateStop() {
            if (!this.editingStop) return;
            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`/api/admin/stops/${this.editingStop.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-access-token': token,
                    },
                    body: JSON.stringify(this.editingStop),
                });

                if (response.ok) {
                    this.fetchStops();
                    this.showEditStopModal = false;
                    this.editingStop = null;
                } else {
                    console.error('Error al actualizar la parada');
                }
            } catch (error) {
                console.error('Error actualizando la parada:', error);
            }
        },
    }
});

app.mount('#app');
