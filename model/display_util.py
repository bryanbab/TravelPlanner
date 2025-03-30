import folium
import polyline


def write_to_map_using(encoded_polyline):

    # Decode the polyline to get coordinates
    coordinates = polyline.decode(encoded_polyline)

    # Create a map centered around the first point of the route
    m = folium.Map(location=coordinates[0], zoom_start=13)

    # Add the route as a polyline to the map
    folium.PolyLine(coordinates, color="blue", weight=5).add_to(m)

    # Save the map to an HTML file
    m.save("osrm_route_map.html")
