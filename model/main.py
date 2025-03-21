# ==== IMPORTS ====
from geopy.geocoders import Nominatim
from shapely.geometry import Point, Polygon, LineString
import overpass
import requests
import numpy as np
import random
import copy


# ==== CONFIGURATION CLASS ====
class RouteConfig:
    def __init__(self):
        self.buffer_km = 15  # Search corridor width
        self.min_pois = 2  # Minimum POIs per route
        self.max_pois = 8  # Maximum POIs per route
        self.daily_capacity = 3  # Stops per day simulation
        self.segment_km = 80  # Route splitting granularity
        self.theme = "education"  # Default theme


# ==== GEOCODING UTILITIES ====
geolocator = Nominatim(user_agent="travel_annealing")


def geocode_city(city_name):
    location = geolocator.geocode(city_name)
    return (location.longitude, location.latitude) if location else None


def get_city_bounds(city_name):
    location = geolocator.geocode(city_name, exactly_one=True, geometry='geojson')
    if location and 'geojson' in location.raw:
        return Polygon(location.raw['geojson']['coordinates'][0])
    return None


def generate_random_point_within(polygon):
    min_x, min_y, max_x, max_y = polygon.bounds
    while True:
        point = Point(random.uniform(min_x, max_x), random.uniform(min_y, max_y))
        if polygon.contains(point):
            return (point.x, point.y)


# ==== THEME DEFINITIONS ====
THEMES = {
    "education": {"amenity": ["school", "college", "university"]},
    "healthcare": {"amenity": ["hospital", "clinic"]},
    "tourism": {"tourism": ["attraction", "museum"]},
    "religious": {"building": ["church", "mosque", "synagogue"]}
}


# ==== ROUTE GEOMETRY HANDLING ====
def get_route_geometry(start_coord, end_coord):
    """Get actual road route geometry using OSRM"""
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coord[0]},{start_coord[1]};{end_coord[0]},{end_coord[1]}?overview=full&geometries=geojson"
    try:
        response = requests.get(url).json()
        if response["code"] == "Ok":
            coords = response["routes"][0]["geometry"]["coordinates"]
            return LineString([(c[0], c[1]) for c in coords])
    except:
        return None


def split_route_into_segments(route, segment_length_km=16):
    """Split route into manageable segments"""
    segment_length = segment_length_km * 1000  # meters
    return [LineString([route.interpolate(i), route.interpolate(i + segment_length)])
            for i in np.arange(0, route.length, segment_length)]


# ==== POI HANDLING ====
api = overpass.API()


def query_pois_for_segment(segment, theme, buffer_km):
    """Query POIs in buffered corridor around route segment"""
    buffer_deg = buffer_km * 1000 / 111320  # Approximate degree conversion
    buffered = segment.buffer(buffer_deg)
    bbox = (buffered.bounds[1], buffered.bounds[0],  # OSM format: (south, west, north, east)
            buffered.bounds[3], buffered.bounds[2])

    theme_filters = "".join(
        f'node["{k}"~"{v}"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});'
        for k, values in THEMES[theme].items() for v in values
    )

    query = f"""
        [out:json];
        (
            {theme_filters}
        );
        out center;
    """
    try:
        response = api.get(query)
        return [(float(e['lon']), float(e['lat'])) for e in response['elements']]
    except:
        return []


def sample_pois(pois, min_pois, max_pois):
    """Random selection with constraints"""
    k = random.randint(min_pois, min(max_pois, len(pois)))
    return random.sample(pois, k) if pois else []


# ==== ROUTE GENERATION ====
def generate_route(start, end, pois, daily_capacity):
    """Create route with daily stop simulation"""
    random.shuffle(pois)
    daily_groups = [pois[i:i + daily_capacity] for i in range(0, len(pois), daily_capacity)]

    coords = [start]
    for group in daily_groups:
        coords.extend(group)
    coords.append(end)

    coord_str = ";".join(f"{lon},{lat}" for lon, lat in coords)
    url = f"http://router.project-osrm.org/route/v1/driving/{coord_str}?overview=full"
    try:
        response = requests.get(url).json()
        return response["routes"][0]["geometry"] if response["code"] == "Ok" else None
    except:
        return None


# ==== MAIN WORKFLOW ====
def generate_random_route(start_city, end_city=None, config=RouteConfig()):
    """Core route generation with current config"""
    # Geocode endpoints
    start = geocode_city(start_city)
    if not start: raise ValueError(f"Couldn't geocode {start_city}")

    end = (geocode_city(end_city) if end_city
           else generate_random_point_within(get_city_bounds(start_city)))

    # Get base route
    route_line = get_route_geometry(start, end)
    if not route_line: return None

    # Query POIs along entire route
    all_pois = []
    for segment in split_route_into_segments(route_line, config.segment_km):
        all_pois += query_pois_for_segment(segment, config.theme, config.buffer_km)

    # Remove duplicates and sample
    unique_pois = list(set(all_pois))
    sampled_pois = sample_pois(unique_pois, config.min_pois, config.max_pois)

    # Generate final route
    return generate_route(start, end, sampled_pois, config.daily_capacity)


# ==== SIMULATED ANNEALING UTILITIES ====
def neighbor_function(current_config):
    """Generate slightly modified configuration"""
    new_config = copy.deepcopy(current_config)

    # Adjust buffer radius
    new_config.buffer_km += random.choice([-2, 0, 2])
    new_config.buffer_km = max(5, min(new_config.buffer_km, 30))

    # Adjust daily capacity
    new_config.daily_capacity += random.randint(-1, 1)
    new_config.daily_capacity = max(1, min(new_config.daily_capacity, 5))

    # Occasionally change theme
    if random.random() < 0.2:
        new_config.theme = random.choice(list(THEMES.keys()))

    return new_config


# ==== EXAMPLE USAGE ====
if __name__ == "__main__":
    # Initial configuration
    config = RouteConfig()

    # Generate initial random route
    route_geo = generate_random_route("Berlin", "Munich", config)

    # Simulated annealing loop sketch
    for iteration in range(100):
        new_config = neighbor_function(config)
        new_route = generate_random_route("Berlin", "Munich", new_config)
        print('generated route')
        # Here you would compare routes using objective function
        # and decide whether to keep new configuration
        # current_score = calculate_score(route_geo, config)
        # new_score = calculate_score(new_route, new_config)
        # if acceptance_criteria(current_score, new_score, temperature):
        #     config = new_config
        #     route_geo = new_route