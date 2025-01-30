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

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def get_todays_events_report():
    """
    Authenticates with Google Calendar, fetches today's events, and returns
    a German-language text report of today's events.
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
        lines = ["Heutige Termine:"]

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
                    hour = dt.strftime("%-H")  # Removes leading zero on some OSes (e.g., 09 -> 9)
                    minute = dt.strftime("%M")

                    if minute == "00":
                        # e.g. "Um 9 Uhr ist Meeting"
                        lines.append(f"Um {hour} Uhr ist {summary}")
                    else:
                        # e.g. "Um 9:30 Uhr ist Meeting"
                        lines.append(f"Um {hour}:{minute} Uhr ist {summary}")
                else:
                    # All-day event
                    lines.append(f"{summary} (ganztägig)")

        # 4) Return a single string
        return "\n".join(lines)

    except HttpError as error:
        # Return an error message if something goes wrong
        return f"Fehler beim Abruf der Termine: {error}"


support.play_wav_file("morning-joy-alarm-clock-20961.wav")

speak(support.get_todays_events_report())