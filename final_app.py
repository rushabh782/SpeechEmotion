# Ignore warnings
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import tensorflow as tf
import logging
import warnings
warnings.filterwarnings('ignore', '.*The name tf.losses.sparse_softmax_cross_entropy is deprecated.*')
# Set TensorFlow logging level to suppress warnings
tf.get_logger().setLevel(logging.ERROR)

# Import necessary libraries
import os
import librosa
from flask import Flask, render_template, jsonify, request, redirect
from flask_cors import CORS
import numpy as np
import pyaudio
import wave
from threading import Thread
from pydub import AudioSegment, effects
from keras.models import load_model
import speech_recognition as sr # pip install SpeechRecognition


# Create the Flask app
app = Flask(__name__)
CORS(app)

# Load the model
model = load_model('model_new.h5')

# Define the folder path where you want to save the file
folder_path = r"static"
# Specify the full path of the file
file_path = os.path.join(folder_path, "predictions.txt")

# Global variable to control recording state
is_recording = False

# Define final_prediction as a global variable
final_prediction = None


# Function to preprocess audio
def preprocess_audio(file):
    audio = AudioSegment.from_file(file)
    samples = np.array(audio.get_array_of_samples(), dtype='float32')
    trimmed, _ = librosa.effects.trim(samples, top_db=25)
    if len(trimmed) >= 180000:
        padded = trimmed[:180000]
    else:
        padded = np.pad(trimmed, (0, 180000 - len(trimmed)), 'constant')
    return padded


# Function to decode emotion label
def decode_emotion(label):
    emotion_dict = {
        0: 'neutral',
        1: 'happy',
        2: 'sad',
        3: 'angry',
        4: 'fear',
        5: 'disgust'
    }
    return emotion_dict.get(label, 'Calm')


# Function to extract features from audio
def extract_features(audio_data):
    zcr = librosa.feature.zero_crossing_rate(audio_data, frame_length=2048, hop_length=512)
    rms = librosa.feature.rms(y=audio_data, frame_length=2048, hop_length=512)
    mfccs = librosa.feature.mfcc(y=audio_data, sr=22050, n_mfcc=13, hop_length=512)
    return zcr, rms, mfccs


def preprocess_audio_chunk(audio_data):
    # Trim silence from the audio waveform
    trimmed, _ = librosa.effects.trim(audio_data, top_db=25)

    # Ensure the length is at most 180000 samples
    max_length = 180000
    if len(trimmed) >= max_length:
        padded = trimmed[:max_length]  # Trim if longer
    else:
        # Pad with zeros if shorter
        padded = np.pad(trimmed, (0, max_length - len(trimmed)), 'constant')

    return padded


def real_time_prediction(audio_data):
    # Preprocess the uploaded audio
    audio_data = preprocess_audio_chunk(audio_data)

    # Extract features from the chunk
    zcr, rms, mfccs = extract_features(audio_data)

    # Reshape features to match the model input shape
    zcr = zcr.T.reshape(-1, 352, 1)
    rms = rms.T.reshape(-1, 352, 1)
    mfccs = mfccs.T.reshape(-1, 352, 13)

    # Concatenate features
    features_concat = np.concatenate((zcr, rms, mfccs), axis=-1)

    # Make prediction using the model
    predictions = model.predict(features_concat)
    predicted_class = np.argmax(predictions)

    # Decode predicted class to emotion label
    prediction = decode_emotion(predicted_class)

    return prediction


# Function to record audio in real-time
def record_audio(filename, chunk_size=16384):
    global is_recording
    global final_prediction
    CHUNK = chunk_size
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100 #96000

    audio = pyaudio.PyAudio()

    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)

    frames = []

    print("Recording...")

    while is_recording:
        data = stream.read(CHUNK)
        frames.append(data)

        # Convert audio data to floating-point format
        audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)

        prediction = real_time_prediction(audio_data)

        print("Partial emotion:", str(prediction))
        # Open the file in write mode to overwrite its contents
        with open(file_path, "w") as predictions_file:
            # Write the prediction to the file
            predictions_file.write(str(prediction) + "\n")

    print("Recording stopped.")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    # Convert all recorded audio data to a single numpy array
    audio_data = np.frombuffer(b''.join(frames), dtype=np.int16).astype(np.float32)

    final_prediction = real_time_prediction(audio_data)

    print("Final Prediction without .wav file:", final_prediction)

    # Save the .wav file to folder
    temp = 'static/recorded_audio.wav'
    wf = wave.open(temp, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"{filename} was successfully saved to static.")

    return filename


