# ==== IMPORTS ====
import math
from geopy.geocoders import Nominatim
from shapely.geometry import Point, Polygon, LineString
import overpass
import requests
import numpy as np
import random
import copy
import display_util


# ==== CONFIGURATION CLASS ====
class RouteConfig:
    def __init__(self):
        self.buffer_km = 15  # Search corridor width
        self.min_pois = 2  # Minimum POIs per route
        self.max_pois = 8  # Maximum POIs per route
        self.daily_capacity = 3  # Stops per day simulation
        self.segment_km = 16  # Route splitting granularity
        self.theme = "tourism"  # Default theme


# ==== GEOCODING UTILITIES ====
geolocator = Nominatim(user_agent="travel_annealing")
overpass_url = "http://localhost:12347/api/interpreter"
osrm_url = "http://localhost:5050/route/v1/driving/"
foursquare_url = "https://api.foursquare.com/v3/places/"
foursquare_api_key = "fsq3njJtNwJ9wE2dqmle63teUelN7qkwSzqrSKDGhg0mQg8="


# returns a city's geographical coordinates (lon, lat)
def geocode_city(city_name):
    location = geolocator.geocode(city_name)
    return (location.longitude, location.latitude) if location else None


# returns a polygon that represents the geographical boundary of a city
def get_city_bounds(city_name):
    location = geolocator.geocode(city_name, exactly_one=True, geometry='geojson')
    if location and 'geojson' in location.raw:
        return Polygon(location.raw['geojson']['coordinates'][0])
    return None


# generates a random point within a given polygon's boundary
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
    "tourism": {"tourism": ["attraction", "museum", "arts_centre", "aquarium", "zoo"]},
    "religious": {"building": ["church", "mosque", "synagogue"]}
}


# ==== ROUTE GEOMETRY HANDLING ====
def get_route_geometry(start_coord, end_coord):
    """Get actual road route geometry using OSRM"""
    url = f"{osrm_url}{start_coord[0]},{start_coord[1]};{end_coord[0]},{end_coord[1]}?overview=full&geometries=geojson"
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

    query = f"[out:json];({theme_filters});out center;"
    try:
        print(f"\n{repr(query)}")
        response = requests.post(overpass_url, data=query).json()
        return [(float(e['lon']), float(e['lat'])) for e in response['elements']]
    except Exception as e:
        return []


def sample_pois(pois, min_pois, max_pois):
    """Random selection with constraints"""
    num_pois = len(pois)

    # fix min and max to be within a valid range
    actual_min = min_pois if num_pois >= min_pois else num_pois
    actual_max = min(max_pois, num_pois)

    if actual_min > actual_max:
        # if there's no valid range, just return all available POIs 
        sampled_pois = pois
    else:
        k = random.randint(actual_min, actual_max)
        sampled_pois = random.sample(pois, k)
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
    url = f"{osrm_url}{coord_str}?overview=full"
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

    final_route = generate_route(start, end, sampled_pois, config.daily_capacity)

    # Generate final route
    return final_route, sampled_pois


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


# returns id for POI (for use with Foursquare Place Details)
def get_poi_id(lat, lon):
    url = f"{foursquare_url}search?&ll={lat},{lon}&limit=1"
    headers = {
        "accept": "application/json",
        "Authorization": foursquare_api_key
    }
    response = requests.get(url, headers=headers).json()
    results = response.get("results", [])

    if results:
        return results[0].get("fsq_id")
    return None

# returns the rating for a place, give the places fsq_id (defaults to 5.0 if None)
def get_poi_rating(place_id):
    url = f"{foursquare_url}{place_id}?fields=rating"

    headers = {
        "accept": "application/json",
        "Authorization": foursquare_api_key
    }
    response = requests.get(url, headers=headers).json()

    return response.get("rating", 5.0)

