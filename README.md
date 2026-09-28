# Weather App

A small Flask app showing current conditions and a 5-day forecast from OpenWeather.

## Features
- Search by city, or use your current location (📍)
- °C / °F toggle, sunrise/sunset in the city's local time, wind direction
- 5-day forecast with chance of rain
- Recent searches (stored in your browser)
- Shareable URLs (`/?city=Paris&units=metric`) and a JSON API (`/api/weather?city=Paris`)
- Responses cached in memory for 10 minutes to save API calls
- Background adapts to the weather; dark mode and mobile friendly

## Setup
```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
```
Fill in `OPENWEATHER_API_KEY` in `.env`, then run:
```bash
python app.py
```
Open http://127.0.0.1:5000. If `NGROK_AUTH_TOKEN` is set, a public https URL is printed too
(the tunnel is refused when `FLASK_DEBUG=1`, since the debugger allows remote code execution).
