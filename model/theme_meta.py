# === THEMES THAT CORRESPOND TO POIs IN OSM FILES ===

THEMES = {
    "Education": {
        "amenity": ["school", "college", "university", "kindergarten", "library", "public_bookcase"]
    },
    "Healthcare": {
        "amenity": ["hospital", "clinic", "doctors", "dentist", "pharmacy", "veterinary"]
    },
    "Tourism": {
        "tourism": ["attraction", "museum", "arts_centre", "aquarium", "zoo", "theme_park", "gallery"],
        "historic": ["castle", "monument", "ruins", "archaeological_site"]
    },
    "Religious": {
        "amenity": ["place_of_worship"],
        "building": ["church", "mosque", "synagogue", "temple"]
    },
    "Transportation": {
        "amenity": ["bus_station", "ferry_terminal", "taxi", "bicycle_rental", "car_rental", "fuel"],
        "railway": ["station", "tram_stop", "halt"]
    },
    "Accommodation": {
        "tourism": ["hotel", "motel", "guest_house", "hostel", "camp_site", "caravan_site"]
    },
    "Food_and_Drink": {
        "amenity": ["restaurant", "cafe", "fast_food", "pub", "bar", "ice_cream"]
    },
    "Shopping": {
        "shop": ["supermarket", "convenience", "mall", "clothes", "gift", "bakery", "butcher", "greengrocer"]
    },
    "Leisure": {
        "leisure": ["park", "garden", "playground", "sports_centre", "stadium", "swimming_pool", "fitness_centre"]
    },
    "Emergency": {
        "amenity": ["police", "fire_station", "ambulance_station"],
        "emergency": ["phone"]
    },
    "Finance": {
        "amenity": ["bank", "atm", "bureau_de_change"]
    },
    "Public_services": {
        "amenity": ["post_office", "townhall", "courthouse", "community_centre"]
    },
    "Entertainment": {
        "amenity": ["theatre", "cinema", "nightclub", "casino"]
    },
    "Natural": {
        "natural": ["beach", "peak", "volcano", "waterfall", "cave_entrance"]
    }
}
