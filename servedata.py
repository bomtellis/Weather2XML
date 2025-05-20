import threading
import time
import schedule
from http.server import BaseHTTPRequestHandler, HTTPServer
import ssl
import xml.etree.cElementTree as ET
import json
from datetime import datetime, timedelta, timezone
import weather
import asyncio
import sys

# WEB SERVER SETUP
HOSTNAME = "127.0.0.1"
SERVERPORT = 8443

forecast_file = "weather_data.json"

# CONFIGURABLE THRESHOLDS
TEMP_DROP_THRESHOLD = 13  # °C
TEMP_DROP_HOURS = 6  # hours
MIN_TEMP_THRESHOLD = 8  # °C if temp drops to below 8 degrees on rapid temp drops
COLD_SUSTAINED_TEMP = 4  # °C
COLD_SUSTAINED_HOURS = 4  # hours
SYSTEM_REPSONSE_HOURS = 3  # hours required for system to heat up in anticipation

COLD_SNAP = False


def load_forecast(json_path):
    with open(json_path, "r") as file:
        data = json.load(file)
    temperatures = data["hourly"]["temperature_2m"]
    datetimes = [datetime.fromisoformat(dt) for dt in data["hourly"]["time"]]
    dates = data["daily"]["time"]
    sunrise = data["daily"]["sunrise"][1]
    sunrises = data["daily"]["sunrise"]
    sunset = data["daily"]["sunset"][0]
    sunsets = data["daily"]["sunset"]
    return temperatures, datetimes, dates, sunrises, sunsets


def detect_cold_snap(temperatures, datetimes):
    snap_events = []

    # Check for rapid drop in temperature
    for i in range(len(temperatures) - TEMP_DROP_HOURS):
        if temperatures[i] - temperatures[i + TEMP_DROP_HOURS] >= TEMP_DROP_THRESHOLD:
            if temperatures[i + TEMP_DROP_HOURS] < MIN_TEMP_THRESHOLD:
                snap_events.append(
                    {
                        "type": "Rapid temperature drop",
                        "start_time": datetimes[i].isoformat(),
                        "end_time": datetimes[i + 6].isoformat(),
                        "drop": round(
                            temperatures[i] - temperatures[i + TEMP_DROP_HOURS], 1
                        ),
                        "start_temp": temperatures[i],
                        "end_temp": temperatures[i + TEMP_DROP_HOURS],
                    }
                )

    # Check for sustained freezing temperatures
    cold_streak = []
    temp_streak = []
    for temp, dt in zip(temperatures, datetimes):
        if temp < COLD_SUSTAINED_TEMP:
            cold_streak.append(dt)
            temp_streak.append(temp)
            if len(cold_streak) == COLD_SUSTAINED_HOURS:
                snap_events.append(
                    {
                        "type": "Sustained freezing",
                        "start_time": cold_streak[0].isoformat(),
                        "end_time": cold_streak[-1].isoformat(),
                        "hours_below_setpoint": len(cold_streak),
                        "start_temp": temp_streak[0],
                        "end_temp": temp_streak[-1],
                        "min_temp": min(temp_streak),
                    }
                )
                cold_streak = []  # Reset after reporting
                temp_streak = []
        else:
            cold_streak = []
            temp_streak = []

    return snap_events


def checkForColdSnap():
    global COLD_SNAP
    currentTime = datetime.today()

    for item in events:
        startTime = datetime.fromisoformat(item["start_time"])
        endTime = datetime.fromisoformat(item["end_time"])
        warmupTime = startTime - timedelta(hours=SYSTEM_REPSONSE_HOURS)

        if currentTime >= warmupTime and currentTime <= endTime:
            COLD_SNAP = True
            return True
            break
        else:
            COLD_SNAP = False
            return False


