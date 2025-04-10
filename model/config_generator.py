import random

# ==== CONFIGURATION CLASS ====
class RouteConfig:
    def __init__(
        self,
        buffer_km=15,           # Search corridor width
        min_pois=2,             # Minimum POIs per route
        max_pois=8,             # Maximum POIs per route
        daily_capacity=3,       # Stops per day simulation
        segment_km=16,          # Route splitting granularity
        theme="tourism",        # Default theme
        time_budget=12          # Exploration tolerance
    ):
        self.buffer_km = buffer_km      # parameterized
        self.min_pois = min_pois        # default value
        self.max_pois = max_pois        # parameterized
        self.daily_capacity = daily_capacity    # user defined
        self.segment_km = segment_km    # parameterized
        self.theme = theme              # user defined
        self.time_budget = 12           # calculated from user parameters


class UserPreferences:
    def __init__(
        self,
        weights=None,  # Default weights for objective function components
        theme_preference="tourism",  # Theme preference
        budget_level=5,  # 1-10 scale (1=budget, 10=luxury)
        max_daily_spending=200,  # in chosen currency
        trip_duration_days=7,  # Trip constraints
        max_daily_driving_hours=4,
        max_daily_pois=5,  # Maximum POIs to visit per day
        min_poi_rating=3.5,  # Minimum acceptable rating (1-5 scale)
        route_type="loop",  # "loop" or "one-way"
        prefer_scenic_routes=True,
        roam_level=1.5
    ):
        # Use provided values or default fallbacks
        self.weights = weights or {
            "distance": 0.3,         # Preference for shorter routes
            "poi_count": 0.2,        # Preference for more POIs
            "theme_alignment": 0.3,  # How well POIs match preferred themes
            "daily_pace": 0.2        # Preference for comfortable daily schedule
        }

        self.theme_preference = theme_preference or "tourism"

        self.budget_level = budget_level
        self.max_daily_spending = max_daily_spending

        self.trip_duration_days = trip_duration_days
        self.max_daily_driving_hours = max_daily_driving_hours
        self.max_daily_pois = max_daily_pois

        self.min_poi_rating = min_poi_rating

        self.route_type = route_type
        self.prefer_scenic_routes = prefer_scenic_routes

        self.roam_level = roam_level


class POIQueryManager:
    def __init__(self):
        self.previously_queried_area = None
        self.cached_pois = []  # Store POIs with their coordinates for efficient filtering

    def reset(self):
        """Reset the query state for a new route"""
        self.previously_queried_area = None
        self.cached_pois = []

    def add_to_cache(self, pois):
        """Add new POIs to the cache, avoiding duplicates"""
        for poi in pois:
            if poi not in self.cached_pois:
                self.cached_pois.append(poi)

    def get_cached_pois(self):
        """Get all cached POIs"""
        return self.cached_pois

def generate_route_config_from_user_preferences(user_preferences = UserPreferences()):
    max_pois = user_preferences.max_daily_pois * user_preferences.trip_duration_days
    time_budget = int(user_preferences.trip_duration_days * user_preferences.max_daily_driving_hours * user_preferences.roam_level)
    daily_capacity = user_preferences.max_daily_pois

    route_config = RouteConfig(max_pois=max_pois,
                               time_budget=time_budget,
                               daily_capacity=daily_capacity, theme=user_preferences.theme_preference)
    return route_config