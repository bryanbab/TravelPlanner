# ==== IMPORTS ====
import math
from geopy.geocoders import Nominatim
from shapely.geometry import Point, Polygon, LineString, MultiPolygon
from shapely.ops import unary_union

from .theme_meta import THEMES
from .config_generator import *
import overpass
import requests
import numpy as np
import random
import copy
from . import display_util
import time


# ==== GEOCODING UTILITIES ====
buffer_counter = 0
poi_manager = POIQueryManager()
geolocator = Nominatim(
    user_agent="travel_annealing",
    domain="localhost:8080",
    scheme="http"
)

overpass_url = "http://localhost:12347/api/interpreter"
osrm_trip_url = "http://localhost:5050/trip/v1/driving/"
osrm_route_url = "http://localhost:5050/route/v1/driving/"

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

# ==== ROUTE GEOMETRY HANDLING ====
def get_route_geometry(start_coord, end_coord):
    """Get actual road route geometry using OSRM"""
    url = f"{osrm_route_url}{start_coord[0]},{start_coord[1]};{end_coord[0]},{end_coord[1]}?overview=full&geometries=geojson"
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
    return sampled_pois


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
    url = f"{osrm_route_url}{coord_str}?overview=full"
    try:
        response = requests.get(url).json()
        if response["code"] == "Ok":
            route_info = response["routes"][0]

            waypoints = response['waypoints']
            latlon_list = []
            # Convert [lon, lat] to [lat, lon]
            for waypoint in waypoints:
                if "location" in waypoint:
                    lon, lat = waypoint["location"]
                    latlon_list.append([lat, lon])
        else:
            route_info, latlon_list = None, None
        return route_info, latlon_list
    except:
        return None


# ==== MAIN WORKFLOW ====
def generate_random_route_and_poll_pois(start, end, config=RouteConfig()):
    #Do not geo code in this method, causes api timeout (start and end needs to be coordinates)
    # Get base route
    route_line = get_route_geometry(start, end)
    if not route_line: return None

    all_pois = poll_pois_from_route_using_segments(route_line, config)
    poi_subset = sample_pois(all_pois, config.min_pois, config.max_pois)
    final_route, waypoints = generate_route(start, end, poi_subset, config.daily_capacity)
    return final_route, waypoints


def poll_pois_from_route_using_segments(route_line, config):
    # Query POIs along entire route
    all_pois = []
    current_buffer_union = None
    segment_buffers = []
    segments = split_route_into_segments(route_line, config.segment_km)



    for segment in segments:
        # Create buffer for current segment
        buffer_deg = config.buffer_km * 1000 / 111320  # Approximate degree conversion
        segment_buffer = segment.buffer(buffer_deg)
        segment_buffers.append(segment_buffer)

    current_buffer_union = unary_union(segment_buffers)

    try:
        global buffer_counter
        display_util.write_buffers_to_map(poi_manager.previously_queried_area,
                                          current_buffer_union,
                                          output_path="./visualmaps/buffers/"+str(buffer_counter))
        buffer_counter += 1
    except Exception as ex:
        print(ex)
        print("failed to write buffers to map")

    # First run case
    if poi_manager.previously_queried_area is None:
        print("Initial query for full buffer area...")
        all_pois = query_pois_for_area(current_buffer_union, config.theme)
        poi_manager.previously_queried_area = current_buffer_union
        poi_manager.cached_pois = all_pois

    # Handle buffer changes - both growing and shrinking

    # 1. Handle new areas (buffer growth)
    elif not poi_manager.previously_queried_area.contains(current_buffer_union):
        new_area = current_buffer_union.difference(poi_manager.previously_queried_area)

        if not new_area.is_empty and new_area.area > 0.001:  # Small threshold to avoid tiny fragments
            print(f"Querying new buffer areas...")
            new_pois = query_pois_for_area(new_area, config.theme)
            all_pois.extend(new_pois)
            poi_manager.previously_queried_area = poi_manager.previously_queried_area.union(current_buffer_union)

        # 2. Handle areas where buffer has decreased
    elif current_buffer_union.within(poi_manager.previously_queried_area):
        print("Buffer has decreased in some areas, filtering POIs...")

        # Option 1: Filter from cached POIs (more efficient)
        cached_pois = poi_manager.get_cached_pois()
        if cached_pois:
            from shapely.geometry import Point

            # Filter to keep only POIs that are still within current buffer
            valid_pois = []
            poi_coords_set = set()
            for poi in cached_pois:
                point = Point(poi)
                if current_buffer_union.contains(point):
                    valid_pois.append(poi)

            all_pois =  valid_pois
        # Option 2: Re-query the entire current buffer (less efficient, but guarantees accuracy)
        else:
            print("No cached POIs available, re-querying entire buffer...")
            all_pois = query_pois_for_area(current_buffer_union, config.theme)
            poi_manager.cached_pois = all_pois
    else:
        # If no part of the buffer decreased, get POIs from cache that are in current buffer
        all_pois =  poi_manager.get_cached_pois()

    # Update the previously queried area to be the current buffer
    poi_manager.previously_queried_area = current_buffer_union

    print(f"Returning {len(all_pois)} POIs for current buffer")
    return all_pois