def updateSunsetTime():
    global temps, times, sunrises, sunsets, dates, events, dayIndex, sunset
    temps, times, dates, sunrises, sunsets = load_forecast(forecast_file)

    current_datetime = datetime.today()
    try:
        dayIndex = findDayIndex()
    except Exception as e:
        print("error", e)
        reloadProgram()
        return

    if dayIndex == None:
        # Day index doesn't exist roll forward the weather data
        reloadProgram()
        updateSunsetTime()
    else:
        # We want the sunset time to before the sunrise time of the current day

        # Find the last sunset of the current day and check it is before the current day' sunrise
        try:
            current_day_sunset = datetime.fromisoformat(
                sunsets[dayIndex]
            )  # Current Day Sunset
        except Exception as e:
            print("error", e)
            reloadProgram()
            return
        if current_day_sunset < current_datetime:
            # We are before 23:59 current day and it is correct.
            # Output as UTC
            sunset = str(current_day_sunset.astimezone(timezone.utc))
        elif current_day_sunset > current_datetime:
            # We could be after midnight the day after the previous sunset
            # Check if the current time is before the next sunrise
            current_sunrise = datetime.fromisoformat(sunrises[dayIndex])
            if current_datetime < current_sunrise:
                # Sun hasn't risen yet so sunset must be the day before
                # Output as UTC
                sunset = str(
                    datetime.fromisoformat(sunsets[dayIndex - 1]).astimezone(
                        timezone.utc
                    )
                )
            else:
                # The sun has risen so sunset must be later on today
                # Output as UTC
                sunset = str(current_day_sunset.astimezone(timezone.utc))


def updateSunriseTime():
    global temps, times, sunrises, sunsets, dates, events, dayIndex, sunrise
    temps, times, dates, sunrises, sunsets = load_forecast(forecast_file)

    current_datetime = datetime.today()
    try:
        todays_sunrise = datetime.fromisoformat(
            sunrises[dayIndex]
        )  # This is based on today's date
    except Exception as e:
        print("error", e)
        reloadProgram()
        return
    try:
        dayIndex = findDayIndex()
    except Exception as e:
        print("error", e)
        reloadProgram()
        return
    if dayIndex == None:
        # Day index doesn't exist roll forward the weather data
        reloadProgram()  # Run async main function
        updateSunriseTime()
        return
    else:
        # We want the sunrise time to be after the sunset time of the previous day
        if current_datetime < todays_sunrise:
            # Output as UTC
            sunrise = str(
                datetime.fromisoformat(sunrises[dayIndex]).astimezone(timezone.utc)
            )
        else:
            # add 1 to dayIndex
            if (dayIndex + 1) > len(sunrises):
                reloadProgram()
                updateSunriseTime()
                return
            else:
                sunrise = str(
                    datetime.fromisoformat(sunrises[dayIndex + 1]).astimezone(
                        timezone.utc
                    )
                )


def findDayIndex():
    current_date = str(datetime.today().date())

    # Loop thru dates to find index
    try:
        index = dates.index(current_date)
    except Exception as e:
        print("error", e)
        return None

    if index != None:
        return index
    else:
        return None


# Run the schedule loop
def run_scheduler():
    schedule.every().day.at("12:00").do(updateSunriseTime)
    schedule.every().day.at("12:00").do(updateSunsetTime)
    schedule.every().minute.do(checkForColdSnap)

    while True:
        schedule.run_pending()
        time.sleep(1)


class MyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/xml")
        self.end_headers()

        root = ET.Element("data")
        ET.SubElement(root, "ColdSnap", status="1" if COLD_SNAP == True else "0")
        ET.SubElement(root, "SunriseDateTime", datetime=sunrise)
        ET.SubElement(root, "SunsetDateTime", datetime=sunset)
        ET.SubElement(root, "APIName").text = "Weather API"

        xmlString = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        self.wfile.write(bytes(xmlString))


# Run the HTTP server
def run_server():
    webServer = HTTPServer((HOSTNAME, SERVERPORT), MyServer)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="certs/server.crt", keyfile="certs/private.key")
    webServer.socket = context.wrap_socket(webServer.socket, server_side=True)
    webServer.serve_forever()


def loadProgram():
    global temps, times, dates, sunrises, sunsets, events
    temps, times, dates, sunrises, sunsets = load_forecast(forecast_file)
    events = detect_cold_snap(temps, times)

    updateSunsetTime()
    updateSunriseTime()


def reloadProgram():
    asyncio.run(weather.main())
    loadProgram()


# Main
if __name__ == "__main__":
    # Load temps, times, sunrise, sunset initially
    try:
        loadProgram()
    except Exception as e:
        print("error", e)
        try:
            reloadProgram()
        except Exception as f:
            print("error", f)

    # Start HTTP server in a background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    print("Application running")

    # Run the scheduler loop on the main thread
    run_scheduler()
