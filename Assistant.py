import sounddevice as sd
import json
from vosk import Model, KaldiRecognizer
import os
import tempfile
from gtts import gTTS
from datetime import datetime, timedelta
import time
import threading
import joblib
import requests
import support
from scipy import signal
import numpy as np
import queue
import subprocess
from pydub import AudioSegment
import soundfile as sf

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
HOTWORD = "computer"
LANGUAGE = "de"
ORIGINAL_SAMPLE_RATE = 48000
TARGET_SAMPLE_RATE = 16000
VOLUME_GAIN_DB = 5

# Load the trained intent classifier
classifier = joblib.load("intent_classifier.pkl")

# Speaking status and lock
speaking = False
speaking_lock = threading.Lock()

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def detect_intent(text):
    try:
        intent = classifier.predict([text])[0]
        print(f"Erkannter Intent: {intent} für Text: '{text}'")
        return intent
    except Exception as e:
        print(f"Fehler bei der Intent-Erkennung: {e}")
        return "unknown"


def speak(text):
    """
    Generate speech (TTS) from the given text, play it back,
    and set speaking status to True/False accordingly.
    """
    global speaking
    with speaking_lock:
        speaking = True
    try:
        print("Sprechstatus: Sprechen begonnen")
        tts = gTTS(text=text, lang=LANGUAGE)
        with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as mp3_fp:
            tts.save(mp3_fp.name)
            # Convert MP3 to WAV
            audio = AudioSegment.from_mp3(mp3_fp.name)
            # Increase volume
            audio += VOLUME_GAIN_DB
            with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as wav_fp:
                audio.export(wav_fp.name, format="wav")
                # Read WAV file
                data, samplerate = sf.read(wav_fp.name, dtype='float32')
                # Play audio
                sd.play(data, samplerate)
                sd.wait()  # Wait until playback finishes
    finally:
        with speaking_lock:
            speaking = False
            # Play a small beep or sound to indicate "ready for input" again
            support.play_wav_file("ready_for_input.wav")
            print("Sprechstatus: Sprechen beendet")


def play_wav_with_speaking_flag(path):
    """
    Plays a WAV file while setting speaking=True, to avoid capturing during playback.
    """
    global speaking
    with speaking_lock:
        speaking = True
    try:
        support.play_wav_file(path)
    finally:
        with speaking_lock:
            speaking = False


def process_command(intent, text):
    """
    Process recognized text based on the detected intent.
    Return False if the assistant should exit; True otherwise.
    """
    print(f"Processing intent: {intent} with text: {text}")
    if intent == "get_date":
        today = datetime.now().strftime("%d.%m.%Y")
        speak(f"Heute ist der {today}.")
    elif intent == "get_time":
        now = datetime.now().strftime("%H:%M")
        speak(f"Es ist {now} Uhr.")
    elif intent == "tell_joke":
        speak("Warum können Geister so schlecht lügen? Weil man durch sie hindurchsehen kann!")
    elif intent == "get_weather":
        weather_report = support.get_today_weather()
        speak(weather_report)
    elif intent == "get_todays_events":
        todayEvent = support.get_todays_events()
        speak(todayEvent)
    elif intent == "get_tomorrows_events":
        tomorrowEvent = support.get_tomorrows_events()
        speak(tomorrowEvent)
    elif intent in ["control_device_on", "control_device_off"]:
        device, action = support.extract_device_action(text)
        if device and action:
            feedback = support.send_command_to_device(device, action)
            speak(feedback)
        else:
            speak("Ich konnte das Gerät nicht erkennen.")
    elif intent == "exit":
        threading.Thread(target=play_wav_with_speaking_flag, args=("Input_successful.wav",)).start()
        print("Exit command received, stopping assistant.")
        return False  # deactivate the assistant
    else:
        speak("Ich habe Sie nicht verstanden. Können Sie das wiederholen?")
    return True  # keep the assistant running


def list_microphones():
    print("Verfügbare Mikrofone:")
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{idx}: {device['name']}")


