from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from model.theme_meta import THEMES
import streamlit as st
import folium
import polyline
import requests

# reverse geocoding utils
geolocator = Nominatim(
        user_agent="travel_annealing",
        domain="localhost:8080",
        scheme="http"
    )
overpass_url = "http://localhost:12347/api/interpreter"

# get city for a POI coordinate
def reverse_geocode(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), language='en', timeout=10)
        if location and location.raw.get('address'):
            city = location.raw['address'].get('city', None)
            # since some places don't have city tags
            if not city:
                city = location.raw['address'].get('town', None)
            if not city:
                city = location.raw['address'].get('village', None)
            return city
        else:
            return "Unknown City"
    except Exception as e:
        return f"Error: {e}"

# reverse search POI from coordinates that is within radius and matches theme
def get_nearest_poi(lat, lon, theme, search_radius=2000):
    # theme picked by user
    tags = THEMES.get(theme, {})

    if not tags:
        return None

    # overpass query to get POIs
    query = """
        [out:json];
        (
            node["amenity"~"{}"](around:{}, {}, {});
            way["amenity"~"{}"](around:{}, {}, {});
            relation["amenity"~"{}"](around:{}, {}, {});
        );
        out body;
        """.format("|".join(tags.get("amenity", [])), search_radius, lat, lon,
                   "|".join(tags.get("amenity", [])), search_radius, lat, lon,
                   "|".join(tags.get("amenity", [])), search_radius, lat, lon)

    # try overpass query, included timeout to prevent error
    try:
        response = requests.get(overpass_url, params={'data': query}, timeout=10)
        # checking for any HTTP errors
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as e:
            print(f"Error decoding JSON: {e}")
            return None

        # if we have the data
        places = []

        for element in data['elements']:
            name = element.get('tags', {}).get('name', 'Unnamed')
            poi_lat = element.get('lat', None)
            poi_lon = element.get('lon', None)

            # make sure we return *named* places with valid coordinates
            if poi_lat and poi_lon and name != 'Unnamed':
                # calculate the distance to the provided coordinates
                distance = geodesic((lat, lon), (poi_lat, poi_lon)).meters
                places.append({'name': name, 'distance': distance})

        # return the closest POI
        if places:
            nearest_poi = min(places, key=lambda x: x['distance'])
            return nearest_poi
        else:
            print("No POIs found within the given radius.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error making request to Overpass API: {e}")
        return None


# generate itinerary from coors
def generate_itinerary(coordinates, theme, legs):
    itinerary = []
    stop_number = 1

    for i, coord in enumerate(coordinates):
        lat, lon = coord
        nearest_poi = get_nearest_poi(lat, lon, theme)

        if nearest_poi:
            city = reverse_geocode(lat, lon)
            # use route["legs"] to add distance and duration to next stop
            if i < len(coordinates) - 1:
                # get the leg that corresponds with the current stop
                leg = legs[stop_number - 1]
                distance_to_next = leg["distance"]
                time_to_next = round(leg["duration"] / 60, 1)
                next_stop_info = f"Distance to next stop: {distance_to_next} meters, Time to next stop: {time_to_next} minutes"
            else:
                next_stop_info = "This is the last stop."

            itinerary.append(f"Stop {stop_number}: {nearest_poi['name']} ({city}) - {next_stop_info}")
            stop_number += 1

    return itinerary

# create a map from a polyline
def write_to_map_using(encoded_polyline):
    try:
        # Decode the polyline to get coordinates
        coordinates = polyline.decode(encoded_polyline)
    except Exception as e:
        st.error(f"Unable to decode polyline: {e}")
        return None

    # Create a map centered around the first point of the route
    m = folium.Map(location=coordinates[0], zoom_start=13)

    # Add the route as a polyline to the map
    folium.PolyLine(coordinates, color="blue", weight=5).add_to(m)

    return m

# create a map from polyline and waypoints
def write_to_map_using_waypoints(encoded_polyline=None, waypoints=None, start_coord=None,
                                 end_coord=None):
    """
    Create a map visualizing the decoded polyline and waypoints.
    """

    # Determine the center point for the map
    if encoded_polyline:
        decoded_points = polyline.decode(encoded_polyline)
        center = decoded_points[0] if decoded_points else [0, 0]
    elif start_coord:
        center = start_coord
    else:
        center = [0, 0]  # Fallback

    # Create a map centered around the determined point
    m = folium.Map(location=center, zoom_start=13)

    # Draw the polyline route if provided
    if encoded_polyline:
        decoded_points = polyline.decode(encoded_polyline)
        folium.PolyLine(
            locations=decoded_points,
            color="blue",
            weight=4,
            opacity=0.8,
            tooltip="Route"
        ).add_to(m)

    # Add start marker if provided
    if start_coord:
        folium.Marker(
            location=start_coord,
            popup="Start",
            tooltip="Start",
            icon=folium.Icon(color="green", icon="play-circle", prefix="fa")
        ).add_to(m)

    # Add waypoint markers
    if waypoints:
        for idx, wp in enumerate(waypoints):
            folium.Marker(
                location=wp,
                popup=f"Waypoint {idx + 1}",
                tooltip=f"{idx + 1}",
                icon=folium.Icon(color="blue", icon="flag", prefix="fa")
            ).add_to(m)

    # Add end marker if provided
    if end_coord:
        folium.Marker(
            location=end_coord,
            popup="End",
            tooltip="End",
            icon=folium.Icon(color="red", icon="stop-circle", prefix="fa")
        ).add_to(m)

    return m