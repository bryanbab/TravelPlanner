from model.config_generator import UserPreferences, generate_route_config_from_user_preferences
from model.main import (geocode_city, generate_random_point_within, get_city_bounds,
                        generate_random_route_and_poll_pois, simulated_annealing)
from gui_utils import generate_itinerary, write_to_map_using, write_to_map_using_waypoints
from streamlit_folium import st_folium
from model.theme_meta import THEMES
import streamlit as st

st.title("Travel Route Generator")

# ALL USER INPUTS
# start and end city
start_city = st.text_input("Start Location", "Boston MA")
end_city = st.text_input("End Location (optional)", "")


# User Preferences configuration
st.sidebar.header("🧭 Plan Your Adventure")

# Questions for weights
# distance
max_distance = st.sidebar.slider(
    "🚗 What's the max distance you're willing to drive per day (km)?",
    min_value=50,
    max_value=1000,
    value=300,
    step=50
)

# poi_count
desired_poi_count = st.sidebar.number_input(
    "📍 How many stops do you want to make?",
    min_value=1,
    max_value=20,
    value=6
)

# theme_alignment
alignment_choice = st.sidebar.radio(
    "🎯 How important is it that stops match your interests?",
    options=["Not important", "Somewhat", "Very important"],
    index=1
)

# daily_pace
daily_pace = st.sidebar.radio(
    "🕰️ How packed should each day be?",
    options=["Relaxed", "Average", "Fast-paced"],
    index=1
)

# answers to above questions
user_preferences = {
    "max_daily_distance_km": max_distance,
    "desired_poi_count": desired_poi_count,
    "theme_alignment": alignment_choice,
    "daily_pace": daily_pace
}

# used to convert preferences to numbers for weights in obj. func.
def convert_preferences_to_weights(prefs):
    distance_weight = max(0.1, 1.0 - (prefs["max_daily_distance_km"] / 1000))
    poi_count_weight = min(1.0, prefs["desired_poi_count"] / 20)
    theme_alignment_mapping = {
        "Not important": 0.1,
        "Somewhat": 0.3,
        "Very important": 0.5,
    }
    theme_alignment_weight = theme_alignment_mapping.get(prefs["theme_alignment"], 0.3)
    daily_pace_mapping = {
        "Relaxed": 0.4,
        "average": 0.2,
        "Fast-paced": 0.1
    }
    daily_pace_weight = daily_pace_mapping.get(prefs["daily_pace"], 0.2)

    return {
        "distance": round(distance_weight, 2),
        "poi_count": round(poi_count_weight, 2),
        "theme_alignment": round(theme_alignment_weight, 2),
        "daily_pace": round(daily_pace_weight, 2)
    }

# theme choice
theme_options = list(THEMES.keys())
selected_theme = st.selectbox("What is the theme of your trip?", theme_options)

trip_duration_days = st.sidebar.slider(
    "🗓️ How many days will your trip be?",
    min_value=1,
    max_value=30,
    value=7
)

max_daily_driving_hours = st.sidebar.slider(
    "⏱️ How many hours are you willing to drive per day?",
    min_value=1,
    max_value=12,
    value=4
)

max_daily_pois = st.sidebar.slider(
    "📌 What's the maximum number of stops per day?",
    min_value=1,
    max_value=10,
    value=5
)

min_poi_rating = st.sidebar.slider(
    "⭐ What's the minimum acceptable rating for places (1–5)?",
    min_value=1.0,
    max_value=5.0,
    value=3.5,
    step=0.5
)

route_type = st.sidebar.radio(
    "🔄 Do you want to return to your starting point?",
    options=["loop", "one-way"],
    index=0,
    format_func=lambda x: "Loop (return to start)" if x == "loop" else "One-way (different end point)"
)

prefer_scenic_routes = st.sidebar.checkbox(
    "🏞️ Prefer scenic routes?",
    value=True
)

roam_level = st.sidebar.slider(
    "🧭 How flexible are you about going off path?",
    min_value=0.5,
    max_value=3.0,
    value=1.5,
    step=0.5
)

run_button = st.button("Generate Route")

# SIMULATED ANNEALING RUN
if 'route_data' not in st.session_state:
    st.session_state.route_data = None

if run_button:
    with st.spinner("Generating route..."):
        try:
            trip_preferences = UserPreferences(weights=convert_preferences_to_weights(user_preferences),
                                               theme_preference=selected_theme,
                                               trip_duration_days=trip_duration_days,
                                               max_daily_driving_hours=max_daily_driving_hours,
                                               max_daily_pois=max_daily_pois,
                                               min_poi_rating=min_poi_rating,
                                               route_type=route_type,
                                               prefer_scenic_routes=prefer_scenic_routes,
                                               roam_level=roam_level)
            config = generate_route_config_from_user_preferences(trip_preferences)
        except KeyError as e:
            st.error(f"Missing expected key: {e}")
            config = None

        if config:
            try:
                start_coord = geocode_city(start_city)
                end_coord = (geocode_city(end_city) if end_city
                             else generate_random_point_within(get_city_bounds(start_city)))

                # check if geocoding was successful
                if not start_coord:
                    st.error(f"Could not find coordinates for start city: {start_city}")
                if end_city and not end_coord:
                    st.error(f"Could not find coordinates for end city: {end_city}")

                # generate initial random route
                if start_coord and end_coord:
                    route, pois = generate_random_route_and_poll_pois(start_coord, end_coord, config)

                    if not route or not pois:
                        st.error("Failed to generate a valid route or POIs.")
                    else:
                        best_route, _, best_pois = simulated_annealing(pois, start_coord, end_coord, route, config)

                        # store route data in session state to display map
                        st.session_state.route_data = (best_route, best_pois, start_coord, end_coord)
                        st.success("Route generated!")

                        # show route using folium
                        poi_coors = [{"lon": lon, "lat": lat} for lon, lat in pois]
                        if best_route:
                            map_folium = write_to_map_using_waypoints(encoded_polyline=best_route["geometry"],
                                                                      waypoints=best_pois,
                                                                      start_coord=(start_coord[1], start_coord[0]),
                                                                      end_coord=(end_coord[1], end_coord[0]))
                            st_folium(map_folium, width=725)

            except Exception as e:
                st.error(f"Error: {e}")

elif st.session_state.route_data:
    best_route, best_pois, start_coord, end_coord = st.session_state.route_data

    if best_route:
        map_folium = write_to_map_using_waypoints(encoded_polyline=best_route["geometry"], waypoints=best_pois,
                                                  start_coord=(start_coord[1],start_coord[0]), end_coord=(end_coord[1],end_coord[0]))
        st_folium(map_folium, width=725)
        st.header("Your Itinerary")
        st.write(generate_itinerary(best_pois, selected_theme, best_route["legs"]))
        print(generate_itinerary(best_pois, selected_theme, best_route["legs"]))

