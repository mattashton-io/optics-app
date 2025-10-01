import os
from flask import Flask, request, render_template, redirect, url_for, send_from_directory
from google.cloud import storage, vision, translate_v2 as translate, texttospeech
from google.cloud import secretmanager
import uuid
import google.generativeai as genai

app = Flask(__name__)

# Function to access secret from Secret Manager
def access_secret_version(secret_version_name):
    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(name=secret_version_name)
    return response.payload.data.decode('UTF-8')

# Configure Gemini API
gemini_api_key = access_secret_version("projects/396631018769/secrets/optics-app-gemini/versions/latest")
genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-2.5-pro')

# Configure Google Cloud Storage
# Replace with your actual bucket name
BUCKET_NAME = "pytutoring-dev-bucket" 
STATIC_DIR = "/usr/local/google/home/mattashton/Documents/pyTutoring/optics-app/static"
# Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set
# or provide credentials explicitly.

# Configure Google Cloud Translate
translate_client = translate.Client()

# Configure Google Cloud Text-to-Speech
tts_client = texttospeech.TextToSpeechClient()
voices = tts_client.list_voices()
supported_languages_for_tts = {lang for voice in voices.voices for lang in voice.language_codes}

#print("voices: ", voices)
print("supported languaged dict:", supported_languages_for_tts)

#filtering languages to what is actually used in the app
scoped_languages = []
for lang in supported_languages_for_tts:
    scoped_languages.append(lang[-2:].lower())
scoped_languages += ["zh-CN", "en"]
print("scoped languages: ", scoped_languages)

@app.route('/', methods=['GET', 'POST'])
def index():
    print("beginning index")
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file:
            # Upload image to GCS
            gcs_path = upload_to_gcs(file)
            if gcs_path:
                # Perform OCR
                extracted_text = detect_text_from_gcs(gcs_path)
                
                target_language = request.form.get('language', 'en')
                if target_language != 'en':
                    translated_text = translate_text(extracted_text, target_language)
                else:
                    translated_text = extracted_text

                stylized_text = stylize_text_with_gemini(translated_text)
                audio_file_path = text_to_speech(stylized_text, target_language)

                return render_template('index.html', extracted_text=stylized_text, audio_file=audio_file_path)
            else:
                return "Error uploading file to GCS", 500
    return render_template('index.html', extracted_text=None, audio_file=None)

def upload_to_gcs(file):
    """Uploads a file to Google Cloud Storage."""
    print("beginning upload_to_gcs")
    try:
        client = storage.Client()
        bucket = client.get_bucket(BUCKET_NAME)
        blob_name = f"uploads/{uuid.uuid4()}_{file.filename}"
        blob = bucket.blob(blob_name)
        blob.upload_from_file(file, content_type=file.content_type)
        return f"gs://{BUCKET_NAME}/{blob_name}"
    except Exception as e:
        print(f"Error uploading to GCS: {e}")
        return None

def detect_text_from_gcs(gcs_uri):
    """Detects text in the image located in Google Cloud Storage or on the Web."""
    print("beginning detect_text_from_gcs")
    client = vision.ImageAnnotatorClient()
    image = vision.Image(source=vision.ImageSource(image_uri=gcs_uri))
    response = client.text_detection(image=image)
    texts = response.text_annotations

    if texts:
        return texts[0].description
    else:
        return "No text found."

def stylize_text_with_gemini(text):
    """Uses Gemini API to reformat and stylize text into paragraphs."""
    print("beginning stylize_text_with_gemini")
    try:
        prompt = f"Reformat and stylize the following text into well-structured paragraphs, but do not generate filler content or insert new words beyond what is in the provided text:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error stylizing text with Gemini: {e}")
        return text # Return original text if Gemini fails

def translate_text(text, target_language):
    """Translates text into the target language."""
    print(f"Translating to {target_language}")
    try:
        result = translate_client.translate(text, target_language=target_language)
        return result['translatedText']
    except Exception as e:
        print(f"Error translating text: {e}")
        return text

def text_to_speech(text, language_code):
    """Synthesizes speech from text."""
    print("Synthesizing speech")
    
    print("language code: ", language_code)
    if language_code not in scoped_languages:
        return "Language not supported for audio playback."

    # Truncate text to avoid exceeding API limits
    truncated_text = text[:4500]
    synthesis_input = texttospeech.SynthesisInput(text=truncated_text)
    
    # Adjust voice based on language
    if language_code.startswith('en'):
        voice_name = 'en-US-Wavenet-D'
    elif language_code.startswith('es'):
        voice_name = 'es-ES-Wavenet-B'
    elif language_code.startswith('ru'):
        voice_name = 'ru-RU-Wavenet-A'
    elif language_code.startswith('zh'):
        voice_name = 'cmn-CN-Wavenet-A'
    elif language_code.startswith('fa'):
        voice_name = 'fa-IR-Wavenet-A'
    elif language_code.startswith('sw'):
        voice_name = 'sw-KE-Wavenet-A'
    elif language_code.startswith('hi'):
        voice_name = 'hi-IN-Wavenet-A'
    elif language_code.startswith('fr'):
        voice_name = 'fr-FR-Wavenet-A'
    else:
        voice_name = 'en-US-Wavenet-D' # Default

    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code, name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    try:
        response = tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
    except Exception as e:
        print(f"Error synthesizing speech: {e}")
        return "Error generating audio."
    
    #print current working dir + create naming convention for generated audio files
    print("os.getcwd = ", os.getcwd())
    audio_filename = f"output-{uuid.uuid4()}.mp3"

    #Create folder to store generated audio
    os.system(f"mkdir -p {STATIC_DIR}")
    audio_filepath = os.path.join(STATIC_DIR, audio_filename)
    with open(audio_filepath, "wb") as out:
        out.write(response.audio_content)
        print(f'Audio content written to file "{audio_filepath}"')

    return audio_filename

@app.route('/static/<filename>')
def static_files(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
