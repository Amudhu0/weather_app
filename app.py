import os
import requests
from flask import Flask, render_template, request
from dotenv import load_dotenv
from pyngrok import ngrok  # <--- Added this

load_dotenv()

app = Flask(__name__)
API_KEY = os.getenv("OPENWEATHER_API_KEY")
# Get your ngrok token from your .env file
NGROK_TOKEN = os.getenv("NGROK_AUTH_TOKEN") 

@app.route('/', methods=['GET', 'POST'])
def home():
    weather_data = None
    if request.method == 'POST':
        city = request.form.get('city')
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"

        response = requests.get(url).json()

        if response.get("cod") == 200:
            weather_data = {
                "city": response["name"],
                "country": response["sys"]["country"],
                "temp": response["main"]["temp"],
                "feels_like": response["main"]["feels_like"],
                "description": response["weather"][0]["description"],
                "icon": response["weather"][0]["icon"],
                "humidity": response["main"]["humidity"],
                "wind_speed": response["wind"]["speed"],
                "pressure": response["main"]["pressure"],
                "visibility": response["visibility"] / 1000,
            }
        else:
            weather_data = {"error": "City not found. Please try again!"}

    return render_template('index.html', weather=weather_data)

if __name__ == '__main__':
    # 1. Setup ngrok authentication
    if NGROK_TOKEN:
        ngrok.set_auth_token(NGROK_TOKEN)
        
        # 2. Open a HTTP tunnel on port 5000
        # Use bind_tls=True to force a secure https link
        public_url = ngrok.connect(5000, bind_tls=True).public_url
        print(" ****************************************************")
        print(f" * Public ngrok URL: {public_url}")
        print(" ****************************************************")
    else:
        print(" * ngrok token not found in .env, running locally only.")

    # 3. Run the Flask app
    app.run(debug=True, port=5000, use_reloader=False)