def resample_audio(audio, orig_sr, target_sr):
    """
    Resample the audio from orig_sr to target_sr using scipy.signal.resample.
    Returns audio as np.int16.
    """
    if orig_sr == target_sr:
        return audio
    number_of_samples = int(len(audio) * float(target_sr) / orig_sr)
    resampled_audio = signal.resample(audio, number_of_samples)
    return resampled_audio.astype(np.int16)


# ------------------------------------------------------------------------------
# Alarm & Lichterkette Toggling
# ------------------------------------------------------------------------------
def toggle_lichterkette(duration):
    """
    Toggles the device 'lichterkette' on/off every 3 seconds
    for the specified 'duration' (in seconds).
    """
    end_time = time.time() + duration
    toggle_on = True
    while time.time() < end_time:
        if toggle_on:
            support.send_command_to_device("lichterkette", "on")
        else:
            support.send_command_to_device("lichterkette", "off")
        toggle_on = not toggle_on
        time.sleep(3)
    # Ensure it ends off
    support.send_command_to_device("lichterkette", "off")


def play_alarm_and_toggle_lichterkette(num_times=2):
    """
    Plays the alarm sound N times (set by num_times).
    While each alarm is playing, toggles 'lichterkette' on/off every 3 seconds.
    """
    # Measure how long the .wav file is (in seconds) using pydub
    alarm_audio = AudioSegment.from_file("morning-joy-alarm-clock-20961.wav")
    alarm_duration_seconds = len(alarm_audio) / 1000.0  # length in seconds

    # Play the alarm 'num_times' times
    for i in range(num_times):
        # Start toggling lights in parallel
        toggler_thread = threading.Thread(
            target=toggle_lichterkette,
            args=(alarm_duration_seconds,)
        )
        toggler_thread.start()

        # Play the alarm (blocking call)
        support.play_wav_file("morning-joy-alarm-clock-20961.wav")

        # Wait until toggling finishes
        toggler_thread.join()

        # Optional small pause between repetitions
        time.sleep(1)


def schedule_daily_alarm(num_times=1, hour=8, minute=30):
    """
    Starts a daemon thread that triggers every weekday (Mon-Fri) at [hour:minute].
    Plays the alarm sound 'num_times' times and toggles 'lichterkette' on/off while playing.
    Then speaks the day's events. Skips weekends (Sat=5, Sun=6).

    :param num_times: How many times the alarm should be played (default=2).
    :param hour: Hour of the day to schedule the alarm (default=8).
    :param minute: Minute of the day to schedule the alarm (default=30).
    """
    def alarm_thread():
        while True:
            now = datetime.now()
            # Monday–Friday => now.weekday() in [0..4]
            if now.weekday() < 5:
                # Set alarm time to [hour:minute] for today
                alarm_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if now >= alarm_time:
                    # If we're already past the alarm time today, schedule for tomorrow
                    alarm_time += timedelta(days=1)
                wait_seconds = (alarm_time - now).total_seconds()
                time.sleep(wait_seconds)

                # Alarm time is reached: play alarm, speak events
                play_alarm_and_toggle_lichterkette(num_times=num_times)
                speak(support.get_todays_events_report())
            else:
                # Weekend => skip. Wait until next day at [hour:minute]
                next_day = now + timedelta(days=1)
                alarm_time = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                wait_seconds = (alarm_time - now).total_seconds()
                time.sleep(wait_seconds)

    t = threading.Thread(target=alarm_thread, daemon=True)
    t.start()


