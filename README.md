# Travel Planner

This Travel Planner is a customizable itinerary generator for road trips. It uses geodata, user preferences, and simulated annealing to build realistic travel plans that balance quality, efficiency, and personal taste.

---

## Features

- Personalized route planning
- POI discovery via Overpass & Foursquare APIs
- Loop or one-way route generation
- Weighted optimization using a custom objective function
- Simulated annealing for route refinement
- Interactive map visualizations using Folium

---
## Configuartion
### 1. Overpass and OSRM
Currently, we have Overpass and OSRM running locally to avoid hitting rate limits and properly develop and add to our app. To set up the necessary Docker containers and images, see [here](https://docs.google.com/document/d/1aRqFgwWwDghG5AwMzBX79qNThzBxBqJHsCR1KASXMuE/edit?usp=sharing). 
### 2. FourSquare API Key
Go to the [FourSquare Developer Console](https://auth.studio.foursquare.com/u/login/identifier?state=hKFo2SBIci1jMGtoUGtIUkhVMUMzSXdKejZrR0tvZ2Iyc2sybqFur3VuaXZlcnNhbC1sb2dpbqN0aWTZIGx0VktFVEk3Wk41VWducHFVVm0xMjZia2tJeWtKOHh6o2NpZNkgZFZ5NzFrNkV4ejd6Y3BJUnBRaEJoWGZTTjRvY2dqRkU) and create an account to generate your own personal API key. In `model/main.py` find the line:
```python
foursquare_api_key = "YOUR_API_KEY_HERE"
```
and replace the placeholder string with your key.

---
## Setup

### 1. Clone the repo:

```bash
git clone <repo_url>
cd <repo_name>
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the app
From `TravelPlanner/`, run
```bash
PYTHONPATH=.:$PYTHONPATH streamlit run webapp/gui.py
```

### 4. Get an itinerary!
Choose your start & end points, theme, and preferences (optional) and hit Generate Route to see your personalized travel plan!
<img width="1580" alt="Screenshot 2025-04-18 at 12 56 04" src="https://github.com/user-attachments/assets/47f317e6-db77-4475-986c-7fcb97c5d641" />

---
### Future Improvements

- Integrate real-time traffic data for routes
- Incorporate EOD stays (e.g. hotels, AirBnBs)
- Real-time weather integration
- Cost Estimation

---
### Contributors
- **Bryan Baboolal**
- **Chenxi Zhao**
- **Pranjal Kanel**
- **Xiang Meng**
