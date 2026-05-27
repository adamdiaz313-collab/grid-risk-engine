from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import requests
import pandas as pd
import joblib
import re
import os

# ============================================
# GRID RISK ENGINE BACKEND
# ============================================

app = FastAPI(title="Grid Risk Engine API")

# Allows your frontend website to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://grid-risk-engine.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# LOAD TRAINED MODEL
# ============================================

MODEL_PATH = os.getenv("MODEL_PATH", "outage_model.pkl")
MODEL_URL = os.getenv("MODEL_URL")


def download_model_if_needed():
    if os.path.exists(MODEL_PATH):
        print("Model file already exists.")
        return

    if not MODEL_URL:
        print("No MODEL_URL provided. Running without trained model.")
        return

    print("Downloading trained model...")

    with requests.get(MODEL_URL, stream=True, timeout=300) as response:
        response.raise_for_status()

        with open(MODEL_PATH, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

    print("Model downloaded successfully.")

try:
    download_model_if_needed()
    model_bundle = joblib.load(MODEL_PATH)

    if isinstance(model_bundle, dict):
        model = model_bundle["model"]
        model_features = model_bundle["features"]
    else:
        model = model_bundle
        model_features = list(getattr(model, "feature_names_in_", [])) or None

    print("Model loaded successfully.")
    print("Model feature count:", len(model_features) if model_features else None)

except Exception as e:
    print("Model failed to load:", e)
    model = None
    model_features = None

# ============================================
# REQUEST FORMAT
# ============================================

class PredictRequest(BaseModel):
    location_query: str
    peak_demand_mw: float = 54000


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_season(month: int) -> str:
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    else:
        return "Fall"


def infer_region(state_name: str | None) -> str:
    if not state_name:
        return "Unknown"

    state = state_name.lower()

    northeast = [
        "new york", "new jersey", "pennsylvania",
        "massachusetts", "connecticut", "rhode island"
    ]

    southeast = [
        "florida", "georgia", "north carolina",
        "south carolina", "virginia", "louisiana"
    ]

    midwest = [
        "illinois", "ohio", "michigan",
        "indiana", "wisconsin"
    ]

    southwest = [
        "texas", "arizona", "new mexico", "nevada"
    ]

    west = [
        "california", "oregon", "washington"
    ]

    if state in northeast:
        return "Northeast"
    if state in southeast:
        return "Southeast"
    if state in midwest:
        return "Midwest"
    if state in southwest:
        return "Southwest"
    if state in west:
        return "West Coast"

    return "Other"


def geocode_location(location_query: str):
    """
    Converts city / ZIP / neighborhood into latitude and longitude.
    Uses Open-Meteo geocoding.
    """

    url = "https://geocoding-api.open-meteo.com/v1/search"

    params = {
        "name": location_query,
        "count": 1,
        "language": "en",
        "format": "json",
        "countryCode": "US",
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Geocoding request failed: {e}")

    if "results" not in data or len(data["results"]) == 0:
        raise HTTPException(
            status_code=404,
            detail="Location not found. Try city + state, ZIP code, or neighborhood + state."
        )

    result = data["results"][0]

    name = result.get("name", "")
    state = result.get("admin1", "")
    country = result.get("country", "")

    display_name = ", ".join([part for part in [name, state, country] if part])

    return {
        "display_name": display_name,
        "name": name,
        "state": state,
        "country": country,
        "latitude": float(result["latitude"]),
        "longitude": float(result["longitude"]),
        "timezone": result.get("timezone", "auto"),
    }


def get_live_weather(latitude: float, longitude: float):
    """
    Pulls live weather from Open-Meteo using latitude and longitude.
    """

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "wind_speed_10m,"
            "wind_gusts_10m,"
            "surface_pressure"
        ),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather request failed: {e}")

    current = data.get("current", {})

    return {
        "temperature_f": float(current.get("temperature_2m", 70)),
        "humidity_percent": float(current.get("relative_humidity_2m", 50)),
        "precipitation_in": float(current.get("precipitation", 0)),
        "wind_mph": float(current.get("wind_speed_10m", 0)),
        "wind_gust_mph": float(current.get("wind_gusts_10m", current.get("wind_speed_10m", 0))),
        "pressure_mb": float(current.get("surface_pressure", 1013)),
        "time": current.get("time"),
    }


def formula_prediction(temp_f, wind_mph, precipitation_in, peak_demand_mw, storm_active, region, season):
    """
    Backup formula if the trained model fails.
    """

    region_factor = {
        "Northeast": 1.05,
        "Southeast": 1.15,
        "Midwest": 1.08,
        "Southwest": 1.02,
        "West Coast": 1.00,
        "Other": 1.00,
        "Unknown": 1.00,
    }.get(region, 1.00)

    season_factor = {
        "Winter": 1.08,
        "Spring": 0.96,
        "Summer": 1.12,
        "Fall": 1.00,
    }.get(season, 1.00)

    risk = (
        0.12
        + max(0, temp_f - 95) * 0.015
        + max(0, 20 - temp_f) * 0.012
        + max(0, wind_mph - 20) * 0.012
        + max(0, precipitation_in - 1.0) * 0.03
        + max(0, (peak_demand_mw - 52000) / 1000) * 0.01
        + (0.18 if storm_active else 0)
    )

    risk = risk * region_factor * season_factor
    risk = max(0.01, min(risk, 0.95))

    return round(risk * 100, 2)


def get_drivers(weather, peak_demand_mw, storm_active):
    drivers = []

    if storm_active:
        drivers.append("storm-like conditions")
    if weather["wind_mph"] > 20:
        drivers.append("high wind")
    if weather["wind_gust_mph"] > 30:
        drivers.append("strong wind gusts")
    if weather["temperature_f"] > 95:
        drivers.append("extreme heat")
    if weather["temperature_f"] < 20:
        drivers.append("extreme cold")
    if weather["precipitation_in"] > 1.0:
        drivers.append("heavy precipitation")
    if peak_demand_mw > 52000:
        drivers.append("high demand")

    return drivers


def normalize_feature_name(text):
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(text)).strip("_")