# ------------------------------------------------------------------------------
# Main Assistant Logic
# ------------------------------------------------------------------------------
def main():
    # List available microphones
    list_microphones()

    # Pick microphone index (customize if you have a specific device in mind)
    try:
        mic_index = 1  # Might be different on your system
    except ValueError:
        print("Ungültige Eingabe. Verwenden des Standard-Mikrofons (Index 0).")
        mic_index = 0

    # Load Vosk model
    print("Lade das Vosk-Modell...")
    model_path = "vosk-model-small-de-0.15"
    if not os.path.exists(model_path):
        print("Das Vosk-Modell wurde nicht gefunden. "
              "Bitte lade es von https://alphacephei.com/vosk/models herunter und entpacke es hier.")
        return

    model = Model(model_path)
    recognizer = KaldiRecognizer(model, TARGET_SAMPLE_RATE)
    recognizer.SetWords(True)
    print("Modell erfolgreich geladen.")

    # Start the daily alarm thread
    # Example: play the alarm 3 times at 08:30 on weekdays
    schedule_daily_alarm(num_times=1, hour=8, minute=30)

    def run_assistant():
        nonlocal recognizer
        active = False
        audio_queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            # If there's any audio stream status, print it
            if status:
                print(f"Audio stream status: {status}", flush=True)

            # If currently speaking, ignore microphone data
            with speaking_lock:
                if speaking:
                    return

            try:
                audio_queue.put(bytes(indata))
            except Exception as e:
                print(f"Fehler beim Hinzufügen der Audiodaten zur Warteschlange: {e}")

        def audio_processing_thread():
            nonlocal active
            while True:
                indata = audio_queue.get()
                if indata is None:
                    break

                try:
                    # Resample from 48kHz to 16kHz
                    resampled_audio = resample_audio(
                        np.frombuffer(indata, dtype=np.int16),
                        ORIGINAL_SAMPLE_RATE,
                        TARGET_SAMPLE_RATE
                    )
                    audio_data = resampled_audio.tobytes()
                except Exception as e:
                    print(f"Fehler beim Resamplen der Audiodaten: {e}")
                    continue

                # If a full utterance was recognized
                if recognizer.AcceptWaveform(audio_data):
                    result = recognizer.Result()
                    print(f"Recognizer accepted waveform: {result}")
                    try:
                        result_json = json.loads(result)
                        text = result_json.get("text", "")
                    except json.JSONDecodeError as e:
                        print(f"Fehler beim Parsen des Ergebnisses: {e}")
                        text = ""

                    if text:
                        print(f"Erkannter Text: {text}")
                        # Check if hotword triggers "active" mode
                        if not active and HOTWORD in text.lower().split():
                            active = True
                            support.play_wav_file("ready_for_input.wav")
                            recognizer.Reset()
                            print("Hotword erkannt. Assistent ist aktiv.")
                        elif active:
                            # We are already active; interpret the intent
                            intent = detect_intent(text)
                            continue_running = process_command(intent, text)
                            if not continue_running:
                                # If intent == exit, deactivate assistant
                                active = False
                                print("Assistent ist zurück im Listen-Modus.")
                                support.play_wav_file("ready_for_input.wav")
                else:
                    # Partial result
                    partial = recognizer.PartialResult()
                    try:
                        partial_json = json.loads(partial)
                        partial_text = partial_json.get("partial", "")
                    except json.JSONDecodeError as e:
                        print(f"Fehler beim Parsen des Partial Result: {e}")
                        partial_text = ""

                    # Check for hotword in partial result
                    if partial_text and not active and HOTWORD in partial_text.lower().split():
                        active = True
                        support.play_wav_file("ready_for_input.wav")
                        recognizer.Reset()
                        print("Hotword in partial Text erkannt. Assistent ist aktiv.")

        # Start the processing thread
        processing_thread = threading.Thread(target=audio_processing_thread, daemon=True)
        processing_thread.start()

        try:
            # Start recording from microphone
            with sd.RawInputStream(
                samplerate=ORIGINAL_SAMPLE_RATE,
                blocksize=4096,  # Larger blocksize to avoid overflows
                device=mic_index,
                dtype="int16",
                channels=1,
                callback=audio_callback
            ):
                print("Starte Audio-Stream und höre auf Hotword...")
                while True:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("Beenden durch Benutzer.")
            return False
        except Exception as e:
            print(f"Ein Fehler ist aufgetreten: {e}")
            return False
        finally:
            audio_queue.put(None)
            processing_thread.join()

        return True

    # Run the assistant loop
    run_assistant()


if __name__ == "__main__":
    main()