def query_pois_for_area(area, theme):
    """Query POIs in the given area (which may be MultiPolygon or Polygon)"""
    pois = []

    # Handle both Polygon and MultiPolygon cases
    if isinstance(area, MultiPolygon):
        # Process each polygon separately to avoid overly complex queries
        for poly in area.geoms:
            new_pois = query_pois_for_polygon(poly, theme)
            pois.extend(new_pois)
    else:
        # Process single polygon
        pois.extend(query_pois_for_polygon(area, theme))

    poi_manager.add_to_cache(pois)

    return pois


def query_pois_for_polygon(polygon, theme):
    """Query POIs for a single polygon area"""

    # Get bounding box
    bbox = (polygon.bounds[1], polygon.bounds[0],  # OSM format: (south, west, north, east)
            polygon.bounds[3], polygon.bounds[2])

    # Format bbox for query
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

    # Create polygon filter
    poly_coords = " ".join([f"{lat} {lon}" for lon, lat in list(polygon.exterior.coords)])
    poly_filter = f"(poly:'{poly_coords}')"

    # Build individual node queries with both bbox and polygon filter applied to each
    node_queries = []
    for k, values in THEMES[theme].items():
        for v in values:
            # Apply both bbox and polygon filter to each node query
            node_queries.append(f'node["{k}"~"{v}"]({bbox_str}){poly_filter};')

    # Join all node queries together
    all_queries = "".join(node_queries)

    # Construct final query
    query = f"[out:json];({all_queries});out center;"

    try:
        print(f"Querying new area...")
        start_time = time.time()
        response = requests.post(overpass_url, data=query).json()
        elapsed = time.time() - start_time
        print(f"Query completed in {elapsed:.2f} seconds, found {len(response['elements'])} POIs")

        return [(float(e['lon']), float(e['lat'])) for e in response['elements']]
    except Exception as e:
        print(f"Error querying Overpass API: {e}")
        return []


