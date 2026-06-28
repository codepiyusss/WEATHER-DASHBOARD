
import os, sys, json, time, threading, itertools, logging
from datetime import datetime
try:
    import requests
    from colorama import init, Fore, Style
    from dotenv import load_dotenv
except ImportError:
    print("Missing packages. Run: pip install requests colorama python-dotenv")
    sys.exit(1)

# Configuration
load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
HISTORY_FILE = "history.json"
FAV_FILE = "favorites.json"
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("WeatherCLI")

# Initialize colorama
init(autoreset=True)

# Simple spinner context manager
class Spinner:
    spinner_cycle = itertools.cycle("|/-\\")
    def __init__(self, message="Loading"):
        self.msg = message
        self.busy = False
        self.thread = None
    def spin(self):
        while self.busy:
            sys.stdout.write(f"\r{next(self.spinner_cycle)} {self.msg}... ")
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write("\r" + " "*(len(self.msg)+4) + "\r")
    def __enter__(self):
        self.busy = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.busy = False
        self.thread.join()

# Utility I/O functions
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path) 

history_data = load_json(HISTORY_FILE, {"history": []})
fav_data = load_json(FAV_FILE, {"favorites": []})

cache = {}
CACHE_TTL = 600  # seconds

def fetch_weather(city):
    if not city:
        print(Fore.RED + "No city provided.")
        return None
    now = time.time()
    if city.lower() in cache:
        ts, info = cache[city.lower()]
        if now - ts < CACHE_TTL:
            logger.debug(f"Cache hit for {city}")
            return info
    if API_KEY:
        params = {"q": city, "appid": API_KEY, "units": "metric"}
        try:
            with Spinner("Fetching weather for " + city):
                res = requests.get(BASE_URL, params=params, timeout=5)
            res.raise_for_status()
            data = res.json()
            if data.get("cod") != 200:
                msg = data.get("message", "Error fetching data.")
                print(Fore.RED + f"API error: {msg}")
                return None
        except requests.RequestException as e:
            print(Fore.RED + "Network/API request failed:", e)
            return None
    else:
        # Offline demo mode
        print(Fore.YELLOW + "No API key found, using offline demo mode.")
        data = {
            "name": city.title(),
            "weather": [{"main": "Clear", "description": "clear sky"}],
            "main": {"temp": 20.0, "feels_like": 19.0, "humidity": 50, "pressure": 1013},
            "wind": {"speed": 3.5, "deg": 200},
            "visibility": 10000,
            "sys": {"sunrise": 1600000000, "sunset": 1600040000},
            "cod": 200
        }
    # Cache and return
    cache[city.lower()] = (now, data)
    return data

def parse_weather(data):
    if not data: return None
    weather = data["weather"][0]
    main = data["main"]
    wind = data.get("wind", {})
    sysinfo = data.get("sys", {})
    info = {
        "city": data.get("name", ""),
        "condition": weather.get("main", ""),
        "description": weather.get("description", ""),
        "temp": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "pressure": main.get("pressure"),
        "wind_speed": wind.get("speed"),
        "visibility": data.get("visibility"),
        "sunrise": sysinfo.get("sunrise"),
        "sunset": sysinfo.get("sunset"),
        "time": datetime.now()
    }
    return info

# Map weather to icons
WEATHER_ICONS = {
    "Clear": "☀️", "Clouds": "☁️", "Rain": "🌧️", "Drizzle": "🌧️",
    "Snow": "❄️", "Thunderstorm": "⚡", "Mist": "🌫️", "Fog": "🌫️"
}

def format_weather(info):
    if not info: return ""
    city = info["city"]
    cond = info["condition"]
    desc = info["description"].capitalize()
    icon = WEATHER_ICONS.get(cond, "")
    line1 = f"{icon}  {Fore.CYAN}{city}{Style.RESET_ALL}"
    temp = info["temp"]
    feels = info["feels_like"]
    line2 = f"🌡️  Temp: {temp:.1f}°C (feels {feels:.1f}°C), Humidity: {info['humidity']}%"
    line3 = f"💨  Wind: {info['wind_speed']} m/s, Pressure: {info['pressure']} hPa, Vis: {info['visibility']} m"
    sr = datetime.fromtimestamp(info["sunrise"]).strftime("%H:%M") if info["sunrise"] else "N/A"
    ss = datetime.fromtimestamp(info["sunset"]).strftime("%H:%M") if info["sunset"] else "N/A"
    line4 = f"🌅  Sunrise: {sr}, 🌇  Sunset: {ss}"
    return f"{line1}\n{line2}\n{line3}\n{line4}"

