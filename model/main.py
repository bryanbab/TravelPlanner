# ==== IMPORTS ====
from geopy.geocoders import Nominatim
from shapely.geometry import Point, Polygon, LineString
import overpass
import requests
import numpy as np
import random
import copy
import math

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

# ==== USER PREFERENCE CLASS ====
class UserPreferences:
    def __init__(self):
        # Default weights for objective function components
        self.weights = {
            "distance": 0.3,        # Preference for shorter routes
            "poi_count": 0.2,        # Preference for more POIs
            "theme_alignment": 0.3,  # How well POIs match preferred themes
            "daily_pace": 0.2,       # Preference for comfortable daily schedule
        }
        
        # Theme preferences (1-10 scale for each theme)
        self.theme_preferences = {
            "education": 5,          # Schools, colleges, universities
            "healthcare": 5,         # Hospitals, clinics
            "tourism": 5,            # Attractions, museums
            "religious": 5,          # Churches, mosques, synagogues
        }
        
        # Budget preferences
        self.budget_level = 5        # 1-10 scale (1=budget, 10=luxury)
        self.max_daily_spending = 200  # in chosen currency
        
        # Trip constraints
        self.trip_duration_days = 7
        self.max_daily_driving_hours = 4
        self.max_daily_pois = 5      # Maximum POIs to visit per day
        
        # POI preferences
        self.min_poi_rating = 3.5    # Minimum acceptable rating (1-5 scale)
        
        # Route style
        self.route_type = "loop"     # "loop" or "one-way"
        self.prefer_scenic_routes = True


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
    if not pois or len(pois) < min_pois:
        return []
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
        return {
            "geometry": LineString([...]),
            "distance": response["routes"][0]["distance"],
            "waypoints": coords
        }if response["code"] == "Ok" else None
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
    final_route = generate_route(start, end, sampled_pois, config.daily_capacity)
    if not final_route:
        return None
    final_route["pois"] = sampled_pois
    return final_route

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

def calculate_score(route, config, user_prefs):
    """Score a route based on multiple factors weighted by user preferences"""
    if not route:
        return float('-inf')
    
    # Extract route metrics
    poi_count = len(route['waypoints']) - 2  # Excluding start/end
    route_length = route['distance']  # in meters
    pois = route['pois']  # Assuming you store POI details including theme info
    
    # === DISTANCE SCORE ===
    # Lower is better, normalize to 0-1 range (inverted)
    max_acceptable_distance = 1000 * config.segment_km * (user_prefs.trip_duration_days - 1)
    distance_score = 1 - min(1, route_length / max_acceptable_distance)
    
    # === POI COUNT SCORE ===
    # More POIs is better, but diminishing returns after preferred density
    preferred_poi_density = user_prefs.max_daily_pois * user_prefs.trip_duration_days
    poi_count_score = min(1, poi_count / preferred_poi_density)
    
    # === THEME ALIGNMENT SCORE ===
    # How well POIs match user's theme preferences
    if poi_count > 0 and hasattr(pois[0], 'theme'):
        theme_scores = []
        for poi in pois:
            # Get user's preference score for this POI's theme (1-10 scale)
            theme_pref = user_prefs.theme_preferences.get(poi.theme, 5)  # Default to 5 if theme not found
            theme_scores.append(theme_pref / 10)  # Normalize to 0-1
        
        # Average theme preference across all POIs
        theme_alignment_score = sum(theme_scores) / len(theme_scores)
    else:
        # If POIs don't have theme data, use the route's configured theme
        theme_alignment_score = user_prefs.theme_preferences.get(config.theme, 5) / 10
    
    # === DAILY PACE SCORE ===
    # How well the route matches preferred daily pace
    days_required = max(1, poi_count / user_prefs.max_daily_pois)
    
    if days_required > user_prefs.trip_duration_days:
        # Too many POIs for trip duration - penalize
        daily_pace_score = user_prefs.trip_duration_days / days_required
    else:
        # Good fit or under capacity
        utilization = days_required / user_prefs.trip_duration_days
        # Score is highest around 80-90% utilization
        daily_pace_score = 1 - abs(0.85 - utilization)
    
    # === COMBINED WEIGHTED SCORE ===
    # Apply user's weights to each component
    final_score = (
        user_prefs.weights["distance"] * distance_score +
        user_prefs.weights["poi_count"] * poi_count_score +
        user_prefs.weights["theme_alignment"] * theme_alignment_score +
        user_prefs.weights["daily_pace"] * daily_pace_score
    )
    
    return final_score

def acceptance_criteria(current_score, new_score, temperature):
    if new_score > current_score:
        return True
    else:
        delta = new_score - current_score
        prob = math.exp(delta / temperature)
        return random.random() < prob

# ==== EXAMPLE USAGE ====
if __name__ == "__main__":
    # Initial configuration
    config = RouteConfig()

    # Generate initial random route
    route_geo = generate_random_route("Berlin", "Munich", config)
    user_prefs = UserPreferences()
    temperature = 100

    # Simulated annealing loop sketch
    for iteration in range(100):
        new_config = neighbor_function(config)
        new_route = generate_random_route("Berlin", "Munich", new_config)
        print('generated route')
        # Here you would compare routes using objective function
        # and decide whether to keep new configuration
        current_score = calculate_score(route_geo, config, user_prefs)
        new_score = calculate_score(new_route, new_config, user_prefs)
        if acceptance_criteria(current_score, new_score, temperature):
            config = new_config
            route_geo = new_route
        temperature *= 95