# ==== SIMULATED ANNEALING UTILITIES ====
def neighbor_function(current_config, time_percentage, temperature):
    """
    Generate a slightly modified configuration based on the current state

    This function creates a "neighbor" solution by making small, intelligent
    modifications to the current configuration. The modifications are adaptive
    based on the current time_percentage.

    Parameters:
    - current_config: The current route configuration
    - time_percentage: How far off we are from the target time budget (negative = under budget)

    Returns:
    - A new RouteConfig object with modified parameters
    """
    new_config = copy.deepcopy(current_config)

    # Scale temperature to a range [0, 1] as it decreases
    scaled_temperature = max(0, min(1, temperature / 100))

    # Use the scaled temperature to decrease the exploration factor from 1.5 to 0.5
    exploration_factor = 1.5 - scaled_temperature * (
        1.0)  # This line ensures the factor starts at 1.5 and decreases

    # Use random.uniform to add variation within the range 0.5 to 1.5
    exploration_factor += random.uniform(0, 0.5)

    # Adjust buffer based on time percentage
    # If we're under budget (negative percentage), we can increase buffer to find more POIs
    # If we're over budget, we should decrease buffer to reduce POIs
    buffer_adjustment = 0.0
    buffer_sample_chance = random.randint(1,100)

    if time_percentage < -10:  # Significantly under time budget
        # Increase buffer to find more POIs - more conservative increase.
        # 75% chance of adjusting polling rate, 10% chance of changing buffer size
        if buffer_sample_chance >= 10:
            increase = new_config.max_pois + 1
            if increase <= new_config.daily_capacity:
                new_config.max_pois = increase
            else:
                buffer_adjustment = random.uniform(0.1, 0.5) * exploration_factor
        else:
            buffer_adjustment = random.uniform(0.1, 0.5) * exploration_factor

    elif time_percentage > 10:  # Significantly over time budget
        # Decrease buffer to reduce number of POIs - more conservative decrease
        # Similar to increase function, with decrement logic
        if buffer_sample_chance >= 25:
            decrease = new_config.max_pois - 1
            if decrease <= new_config.min_pois:
                new_config.max_pois = decrease
            else:
                buffer_adjustment = random.uniform(-0.5, -0.1) * exploration_factor
        else:
            buffer_adjustment = random.uniform(-0.5, -0.1) * exploration_factor
    else:
        # Near target budget, make smaller adjustments
        buffer_adjustment = random.uniform(-0.05, 0.05) * exploration_factor

    # Apply buffer adjustment with bounds checking
    new_buffer = new_config.buffer_km + buffer_adjustment
    new_config.buffer_km = max(0.5, min(new_buffer, 20.0))  # Keep between 0.5 and 20 km

    # Occasionally adjust other parameters
    if random.random() < 0.15:  # 15% chance to adjust segment size
        segment_adjustment = random.choice([-2, -1, 1, 2])
        new_config.segment_km = max(5, min(new_config.segment_km + segment_adjustment, 25))

    # Occasionally change theme (less frequently)
    if random.random() < 0.005:  # 0.5% chance
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
    response = {}
    try:
        response = requests.get(url, headers=headers).json()
    except Exception as e:
        response["rating"] = random.randint(0,5)
    return response.get("rating", 5.0)

# gets the ratings for all POIs in a list
def get_all_ratings(pois):
    ratings = []

    for lat, lon in pois:
        place_id = get_poi_id(lat, lon)
        if place_id:
            #TODO: REMOVE IN FINAL LOOP
            # rating = get_poi_rating(place_id)
            rating = random.randint(1,5)
        else:
            # default if there is no place_id
            rating = 5.0

        ratings.append(rating)

    return np.array(ratings)

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


def calculate_time_score(route, pois, config):
    """
    Calculate how well the route adheres to the target time budget.

    Parameters:
    - route: The route data containing time information
    - pois: List of POIs on the route
    - config: Route configuration with time_budget

    Returns:
    - time_diff: Difference from budget in seconds (+ over budget, - under budget)
    - time_percentage: Percentage difference from budget
    """
    # Time budget in seconds
    time_budget = config.time_budget

    # Calculate travel time
    travel_time = route.get('duration', 0)  # Route travel time in seconds
    if not travel_time and 'time' in route:
        travel_time = route['time']  # Alternative key

    # Add time spent at POIs
    poi_time = time_spent_in_pois(pois)

    # Total time
    total_time = travel_time + poi_time

    # Calculate difference
    time_diff = total_time - time_budget

    # Calculate percentage (+ means over budget, - means under budget)
    if time_budget > 0:
        time_percentage = (time_diff / time_budget) * 100
    else:
        time_percentage = 0

    return time_diff, time_percentage


def time_spent_in_pois(pois):
    poi_time = 0
    for poi in pois:
        poi_time += random.randint(1,3) * 60 * 60 #Convert time spent to seconds
    return poi_time