def save_history(city, info):
    entry = {
        "city": city.title(),
        "when": datetime.now().isoformat(timespec="seconds"),
        "temp": info["temp"],
        "feels_like": info["feels_like"]
    }
    history_data["history"].insert(0, entry)
    # Optional: limit history length
    history_data["history"] = history_data["history"][:100]
    save_json_atomic(HISTORY_FILE, history_data)

def add_favorite(city):
    city = city.title()
    if city not in fav_data["favorites"]:
        fav_data["favorites"].append(city)
        save_json_atomic(FAV_FILE, fav_data)
        print(Fore.GREEN + f"{city} added to favorites.")
    else:
        print(Fore.YELLOW + f"{city} is already a favorite.")

def remove_favorite(city):
    city = city.title()
    if city in fav_data["favorites"]:
        fav_data["favorites"].remove(city)
        save_json_atomic(FAV_FILE, fav_data)
        print(Fore.GREEN + f"{city} removed from favorites.")
    else:
        print(Fore.YELLOW + f"{city} not in favorites.")

# Menu functions
def menu_search():
    city = input("Enter city name: ").strip()
    if not city:
        print("No city entered.")
        return
    data = fetch_weather(city)
    info = parse_weather(data)
    if info:
        print(format_weather(info))
        save_history(info["city"], info)
        # Ask to favorite
        ans = input("Add to favorites? (y/n): ").strip().lower()
        if ans.startswith('y'):
            add_favorite(info["city"])

def menu_history():
    hist = history_data.get("history", [])
    if not hist:
        print("No history yet.")
        return
    for idx, entry in enumerate(hist, 1):
        print(f"{idx}. {entry['city']} at {entry['when']} (Temp: {entry['temp']}°C)")
    choice = input("Delete entry number or press Enter to go back: ").strip()
    if choice.isdigit():
        i = int(choice)-1
        if 0 <= i < len(hist):
            removed = history_data["history"].pop(i)
            save_json_atomic(HISTORY_FILE, history_data)
            print(f"Removed {removed['city']} from history.")

def menu_favorites():
    favs = fav_data.get("favorites", [])
    if not favs:
        print("No favorites yet.")
        return
    for idx, city in enumerate(favs, 1):
        print(f"{idx}. {city}")
    print("Enter number to view weather, or 'r'+num to remove (e.g. r2), or Enter to return.")
    choice = input("Choice: ").strip().lower()
    if choice.startswith('r') and choice[1:].isdigit():
        i = int(choice[1:]) - 1
        if 0 <= i < len(favs):
            remove_favorite(favs[i])
    elif choice.isdigit():
        i = int(choice) - 1
        if 0 <= i < len(favs):
            data = fetch_weather(favs[i])
            info = parse_weather(data)
            if info:
                print(format_weather(info))
    # else: return

def menu_stats():
    hist = history_data.get("history", [])
    if not hist:
        print("No history to analyze.")
        return
    # Most searched city
    counts = {}
    for e in hist:
        counts[e["city"]] = counts.get(e["city"], 0) + 1
    top_city = max(counts, key=counts.get)
    # Hottest / coldest search
    temps = [(e["temp"], e["city"]) for e in hist]
    hottest = max(temps)[1]
    coldest = min(temps)[1]
    print(f"Most searched city: {top_city} ({counts[top_city]} times)")
    print(f"Hottest search: {hottest}")
    print(f"Coldest search: {coldest}")


def main():
    while True:
        print(Fore.MAGENTA + "\n=== Weather Dashboard ===")
        print("1. Search weather")
        print("2. View history")
        print("3. Favorites")
        print("4. Statistics")
        print("5. Exit")
        choice = input("Choose an option [1-5]: ").strip()
        if choice == '1':
            menu_search()
        elif choice == '2':
            menu_history()
        elif choice == '3':
            menu_favorites()
        elif choice == '4':
            menu_stats()
        elif choice == '5':
            print("Goodbye!")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