# gets the ratings for all POIs in a list
def get_all_ratings(pois):
    ratings = []

    for lon, lat in pois:
        place_id = get_poi_id(lat, lon)
        if place_id:
            rating = get_poi_rating(place_id)
        else:
            # default if there is no place_id
            rating = 5.0

        ratings.append(rating)

    return np.array(ratings)


# returns a score based on how well POIs on route match the theme
def calculate_theme_match(pois, theme):
    theme_keywords = THEMES[theme]
    matching_pois = 0
    for poi in pois:
        for k, values in theme_keywords.items():
            if any(value in poi[0] for value in values):
                matching_pois += 1
    return matching_pois / len(pois)

# haversine formula to calculate the distance between two points on the Earth's surface
def haversine_distance(lon1, lat1, lon2, lat2):
    # radius of the Earth (km)
    earth_radius = 6371
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = earth_radius * c
    distance_meters = distance * 1000

    return distance_meters


# returns how spaced out POIs are on the route
def calculate_geographic_spread(pois):
    # defaults to 0 if there is only 1 POI in the route
    if len(pois) < 2:
        return 0

    total_distance = 0
    num_pairs = 0

    # calculate the distance between each pair of points
    for i in range(len(pois)):
        for j in range(i + 1, len(pois)):
            lon1, lat1 = pois[i]
            lon2, lat2 = pois[j]
            total_distance += haversine_distance(lon1, lat1, lon2, lat2)
            num_pairs += 1

    # average distance between all pairs
    average_distance = total_distance / num_pairs
    return average_distance


# returns the length of the route in meters (shorter is better)
def calculate_route_length(pois):
    line = LineString(pois)
    return line.length


# calculates a score for a route based on:
# theme match, ratings, geographic distribution, and route length
def calculate_score(route, config, pois):

    # calculate all intermediate scores
    theme_score = calculate_theme_match(route[1], config.theme)
    print(pois)
    ratings = get_all_ratings(pois)
    print(ratings)
    rating_score = np.mean(ratings)
    geographic_score = calculate_geographic_spread(pois)
    route_length_score = calculate_route_length(pois)

    # combine all scores (ADJUST WEIGHTS dynamically?)
    total_score = ((theme_score * 0.4)
                   + (rating_score * 0.3)
                   + (geographic_score * 0.2)
                   + (route_length_score * 0.1))
    return total_score


# determines whether to accept a new solution in an optimization process
def acceptance_criteria(current_score, new_score, temperature):
    if new_score > current_score:
        return True
    else:
        delta = new_score - current_score
        prob = math.exp(delta / temperature)
        return random.random() < prob


# ==== SIMULATED ANNEALING LOOP ====
# runs simulated annealing for generated routes,
# returns the best-found route and configuration
def simulated_annealing(pois, start_city, end_city=None, route_geo=None, config=RouteConfig(), temperature=0.5,
                        cooling_rate=0.99):
    # just in case route hasn't been generated
    if route_geo is None:
        route_geo = generate_random_route(start_city, end_city, config)

    current_score = calculate_score(route_geo, config, pois)

    for iteration in range(100):
        # generate a new solution
        new_config = neighbor_function(config)
        new_route, new_pois = generate_random_route(start_city, end_city, new_config)
        new_score = calculate_score(new_route, new_config, new_pois)

        # accept the new route based on acceptance criteria
        if acceptance_criteria(current_score, new_score, temperature):
            config = new_config
            route_geo = new_route
            pois = new_pois
            # update the score as well
            current_score = new_score

        # decrease temperature
        temperature *= cooling_rate

    print("final score: ", calculate_score(route_geo, config, pois))
    return route_geo, config, pois


# ==== EXAMPLE USAGE ====
if __name__ == "__main__":
    # Initial configuration
    config = RouteConfig()

    # start and end cities
    start_city = "Boston MA"
    end_city = "Amherst MA"

    # generate initial random route
    route_geo, pois = generate_random_route(start_city, end_city, config)

    # run simulated annealing to get best route
    simulated_annealing(pois, start_city, end_city, route_geo, config)
