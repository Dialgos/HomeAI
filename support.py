import sounddevice as sd
import requests  # Für die Wetterfunktion
import sounddevice as sd
import soundfile as sf
from openai import OpenAI
import constants


import datetime
import os.path
import support

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# For parsing ISO8601 (RFC3339) dateTime strings
from dateutil import parser

client = OpenAI(api_key=constants.OpenAIAPIKey)
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def play_wav_file(path):
    """
    Spielt eine WAV-Datei ab.

    Parameter:
        path (str): Pfad zur WAV-Datei.
    """
    try:
        # Lade die Audiodaten und die Abtastrate
        data, samplerate = sf.read(path, dtype='float32')
        # Spiele die Audiodaten ab
        sd.play(data, samplerate)
        # Warte, bis die Wiedergabe abgeschlossen ist
        sd.wait()
    except Exception as e:
        print(f"Fehler beim Abspielen der Datei: {e}")

def clean_text(text):
    """Bereinigt wiederholte oder irrelevante Phrasen aus dem erkannten Text."""
    words = text.split()
    
    # Entferne benachbarte Wiederholungen
    cleaned_words = [word for i, word in enumerate(words) if i == 0 or word != words[i - 1]]
    
    # Entferne größere Wiederholungen
    final_words = []
    for word in cleaned_words:
        if not final_words or word != final_words[-1]:
            final_words.append(word)
    
    return " ".join(final_words)

def get_todays_events_report():
    """
    Authenticates with Google Calendar, fetches today's events, and returns
    a German-language text report of today's events. Also appends the output
    of `get_today_weather()`.
    """

    # 1) Load credentials (or create if needed)
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save credentials for future runs
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # 2) Build the Calendar service
        service = build("calendar", "v3", credentials=creds)

        # Determine the start/end of "today" in local time
        local_tz = datetime.datetime.now().astimezone().tzinfo
        today = datetime.date.today()

        start_of_day = datetime.datetime(
            today.year, today.month, today.day, 0, 0, 0, tzinfo=local_tz
        )
        end_of_day = start_of_day + datetime.timedelta(days=1)

        time_min = start_of_day.isoformat()
        time_max = end_of_day.isoformat()

        # Fetch today's events
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        # 3) Build the report lines
        lines = ["Einen wunderschönen guten Morgen. Jetzt deine heutigen Termine:"]

        if not events:
            lines.append("Keine Termine heute.")
        else:
            for event in events:
                summary = event.get("summary", "Ohne Titel")
                start_info = event["start"]

                if "dateTime" in start_info:
                    # Timed event
                    dt = parser.parse(start_info["dateTime"]).astimezone(local_tz)

                    # Extract hour and minute in a "spoken-friendly" way:
                    hour = dt.strftime("%-H")  # Removes leading zero on some OSes
                    minute = dt.strftime("%M")

                    if minute == "00":
                        lines.append(f"Um {hour} Uhr ist {summary}")
                    else:
                        lines.append(f"Um {hour}:{minute} Uhr ist {summary}")
                else:
                    # All-day event
                    lines.append(f"{summary} (ganztägig)")

        # 4) Append weather information
        lines.append("\nUnd jetzt die Wettervorhersage für heute:")
        lines.append(get_today_weather())

        # 5) Return a single string
        return "\n".join(lines)

    except HttpError as error:
        # Return an error message if something goes wrong
        return f"Fehler beim Abruf der Termine: {error}"

def get_todays_events():
    """
    Authentifiziert mit dem Google Kalender und gibt eine
    deutschsprachige Auflistung der heutigen Termine zurück.
    """

    # 1) Load credentials (or create if needed)
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save credentials for future runs
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # 2) Google Calendar-Service aufbauen
        service = build("calendar", "v3", credentials=creds)

        # Heute bestimmen (Start/Ende in lokaler Zeitzone)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        today = datetime.date.today()

        start_of_day = datetime.datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=local_tz)
        end_of_day = start_of_day + datetime.timedelta(days=1)

        time_min = start_of_day.isoformat()
        time_max = end_of_day.isoformat()

        # 3) Heutige Termine abrufen
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        # 4) Ausgabe zusammenbauen
        lines = ["Deine heutigen Termine:"]
        if not events:
            lines.append("Keine Termine heute.")
        else:
            for event in events:
                summary = event.get("summary", "Ohne Titel")
                start_info = event["start"]

                if "dateTime" in start_info:
                    # Termin mit Uhrzeit
                    dt = parser.parse(start_info["dateTime"]).astimezone(local_tz)
                    hour = dt.strftime("%-H")  # entfernt führende Null (Linux/Mac)
                    minute = dt.strftime("%M")

                    if minute == "00":
                        lines.append(f"• Um {hour} Uhr: {summary}")
                    else:
                        lines.append(f"• Um {hour}:{minute} Uhr: {summary}")
                else:
                    # Ganztägiger Termin
                    lines.append(f"• {summary} (ganztägig)")

        return "\n".join(lines)

    except HttpError as error:
        return f"Fehler beim Abruf der Termine: {error}"