# Flask route for login page
@app.route('/')
def login():
    return render_template('login.html')



# Flask route for index page
@app.route('/home')
def index():
    return render_template('index.html')


# Flask route to start recording
@app.route('/start_recording', methods=['GET'])
def start_recording():
    global is_recording
    is_recording = True

    with open(file_path, "w") as predictions_file:
        # Write the prediction to the file
        predictions_file.write("\n")

    # Delete any previous recording
    recording_path = 'static/recorded_audio.wav'
    # Check if the file exists before attempting to delete it
    if os.path.exists(recording_path):
        # Delete the file using os.remove()
        os.remove(recording_path)
        print(f"File '{recording_path}' deleted successfully.")
    else:
        print(f"File '{recording_path}' does not exist.")

    # Start recording audio
    audio_filename = 'recorded_audio.wav'
    t = Thread(target=record_audio, args=(audio_filename,))
    t.start()
    return jsonify({'message': 'Recording started'})


# Flask route to stop recording
@app.route('/stop_recording', methods=['GET'])
def stop_recording():
    global is_recording
    is_recording = False  # Set is_recording flag to False to stop recording
    return jsonify({'message': 'Recording stopped'})


# Flask route to stop recording
@app.route('/predict', methods=['GET'])
def predict():
    global final_prediction
    prediction = final_prediction
    final_prediction = None
    print('Final Prediction:', prediction)
    with open('final_emotion.txt', 'w') as f:
        f.write(prediction)
    return jsonify({'message': 'Recording stopped', 'prediction': str(prediction)})


# Flask route to analyze the audio file
@app.route('/predictFile', methods=['POST'])
def predictFile():
    # Check if 'audio' file is present in the request
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'})

    audio_data = request.files['audio']
    if audio_data.filename == '':
        return jsonify({'error': 'No selected file'})

    # Preprocess the uploaded audio
    audio_data = preprocess_audio(audio_data)

    # Extract features (ZCR, RMS, MFCCs)
    zcr, rms, mfccs = extract_features(audio_data)

    # Reshape features to match the model input shape
    zcr = zcr.T.reshape(-1, 352, 1)
    rms = rms.T.reshape(-1, 352, 1)
    mfccs = mfccs.T.reshape(-1, 352, 13)

    # Concatenate features
    features = np.concatenate((zcr, rms, mfccs), axis=-1)

    # Make predictions using the model
    predictions = model.predict(features)
    predicted_class = np.argmax(predictions)

    # Decode predicted class to emotion label
    prediction = decode_emotion(predicted_class)

    print('Final Prediction:', prediction)
    return jsonify({'message': 'Audio file stored and analyzed', 'prediction': str(prediction)})


# Flask route to transcribe the audio file
@app.route('/transcribeFile', methods=['POST'])
def transcribeFile():
    # Check if 'audio' file is present in the request
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'})

    audio_data = request.files['audio']
    if audio_data.filename == '':
        return jsonify({'error': 'No selected file'})

    # Initialize recognizer class
    r = sr.Recognizer()
    # audio object
    audio = sr.AudioFile(audio_data)
    # read audio object and transcribe
    with audio as source:
        audio = r.record(source)
        result = r.recognize_google(audio)

    print('Transcribed Audio: ', result)
    return jsonify({'message': 'Transcription finished', 'transcription': str(result)})

# Flask route for logout
@app.route('/logout')
def logout():
    # Add your logout logic here (e.g., clearing session data)
    return render_template('/login.html')

@app.route('/about_us')
def about_us():
    return render_template('/about_us.html')

@app.route('/contact_us')
def contact_us():
    return render_template('/ContactUs.html')

# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)