# returns the length of the route in meters (shorter is better)
def calculate_route_length(pois):
    line = LineString(pois)
    return line.length


# calculates a score for a route based on:
# ratings, geographic distribution, and time_budget
def calculate_score(route, config, pois):
    """
    Calculate a comprehensive score for a route based on multiple factors.

    A lower score is better. The function balances:
    - POI ratings (higher ratings = better score)
    - Geographic distribution (more evenly spaced = better score)
    - Time budget adherence (closer to target time = better score)
    - POI count (appropriate number of POIs based on time budget)

    Parameters:
    - route: The route data (containing time, distance)
    - config: Route configuration parameters
    - pois: List of POIs on the route [(lon, lat), ...]

    Returns:
    - total_score: The overall score (lower is better)
    - time_percentage: How far off we are from time budget (for neighbor function)
    """
    # Safety check
    if not pois or len(pois) == 0:
        return float('inf'), 0

    # Calculate all component scores
    try:
        # Ratings component (higher ratings = lower score)
        ratings = get_all_ratings(pois)
        if len(ratings) == 0:
            rating_score = 5.0  # Default if no ratings
        else:
            # Transform ratings so lower values are better (for minimization)
            rating_score = 10.0 - min(10.0, np.mean(ratings) * 2)  # Scale 0-5 ratings to 0-10 score

        # Geographic distribution component (higher spread = lower score, up to a point)
        geographic_spread = calculate_geographic_spread(pois)
        # Normalize geographic spread: we want points reasonably spread out but not too far
        ideal_spread = 5000.0  # in meters
        geographic_score = abs(geographic_spread - ideal_spread) / 1000.0

        # Time budget adherence
        time_diff, time_percentage = calculate_time_score(route, pois, config)
        time_budget = config.time_budget
        time_score = abs(time_diff) / (time_budget / 5)  # Normalized score

        # POI count component - reward routes with appropriate number of POIs, maximize number of POIs user wants to visit
        poi_count_score = abs(len(pois) - config.max_pois)

        # Weight the components and combine for final score (lower is better)
        weighted_score = (
                rating_score * 0.30 +  # 30% weight for quality
                geographic_score * 0.15 +  # 15% weight for distribution
                time_score * 0.40 +  # 40% weight for time adherence
                poi_count_score * 0.15  # 15% weight for appropriate POI count
        )

        print(f"Score components - Rating: {rating_score:.2f}, Geographic: {geographic_score:.2f}, "
              f"Time: {time_score:.2f}, POI count: {poi_count_score:.2f}")
        print(f"Final weighted score: {weighted_score:.4f}, Time %: {time_percentage}")

        return weighted_score, time_percentage

    except Exception as e:
        print(f"Error calculating score: {e}")
        return float('inf'), 0


# determines whether to accept a new solution in an optimization process
def acceptance_criteria(current_score, new_score, temperature):
    if new_score < current_score:
        return True
    else:
        delta = new_score - current_score
        prob = math.exp(delta / temperature)
        return random.random() < prob


