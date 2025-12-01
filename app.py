import os
from flask import Flask, request, render_template, send_from_directory
from google.cloud import storage, vision, translate_v2 as translate, texttospeech
from google.cloud import secretmanager
import google.generativeai as genai
import uuid
import time
from functools import wraps


# Configure Google Cloud Storage
# Replace with your actual bucket name
BUCKET_NAME = "optics-app-uploads" 
STATIC_DIR  = "static"
os.system(f"mkdir -p {STATIC_DIR}")

# Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set
# or provide credentials explicitly.

# Check system clock for time (miliseconds) since the UNIX epoch (1/1/1970)
start_time = time.time()

def time_profile(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = time.time()
        result = f(*args, **kw)
        te = time.time()
        print('func:%r took: %2.4f sec' % \
          (f.__name__, te-ts))
        return result
    return wrap
# init Flask app
app = Flask(__name__)


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

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/ocr', methods=['POST'])
def ocr():
    print("ocr route line 61")
    if 'file' not in request.files:
        return {"error": "No file part"}, 400
    file = request.files['file']
    if file.filename == '':
        return {"error": "No selected file"}, 400
    if file:
        gcs_path = upload_to_gcs(file)
        if gcs_path:
            text = detect_text_from_gcs(gcs_path)
            return {"text": text}
        else:
            return {"error": "Error uploading file to GCS"}, 500
    return {"error": "File processing error"}, 500

@app.route('/translate', methods=['POST'])
def translate():
    data = request.get_json()
    text = data.get('text')
    language = data.get('language')
    if not text or not language:
        return {"error": "Missing text or language"}, 400
    
    if language != 'en':
        translated_text = translate_text(text, language)
    else:
        translated_text = text
    return {"text": translated_text}

@app.route('/stylize', methods=['POST'])
def stylize():
    data = request.get_json()
    text = data.get('text')
    if not text:
        return {"error": "Missing text"}, 400
    stylized_text = stylize_text_with_gemini(text)
    return {"text": stylized_text}

@app.route('/synthesize', methods=['POST'])
def synthesize():
    print("begin text synthesis on line 100")
    text = request.form.get('text')
    language = request.form.get('language')

    if not text or not language:
        return {"error": "Missing text or language"}, 400
    try:
        audio_file_path = text_to_speech(text, language)
    except Exception as e:
        print (e)
        return {"error": "error in text_to_speech"},400 
    
    if "Error" in audio_file_path:
        return {"error": audio_file_path}, 500

    return {"audio_file": audio_file_path}

# @app.route('/plot', methods=['POST'])
# def plot():
#     data = request.get_json()
#     text = data.get('text')
#     if not text:
#         return {"error": "Missing text"}, 400
    
#     # Generate plot
#     try:
#         # Simple word count
#         words = text.lower().split()
#         word_counts = Counter(words)
#         most_common_words = word_counts.most_common(15)

#         if not most_common_words:
#             return {"plot_url": None}

#         labels, values = zip(*most_common_words)

#         fig, ax = plt.subplots(figsize=(10, 8))
#         ax.barh(labels, values, color='skyblue')
#         ax.set_xlabel('Frequency')
#         ax.set_title('Top 15 Most Common Words')
#         plt.gca().invert_yaxis()
#         plt.tight_layout()

#         # Save plot to a bytes buffer
#         buf = io.BytesIO()
#         plt.savefig(buf, format='png')
#         buf.seek(0)
        
#         plot_filename = f"plot-{uuid.uuid4()}.png"
#         plot_filepath = os.path.join(STATIC_DIR, plot_filename)
#         with open(plot_filepath, "wb") as out:
#             out.write(buf.read())

#         return {"plot_url": url_for('static', filename=plot_filename)}
#     except Exception as e:
#         print(f"Error generating plot: {e}")
#         return {"error": "Failed to generate plot"}, 500

@time_profile
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

@time_profile
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

# @time_profile
# def stylize_text_with_gemini(text):
#     """Uses local model to reformat and stylize text into paragraphs."""
#     print("beginning stylize_text_with_local_model")
#     try:
#         prompt = f"Reformat and stylize the following text into well-structured paragraphs, but do not generate filler content or insert new words beyond what is in the provided text:\n\n{text[:10]}"
#         print(prompt)
#         # Assuming the local model has a similar API to OpenAI's completion
#         # and is running on localhost:11434
#         response = requests.post("http://localhost:11434/api/generate", json={
#             "model": "gemma3n:e4b", # model name is often required
#             "prompt": prompt,
#             "stream": False
#         })
#         response.raise_for_status()
#         # Assuming the response format is similar to OpenAI's
#         return response.json()['response'].strip()
#     except Exception as e:
#         print(f"Error stylizing text with local model: {e}")
#         return text # Return original text if it fails

@time_profile
def stylize_text_with_gemini(text):
    """Uses Gemini API to reformat and stylize text into paragraphs."""
    print("beginning stylize_text_with_gemini")
    try:
        # Create the Secret Manager client.
        client = secretmanager.SecretManagerServiceClient()

        # Build the resource name of the secret version.
        name = "projects/396631018769/secrets/optics-app-gemini/versions/latest"

        # Access the secret version.
        response = client.access_secret_version(request={"name": name})

        # Extract the payload.
        secret_string = response.payload.data.decode("UTF-8")

        genai.configure(api_key=secret_string)
        model = genai.GenerativeModel('gemini-2.5-flash-lite') #gemini-3-pro-preview
        prompt = f"Reformat and stylize the following text into well-structured paragraphs, but do not generate filler content or insert new words beyond what is in the provided text:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error stylizing text with Gemini: {e}")
        return text # Return original text if Gemini fails

@time_profile
def translate_text(text, target_language):
    """Translates text into the target language."""
    print(f"Translating to {target_language}")
    try:
        result = translate_client.translate(text, target_language=target_language)
        return result['translatedText']
    except Exception as e:
        print(f"Error translating text: {e}")
        return text

@time_profile
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
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
