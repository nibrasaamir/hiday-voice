
# va.py

from flask import Flask, render_template, jsonify
import pyaudio
import numpy as np
import speech_recognition as sr
import re
import threading
import time
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import parselmouth
import requests
from datetime import datetime
from gtts import gTTS
import subprocess
import os
import sys
import json
from queue import Queue
import random
import pygame

app = Flask(__name__)

# Initialize pygame mixer for audio playback
pygame.mixer.init()

# Audio recording parameters
RATE = 16000
CHUNK = 1024
BUFFER_DURATION = 2  # seconds
BUFFER_SAMPLES = int(RATE * BUFFER_DURATION)
MAX_BUFFER_SIZE = BUFFER_SAMPLES * 2  # 2 bytes per sample for paInt16

# Initialize a thread-safe queue for audio buffers
audio_queue = Queue()

# Event to signal threads to stop
stop_event = threading.Event()

# Event to manage speaking state
is_speaking = threading.Event()

# Initialize Speech Recognizer
recognizer = sr.Recognizer()

# Adjust recognizer parameters for better performance
def calibrate_recognizer():
    with sr.Microphone(sample_rate=RATE) as source:
        app.logger.info("Calibrating for ambient noise... Please wait.")
        recognizer.adjust_for_ambient_noise(source, duration=2)
        app.logger.info(f"Energy threshold set to {recognizer.energy_threshold}")

calibrate_recognizer()

# Load NER model
model_name = "xlm-roberta-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model_ner = AutoModelForTokenClassification.from_pretrained("Davlan/xlm-roberta-base-ner-hrl")
nlp_ner = pipeline("ner", model=model_ner, tokenizer=tokenizer, aggregation_strategy="simple")

# Abusive words list (expanded)
abusive_words = [
    'پاگل', 'اُلو کا پٹھا', 'گدھے', 'کمینے', 'حرام زاد', 'بیوقوف', 'بدتمیز', 'کڑاکڑ', 'درندہ', 'بندر', 'کٹوا', 'مکروہ', 'لوچ',
    'لالچی', 'بغض', 'لعنتی', 'جاهل', 'نہایتی', 'کھنتا', 'شیشے کا', 'تنگ نظری', 'گنگا', 'چڑیا', 'سوکھا', 'بیچارہ', 'ناپسندیدہ', 'بیکار',
    'بدمعاش', 'خائن', 'غیرمتحرک', 'جھوٹی', 'باطل', 'سست', 'تاکید', 'شگفتہ', 'فساد', 'حسد', 'ڈانگ', 'ہنسی مذاق', 'گدلا', 'کپٹا', 'شریر',
    'مکار', 'دھوکہ باز', 'لاواں', 'تنقیدی', 'بےعزت', 'کٹھ پتلی', 'بیحد', 'غیر اخلاقی', 'چالبازی', 'ہتک آمیز', 'بیزار', 'حسینہ', 'فیصلہ کن',
    'لغو', 'مغلط', 'نقصان دہ'
]

# Greeting and Farewell lists
greetings = ['hi', 'hello', 'ہیلو', 'ہی', 'ہائے']
farewells = ['bye', 'goodbye', 'خدا حافظ', 'اللہ حافظ', 'بائے', 'بیائے']

# Swearing phrases list in Urdu
swearing_phrases = [
    'قسم سے', 'اللہ کے قسم', 'میں قسم کھاتا ہوں', 'خدا کے قسم', 'قسم کھاتا ہوں', 'قسم کھاتی ہوں'
]

# Exit phrases list in Urdu
exit_phrases = [
    'بند ہو جاؤ', 'بند کرو دو'
]

# Wada phrases list in Urdu
wada_phrases = [
    'وعدہ', 'وعدے'
]

# Responses dictionary (expanded)
responses = {
    'gheebat': "غیبت نہ کریں۔",
    'abuse': "گالیاں نہ دیں۔",
    'loud': "آہستہ بولیں۔",
    'azaan': "اذان کا وقت ہے، ٹی وی یا موسیقی بند کر دیں۔",
    'greeting': "سلام بولیں۔",
    'farewell': "اللہ حافظ۔",
    'sneeze': "سبحان اللہ۔",
    'high_pitch': "آہستہ بولیں۔",
    'swear': "آپ سچ بول رہے ہیں، تو قسم کی ضرورت نہیں ہے۔",
    'exit': "الوداع!",
    'wada': "وعدہ پورا ضرور کیجیے گا۔"
}

# Pre-compile regular expressions for performance
abusive_pattern = re.compile(r'\b(' + '|'.join(abusive_words) + r')\b', re.IGNORECASE)
greeting_pattern = re.compile(r'\b(' + '|'.join(greetings) + r')\b', re.IGNORECASE)
farewell_pattern = re.compile(r'\b(' + '|'.join(farewells) + r')\b', re.IGNORECASE)
swear_pattern = re.compile(r'\b(' + '|'.join(swearing_phrases) + r')\b', re.IGNORECASE)
exit_pattern = re.compile(r'\b(' + '|'.join(exit_phrases) + r')\b', re.IGNORECASE)
wada_pattern = re.compile(r'\b(' + '|'.join(wada_phrases) + r')\b', re.IGNORECASE)

