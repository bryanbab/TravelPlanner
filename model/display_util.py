import string
from datetime import datetime
from shapely.geometry import LineString, MultiPolygon, Polygon
import folium
import polyline
import random

# === UTILS TO SAVE MAPS FOR DEBUGGING AND VISUALIZATION ===
# creates a map with just a route
def write_to_map_using(encoded_polyline, path):

    # Decode the polyline to get coordinates
    coordinates = polyline.decode(encoded_polyline)

    # Create a map centered around the first point of the route
    m = folium.Map(location=coordinates[0], zoom_start=13)

    # Add the route as a polyline to the map
    folium.PolyLine(locations=coordinates, color="blue", weight=5).add_to(m)

    # Save the map to an HTML file
    m.save(path+generate_html_filename())


def generate_html_filename():
    return f"map_{random.randint(1000, 9999)}.html"


# create a map visualizing the decoded polyline and waypoints.
def write_to_map_using_waypoints(encoded_polyline=None, waypoints=None, start_coord=None,
                                 end_coord=None, path="./visualmaps/good/"):
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

    # Save the map
    m.save(path + generate_html_filename())

    return m

# Visualizes two optional Shapely buffer geometries independently on a Folium map,
# without merging them. Each buffer is shown in a different color.
def write_buffers_to_map(buffer1=None, buffer2=None, output_path="./visualmaps/buffers/"):
    if not buffer1 and not buffer2:
        raise ValueError("At least one buffer must be provided.")

    # Use the first available buffer to center the map
    center_geom = buffer1 or buffer2
    lon, lat = center_geom.centroid.x, center_geom.centroid.y
    m = folium.Map(location=[lat, lon], zoom_start=13)

    # Helper to add buffer geometry to map
    def add_buffer_to_map(buffer_geom, color):
        if isinstance(buffer_geom, Polygon):
            coords = [(y, x) for x, y in buffer_geom.exterior.coords]  # [lat, lon]
            folium.Polygon(locations=coords, color=color, fill=True, fill_opacity=0.4).add_to(m)
        elif isinstance(buffer_geom, MultiPolygon):
            for poly in buffer_geom.geoms:
                add_buffer_to_map(poly, color)

    # Add buffers with different colors
    if buffer1:
        add_buffer_to_map(buffer1, color="red")
    if buffer2:
        add_buffer_to_map(buffer2, color="blue")

    # Save the map
    html_filename = generate_html_filename()
    full_path = output_path + html_filename
    m.save(full_path)
    print(f"Map saved to {full_path}")

# creates a map with multiple routes
def write_multiple_routes_to_map(encoded_polylines, output_file="./visualmaps/osrm_route_map.html"):
    if not encoded_polylines:
        raise ValueError("No routes provided.")

    # Decode the first polyline to center the map
    first_coords = polyline.decode(encoded_polylines[0])
    m = folium.Map(location=first_coords[0], zoom_start=13)

    # List of colors to cycle through
    colors = [
        "blue", "green", "red", "purple", "orange",
        "darkred", "lightred", "beige", "darkblue",
        "darkgreen", "cadetblue", "darkpurple", "white", "pink", "lightblue"
    ]

    for i, encoded in enumerate(encoded_polylines):
        coords = polyline.decode(encoded)
        color = colors[i % len(colors)]  # Cycle through colors
        folium.PolyLine(coords, color=color, weight=5, opacity=0.8).add_to(m)

    m.save(output_file)

# generates an html file name
def generate_html_filename():
    # Generate random string (8 characters)
    random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    # Get current timestamp in YYYYMMDD_HHMMSS format
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Combine into filename with .html extension
    filename = f"{random_chars}_{timestamp}.html"

    return filename


def osrm_geometry_to_linestring(osrm_geometry):
    """
    Convert OSRM geometry to a Shapely LineString object.

    Parameters:
    -----------
    osrm_geometry : dict or str
        OSRM geometry object or encoded polyline string

    Returns:
    --------
    shapely.geometry.LineString
        LineString representing the route
    """
    if isinstance(osrm_geometry, dict):
        if 'coordinates' in osrm_geometry:
            # OSRM coordinates are [longitude, latitude] pairs
            return LineString(osrm_geometry['coordinates'])
        elif 'polyline' in osrm_geometry:
            # Convert encoded polyline to coordinates
            coords = polyline.decode(osrm_geometry['polyline'])
            # Convert [latitude, longitude] to [longitude, latitude]
            return LineString([(lng, lat) for lat, lng in coords])
        else:
            raise ValueError("OSRM geometry must contain either 'coordinates' or 'polyline' field")
    else:
        # Assume it's directly an encoded polyline string
        try:
            coords = polyline.decode(osrm_geometry)
            # Convert [latitude, longitude] to [longitude, latitude]
            return LineString([(lng, lat) for lat, lng in coords])
        except Exception as e:
            raise ValueError(f"Could not parse OSRM geometry: {e}")