def build_model_input(weather, peak_demand_mw, location, region, season, storm_active):
    """
    Creates one row of input data and aligns it to the exact features
    used during training.
    """

    now = datetime.now()

    base_values = {
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "is_weekend": 1 if now.weekday() in [5, 6] else 0,

        "latitude": location["latitude"],
        "longitude": location["longitude"],

        "temperature_f": weather["temperature_f"],
        "weather_temperature_f": weather["temperature_f"],
        "weather_tavg_f": weather["temperature_f"],
        "weather_tmax_f": weather["temperature_f"],
        "weather_tmin_f": weather["temperature_f"] - 8,

        "wind_speed_mph": weather["wind_mph"],
        "wind_mph": weather["wind_mph"],
        "wind_gust_mph": weather["wind_gust_mph"],

        "precipitation_in": weather["precipitation_in"],
        "weather_prcp_in": weather["precipitation_in"],

        "humidity_percent": weather["humidity_percent"],
        "pressure_mb": weather["pressure_mb"],

        "hourly_demand_mw": peak_demand_mw,
        "daily_peak_demand_mw": peak_demand_mw,
        "daily_mean_demand_mw": peak_demand_mw * 0.8,
        "daily_min_demand_mw": peak_demand_mw * 0.6,
        "daily_total_demand_mwh": peak_demand_mw * 24 * 0.8,
        "demand_range_mw": peak_demand_mw * 0.2,
        "demand_hours": 24.0,

        "storm_event_active": 1 if storm_active else 0,
    }

    if model_features is None:
        return pd.DataFrame([base_values])

    row = {}

    state = location.get("state", "")
    city = location.get("name", "")

    state_key = normalize_feature_name(state)
    city_key = normalize_feature_name(city)
    region_key = normalize_feature_name(region)
    season_key = normalize_feature_name(season)
    weekday_key = normalize_feature_name(now.strftime("%A"))

    for feature in model_features:
        # Default value
        value = 0

        # Direct numeric match
        if feature in base_values:
            value = base_values[feature]

        # One-hot encoded state
        elif feature == f"state_{state_key}" or feature == f"state_{state}":
            value = 1

        # One-hot encoded city/station if it exists in the model
        elif feature == f"city_or_station_{city_key}" or feature == f"city_or_station_{city}":
            value = 1

        # One-hot encoded region
        elif feature == f"region_{region_key}" or feature == f"region_{region}":
            value = 1

        # One-hot encoded season
        elif feature == f"season_{season_key}" or feature == f"season_{season}":
            value = 1

        # One-hot encoded day of week
        elif feature == f"day_of_week_{weekday_key}" or feature == f"day_of_week_{now.strftime('%A')}":
            value = 1

        # Storm event type
        elif feature.startswith("storm_event_type_") and storm_active:
            value = 1 if "Thunderstorm" in feature or "Storm" in feature else 0

        row[feature] = value

    return pd.DataFrame([row])


# ============================================
# API ROUTES
# ============================================

@app.get("/")
def health_check():
    return {
        "status": "running",
        "model_loaded": model is not None,
        "feature_count": len(model_features) if model_features else None,
    }


@app.post("/predict")
def predict(req: PredictRequest):
    location = geocode_location(req.location_query)
    weather = get_live_weather(location["latitude"], location["longitude"])

    month = datetime.now().month
    season = get_season(month)
    region = infer_region(location["state"])

    storm_active = weather["wind_mph"] >= 25 or weather["precipitation_in"] >= 1.0
    drivers = get_drivers(weather, req.peak_demand_mw, storm_active)

    source = "formula fallback"

    if model is not None:
        try:
            sample = build_model_input(
                weather=weather,
                peak_demand_mw=req.peak_demand_mw,
                location=location,
                region=region,
                season=season,
                storm_active=storm_active
            )

            probability = round(float(model.predict_proba(sample)[0][1]) * 100, 2)
            source = "trained Random Forest model"

        except Exception as e:
            print("Model prediction failed:", e)

            probability = formula_prediction(
                weather["temperature_f"],
                weather["wind_mph"],
                weather["precipitation_in"],
                req.peak_demand_mw,
                storm_active,
                region,
                season,
            )
            source = "formula fallback"

    else:
        probability = formula_prediction(
            weather["temperature_f"],
            weather["wind_mph"],
            weather["precipitation_in"],
            req.peak_demand_mw,
            storm_active,
            region,
            season,
        )

    return {
        "location": location,
        "region": region,
        "season": season,
        "weather": weather,
        "peak_demand_mw": req.peak_demand_mw,
        "storm_active": storm_active,
        "drivers": drivers,
        "outage_probability": probability,
        "source": source,
    }
