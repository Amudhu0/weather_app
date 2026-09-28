import os
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("OPENWEATHER_API_KEY")
NGROK_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
PORT = int(os.getenv("PORT", "5000"))

BASE_URL = "https://api.openweathermap.org/data/2.5"
UNITS = {"metric": ("°C", "m/s"), "imperial": ("°F", "mph")}
CACHE_TTL = 600  # seconds; OpenWeather updates roughly every 10 minutes
CACHE_MAX = 256

# One pooled connection for all API calls instead of a new TCP/TLS handshake each time.
session = requests.Session()
_cache = {}


class WeatherError(Exception):
    pass


def _fetch(endpoint, params):
    """GET an OpenWeather endpoint with a small in-memory TTL cache."""
    key = (endpoint, tuple(sorted(params.items())))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]

    try:
        resp = session.get(f"{BASE_URL}/{endpoint}",
                           params={**params, "appid": API_KEY}, timeout=8)
    except requests.RequestException:
        raise WeatherError("Couldn't reach the weather service. Check your connection and try again.")

    if resp.status_code == 404:
        raise WeatherError("City not found. Check the spelling and try again.")
    if resp.status_code == 401:
        raise WeatherError("Invalid API key. Check OPENWEATHER_API_KEY in your .env file.")
    if resp.status_code == 429:
        raise WeatherError("Too many requests. Please wait a minute and try again.")
    if not resp.ok:
        raise WeatherError("The weather service returned an error. Please try again later.")

    data = resp.json()
    if len(_cache) >= CACHE_MAX:
        _cache.clear()
    _cache[key] = (time.monotonic(), data)
    return data


def _local_time(ts, offset):
    return datetime.fromtimestamp(ts + offset, tz=timezone.utc).strftime("%H:%M")


def _summarize_forecast(data, offset):
    """Collapse 3-hourly forecast entries into one row per day."""
    days = {}
    for item in data.get("list", []):
        local = datetime.fromtimestamp(item["dt"], tz=timezone.utc) + timedelta(seconds=offset)
        day = days.setdefault(local.date(), {"lows": [], "highs": [], "icons": {}, "pop": 0})
        day["lows"].append(item["main"]["temp_min"])
        day["highs"].append(item["main"]["temp_max"])
        day["pop"] = max(day["pop"], item.get("pop", 0))
        # Prefer the midday icon as the day's representative condition.
        day["icons"][abs(local.hour - 13)] = (item["weather"][0]["icon"],
                                              item["weather"][0]["description"])

    today = (datetime.now(timezone.utc) + timedelta(seconds=offset)).date()
    result = []
    for date, d in sorted(days.items()):
        icon, desc = d["icons"][min(d["icons"])]
        result.append({
            "day": "Today" if date == today else date.strftime("%a"),
            "low": round(min(d["lows"])),
            "high": round(max(d["highs"])),
            "icon": icon,
            "description": desc,
            "rain_chance": round(d["pop"] * 100),
        })
    return result[:5]


def get_weather(city=None, lat=None, lon=None, units="metric"):
    if not API_KEY:
        raise WeatherError("OPENWEATHER_API_KEY is not set in your .env file.")

    params = {"units": units}
    if lat is not None and lon is not None:
        params.update(lat=lat, lon=lon)
    else:
        params["q"] = city

    current = _fetch("weather", params)
    offset = current.get("timezone", 0)
    # Query the forecast by coordinates so both calls describe the exact same place.
    forecast = _fetch("forecast", {"units": units,
                                   "lat": current["coord"]["lat"],
                                   "lon": current["coord"]["lon"]})

    main, wind, sys_ = current["main"], current.get("wind", {}), current.get("sys", {})
    temp_unit, speed_unit = UNITS[units]
    visibility = current.get("visibility")
    return {
        "city": current.get("name") or "Unknown location",
        "country": sys_.get("country", ""),
        "temp": round(main["temp"]),
        "feels_like": round(main["feels_like"]),
        "temp_min": round(main["temp_min"]),
        "temp_max": round(main["temp_max"]),
        "description": current["weather"][0]["description"],
        "main": current["weather"][0]["main"],
        "icon": current["weather"][0]["icon"],
        "humidity": main["humidity"],
        "pressure": main["pressure"],
        "wind_speed": round(wind.get("speed", 0), 1),
        "wind_deg": wind.get("deg", 0),
        "clouds": current.get("clouds", {}).get("all", 0),
        "visibility": round(visibility / 1000, 1) if visibility is not None else None,
        "sunrise": _local_time(sys_["sunrise"], offset) if "sunrise" in sys_ else None,
        "sunset": _local_time(sys_["sunset"], offset) if "sunset" in sys_ else None,
        "is_day": current["weather"][0]["icon"].endswith("d"),
        "temp_unit": temp_unit,
        "speed_unit": speed_unit,
        "forecast": _summarize_forecast(forecast, offset),
    }


def _read_args():
    city = request.args.get("city", "").strip()[:100]
    lat, lon = request.args.get("lat"), request.args.get("lon")
    units = request.args.get("units", "metric")
    if units not in UNITS:
        units = "metric"
    try:
        lat = float(lat) if lat else None
        lon = float(lon) if lon else None
    except ValueError:
        lat = lon = None
    return city, lat, lon, units


@app.route("/")
def home():
    city, lat, lon, units = _read_args()
    weather = error = None
    if city or (lat is not None and lon is not None):
        try:
            weather = get_weather(city, lat, lon, units)
        except WeatherError as e:
            error = str(e)
    return render_template("index.html", weather=weather, error=error,
                           city=city, units=units)


@app.route("/api/weather")
def api_weather():
    city, lat, lon, units = _read_args()
    if not city and (lat is None or lon is None):
        return jsonify(error="Provide ?city= or ?lat=&lon="), 400
    try:
        return jsonify(get_weather(city, lat, lon, units))
    except WeatherError as e:
        return jsonify(error=str(e)), 502


if __name__ == "__main__":
    if NGROK_TOKEN:
        from pyngrok import ngrok

        if DEBUG:
            # The Werkzeug debugger allows arbitrary code execution; never expose it publicly.
            print(" * FLASK_DEBUG=1 is set, refusing to open a public ngrok tunnel.")
        else:
            ngrok.set_auth_token(NGROK_TOKEN)
            public_url = ngrok.connect(PORT, bind_tls=True).public_url
            print(" ****************************************************")
            print(f" * Public ngrok URL: {public_url}")
            print(" ****************************************************")
    else:
        print(" * ngrok token not found in .env, running locally only.")

    app.run(debug=DEBUG, port=PORT, use_reloader=False)