def get_tomorrows_events():
    """
    Authentifiziert mit dem Google Kalender und gibt eine
    deutschsprachige Auflistung der morgigen Termine zurück.
    """

    # 1) Load credentials (or create if needed)
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save credentials for future runs
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # 2) Google Calendar-Service aufbauen
        service = build("calendar", "v3", credentials=creds)

        # Morgen bestimmen (Start/Ende in lokaler Zeitzone)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)

        start_of_day = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=local_tz)
        end_of_day = start_of_day + datetime.timedelta(days=1)

        time_min = start_of_day.isoformat()
        time_max = end_of_day.isoformat()

        # 3) Morgige Termine abrufen
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        # 4) Ausgabe zusammenbauen
        lines = ["Deine Termine für morgen:"]
        if not events:
            lines.append("Keine Termine für morgen.")
        else:
            for event in events:
                summary = event.get("summary", "Ohne Titel")
                start_info = event["start"]

                if "dateTime" in start_info:
                    # Termin mit Uhrzeit
                    dt = parser.parse(start_info["dateTime"]).astimezone(local_tz)
                    hour = dt.strftime("%-H")
                    minute = dt.strftime("%M")

                    if minute == "00":
                        lines.append(f"• Um {hour} Uhr: {summary}")
                    else:
                        lines.append(f"• Um {hour}:{minute} Uhr: {summary}")
                else:
                    # Ganztägiger Termin
                    lines.append(f"• {summary} (ganztägig)")

        return "\n".join(lines)

    except HttpError as error:
        return f"Fehler beim Abruf der Termine: {error}"


def get_today_weather():
    """Ruft das aktuelle Wetter für einen festgelegten Standort ab und gibt eine beschreibende Zeichenkette zurück."""
    API_KEY = constants.WeatherAPIKEY  # Ersetzen Sie dies durch Ihren OpenWeatherMap API-Schlüssel
    CITY = 'Bubenreuth'  # Ersetzen Sie dies durch Ihren gewünschten Standort
    LANGUAGE = 'de'  # Sprache der Antwort, 'de' für Deutsch
    UNITS = 'metric'  # 'metric' für Celsius, 'imperial' für Fahrenheit

    url = f'http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units={UNITS}&lang={LANGUAGE}'

    try:
        response = requests.get(url)
        response.raise_for_status()  # Überprüft, ob die Anfrage erfolgreich war
        data = response.json()

        # Extrahieren relevanter Informationen
        weather_description = data['weather'][0]['description']
        temperature = data['main']['temp']
        feels_like = data['main']['feels_like']
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']

        # Erstellen einer beschreibenden Nachricht
        weather_report = (
            f"Das Wetter in {CITY} ist {weather_description} "
            f"mit einer Temperatur von {temperature} Grad Celsius. "
            f"Gefühlt sind es {feels_like} Grad."
            f"Der Wind weht mit {wind_speed} Metern pro Sekunde."
        )

        return weather_report

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP-Fehler aufgetreten: {http_err}")
        return "Entschuldigung, ich konnte die Wetterdaten nicht abrufen."
    except Exception as err:
        print(f"Ein Fehler ist aufgetreten: {err}")
        return "Entschuldigung, ein unerwarteter Fehler ist aufgetreten."
    
def extract_device_action(text):
    """Extrahiert das Gerät und die Aktion aus dem Text und mappt Aktionen zu 'on'/'off'."""
    devices = ["lichterkette", "stehlampe"]  # Erweiterbar
    actions_on = ["ein", "an", "einschalten", "aktivieren", "starten"]
    actions_off = ["aus", "ausschalten", "deaktivieren", "stoppen", "abschalten"]

    device = None
    action = None

    # Gerät extrahieren
    for dev in devices:
        if dev in text.lower():
            device = dev
            break

    # Aktion extrahieren und mappen
    for act in actions_on:
        if act in text.lower():
            action = "on"
            break

    if not action:
        for act in actions_off:
            if act in text.lower():
                action = "off"
                break

    return device, action


# Gerät zu IP-Adresse Mapping
DEVICE_IPS = {
    "stehlampe": "192.168.178.139",
    "lichterkette": "192.168.178.111"
}

def send_command_to_device(device, action):
    """
    Sendet einen Befehl an ein Smart Home Gerät und gibt Feedback.

    :param device: Name des Geräts (z.B. "stehlampe", "lichterkette")
    :param action: Aktion ("on" oder "off")
    """
    device_lower = device.lower()
    ip = DEVICE_IPS.get(device_lower)
    
    if not ip:
        print(f"Unbekanntes Gerät: {device}")
        # Statt Assistant.speak, gib den Fehler zurück
        return f"Entschuldigung, ich kenne das Gerät {device} nicht."
    
    # Aufbau der URL entsprechend der Shelly API
    url = f"http://{ip}/relay/0"
    params = {'turn': action}
    
    try:
        response = requests.get(url, params=params, timeout=5)  # Timeout hinzugefügt für bessere Fehlerbehandlung
        response.raise_for_status()  # Überprüft auf HTTP-Fehler
        print(f"Befehl erfolgreich an {device} gesendet: {action}")
        
        # Feedback basierend auf der Aktion
        if action == "on":
            return f"Okay, {device} eingeschaltet."
        elif action == "off":
            return f"Okay, {device} ausgeschaltet."
        else:
            return f"Aktion {action} für {device} wurde ausgeführt."
    except requests.exceptions.Timeout:
        print(f"Zeitüberschreitung beim Senden des Befehls an {device}.")
        return f"Entschuldigung, die Verbindung zum Gerät {device} ist ausgefallen."
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP-Fehler beim Senden des Befehls an {device}: {http_err}")
        return f"Entschuldigung, es gab ein Problem beim Steuern des Geräts {device}."
    except requests.exceptions.RequestException as e:
        print(f"Allgemeiner Fehler beim Senden des Befehls an {device}: {e}")
        return f"Entschuldigung, ich konnte das Gerät {device} nicht steuern."

def AdvancedQuery(prompt):

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": f"{prompt}"
            }
        ]
    )

    return completion.choices[0].message.content