# ==== IMPROVED SIMULATED ANNEALING LOOP ====
def simulated_annealing(pois, start_coord, end_coord, route, config=RouteConfig(),
                        initial_temperature=100.0, cooling_rate=0.95, min_temperature=0.1,
                        max_iterations=100, convergence_threshold=0.001, max_non_improving=15):
    """
    Run simulated annealing with proper temperature decay and convergence detection

    Parameters:
    - initial_temperature: Starting temperature (higher = more exploration)
    - cooling_rate: Rate at which temperature decreases (0.8-0.99)
    - min_temperature: Stop when temperature reaches this value
    - max_iterations: Maximum number of iterations regardless of other conditions
    - convergence_threshold: If score doesn't improve by this amount, consider converged
    - max_non_improving: Number of consecutive non-improving iterations before stopping
    """
    visualizer = []
    temperature = initial_temperature
    current_config = copy.deepcopy(config)
    current_route = route
    current_pois = pois

    # Calculate initial score
    current_score, time_percentage = calculate_score(current_route, current_config, current_pois)

    # Track best solution found
    best_route = current_route
    best_config = copy.deepcopy(current_config)
    best_pois = current_pois
    best_score = current_score

    # Counters and tracking
    iteration = 0
    non_improving_iterations = 0
    score_history = [current_score]

    print(f"Starting SA: Initial score = {current_score:.4f}, Temperature = {temperature:.2f}")

    # Main annealing loop
    while (temperature > min_temperature and
           iteration < max_iterations and
           non_improving_iterations < max_non_improving):

        # Generate a neighbor solution
        new_config = neighbor_function(current_config, time_percentage, temperature)
        new_route, new_pois = generate_random_route_and_poll_pois(start_coord, end_coord,
                                                                  new_config)

        # Check if route generation was successful
        if not new_route or not new_pois:
            print("Failed to generate new route, skipping iteration")
            iteration += 1
            continue

        # Calculate new score
        new_score, new_time_percentage = calculate_score(new_route, new_config, new_pois)

        # Decide whether to accept the new solution
        # For maximization problems (higher score is better)
        delta = current_score - new_score

        if delta > 0 or random.random() < math.exp(delta / temperature):
            # Accept the new solution
            current_config = new_config
            current_route = new_route
            current_pois = new_pois
            current_score = new_score
            time_percentage = new_time_percentage

            # Record for visualization
            visualizer.append(current_route)

            # Update best solution if needed
            if current_score < best_score:
                best_route = current_route
                best_config = copy.deepcopy(current_config)
                best_pois = current_pois
                best_score = current_score
                non_improving_iterations = 0
                print(f"Iteration {iteration}: New best score = {best_score:.4f}")

            else:
                non_improving_iterations += 1

        else:
            # Reject the solution
            non_improving_iterations += 1

        # Check for convergence
        score_history.append(current_score)
        if len(score_history) > 5:  # Use window of 5 iterations
            avg_recent = sum(score_history[-5:]) / 5
            if abs(avg_recent - score_history[-6]) < convergence_threshold:
                print(f"Converged after {iteration} iterations (score stabilized)")
                break

        # Cool down the temperature
        temperature *= cooling_rate
        iteration += 1
        try:
            display_util.write_to_map_using_waypoints(current_route['geometry'],path="./visualmaps/bad/"+str(iteration), waypoints=best_pois, start_coord=(start_coord[1],start_coord[0]), end_coord=(end_coord[1],end_coord[0]))
            display_util.write_to_map_using(current_route['geometry'])
        except Exception as e:
            print(f"Failed to display route: {e}")

        # Log progress periodically
        if iteration % 10 == 0:
            print(
                f"Iteration {iteration}: Score = {current_score:.4f}, Best = {best_score:.4f}, Temp = {temperature:.2f}")

    # Report termination condition
    if temperature <= min_temperature:
        print(f"Stopped: Minimum temperature reached ({temperature:.6f})")
    elif iteration >= max_iterations:
        print(f"Stopped: Maximum iterations reached ({iteration})")
    elif non_improving_iterations >= max_non_improving:
        print(f"Stopped: No improvement for {max_non_improving} iterations")

    print(f"Final Config: {best_config}")
    print(f"Final Time %: {time_percentage}%")
    print(f"Final best score: {best_score:.4f}")
    print(f"Iterations run: {iteration}")

    # Return the best solution found
    return best_route, best_config, best_pois

# ==== EXAMPLE USAGE ====
if __name__ == "__main__":

    # Initial configuration
    config = generate_route_config_from_user_preferences(UserPreferences())

    # start and end cities
    start_city = "Boston MA"
    end_city = None

    start_coord = geocode_city(start_city)
    if not start_coord: raise ValueError(f"Couldn't geocode {start_city}")

    end_coord = (geocode_city(end_city) if end_city
           else generate_random_point_within(get_city_bounds(start_city)))

    # generate initial random route
    route, pois = generate_random_route_and_poll_pois(start_coord, end_coord, config)

    # run simulated annealing to get best route
    simulated_annealing(pois, start_coord, end_coord, route, config)