def contains_abusive_language(text):
    return bool(abusive_pattern.search(text))

def detect_person_names(text):
    if not nlp_ner:
        return False
    entities = nlp_ner(text)
    for entity in entities:
        if entity['entity_group'] == 'PER':
            return True
    return False

def contains_greeting(text):
    return bool(greeting_pattern.search(text))

def contains_farewell(text):
    return bool(farewell_pattern.search(text))

def contains_swearing_phrase(text):
    return bool(swear_pattern.search(text))

def contains_exit_phrase(text):
    return bool(exit_pattern.search(text))

def contains_wada_phrase(text):
    return bool(wada_pattern.search(text))

# Function to generate response based on transcribed text
def generate_response(transcribed_text):
    if contains_swearing_phrase(transcribed_text):
        return responses['swear']
    elif contains_exit_phrase(transcribed_text):
        return responses['exit']
    elif contains_wada_phrase(transcribed_text):
        return responses['wada']
    elif contains_greeting(transcribed_text):
        return responses['greeting']
    elif contains_farewell(transcribed_text):
        return responses['farewell']
    elif detect_person_names(transcribed_text):
        return responses['gheebat']
    elif contains_abusive_language(transcribed_text):
        return responses['abuse']
    else:
        return None

# Function to speak the response using gTTS
def speak_response(response_text):
    # Prevent speaking if already speaking
    if is_speaking.is_set():
        return
    is_speaking.set()
    filename = "response.mp3"
    try:
        tts = gTTS(text=response_text, lang='ur')
        tts.save(filename)
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        
        # Wait for the audio to finish before proceeding
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        
    except Exception as e:
        app.logger.error(f"Error in TTS playback: {e}")
    finally:
        # Delete the file if it exists
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception as e:
                app.logger.error(f"Error deleting {filename}: {e}")
        is_speaking.clear()

# Function to continuously listen and respond
def assistant_loop():
    while not stop_event.is_set():
        # Capture audio
        with sr.Microphone(sample_rate=RATE) as source:
            app.logger.info("Listening... Speak now.")
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            except sr.WaitTimeoutError:
                app.logger.warning("Listening timed out while waiting for phrase to start.")
                continue
            except Exception as e:
                app.logger.error(f"Error during listening: {e}")
                continue

        app.logger.info("Processing...")

        # Transcribe audio
        try:
            transcribed_text = recognizer.recognize_google(audio, language="ur-PK")
            app.logger.info(f"Recognized: {transcribed_text}")
        except sr.UnknownValueError:
            app.logger.warning("Speech Recognition could not understand audio.")
            continue
        except sr.RequestError as e:
            app.logger.error(f"Could not request results from Speech Recognition service; {e}")
            continue

        # Generate response
        response = generate_response(transcribed_text)
        app.logger.info(f"Response: {response}")

        # Speak the response
        speak_response(response)

    app.logger.info("Assistant loop terminated.")

# Global variable to hold the assistant thread
assistant_thread = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_assistant', methods=['POST'])
def start_assistant():
    global assistant_thread
    if assistant_thread and assistant_thread.is_alive():
        return jsonify({"status": "Assistant is already running."}), 200
    else:
        stop_event.clear()
        assistant_thread = threading.Thread(target=assistant_loop, daemon=True)
        assistant_thread.start()
        app.logger.info("Assistant started.")
        return jsonify({"status": "Assistant started."}), 200

@app.route('/stop_assistant', methods=['POST'])
def stop_assistant():
    global assistant_thread
    if assistant_thread and assistant_thread.is_alive():
        stop_event.set()
        assistant_thread.join()
        app.logger.info("Assistant stopped.")
        return jsonify({"status": "Assistant stopped."}), 200
    else:
        return jsonify({"status": "Assistant is not running."}), 200

@app.route('/start_conversation', methods=['POST'])
def start_conversation():
    response = ""
    
    with sr.Microphone(sample_rate=RATE) as source:
        app.logger.info("Listening... Speak now.")
        try:
            audio = recognizer.listen(source)
        except Exception as e:
            app.logger.error(f"Error during listening: {e}")
            return jsonify({"response": "سنوائی میں خرابی ہوئی۔"}), 500

    app.logger.info("Processing...")

    try:
        transcribed_text = recognizer.recognize_google(audio, language="ur-PK")
        app.logger.info(f"Recognized: {transcribed_text}")

        response = generate_response(transcribed_text)
        app.logger.info(f"Response: {response}")

        # Respond with speech
        speak_response(response)

    except sr.UnknownValueError:
        response = "آپ کی آواز واضح نہیں تھی، دوبارہ کوشش کریں۔"
        app.logger.warning(response)
    except sr.RequestError:
        response = "Google Speech Recognition service unavailable."
        app.logger.error(response)
    except Exception as e:
        response = "ایک غیر متوقع خرابی واقع ہوئی۔"
        app.logger.error(f"Unexpected error: {e}")

    return jsonify({"response": response}), 200

if __name__ == '__main__':
    # Run the Flask app with threading enabled
    app.run(debug=False, threaded=True)

