import os
from flask import Flask, request, render_template, redirect, url_for
from google.cloud import storage, vision, translate_v2 as translate
import uuid
import google.generativeai as genai

app = Flask(__name__)

# Configure Gemini API
# Replace with your actual API key
genai.configure(api_key=os.environ["YOUR_GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

# Configure Google Cloud Storage
# Replace with your actual bucket name
BUCKET_NAME = "pytutoring-dev-bucket" 
# Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set
# or provide credentials explicitly.

# Configure Google Cloud Translate
translate_client = translate.Client()

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

                return render_template('index.html', extracted_text=stylized_text)
            else:
                return "Error uploading file to GCS", 500
    return render_template('index.html', extracted_text=None)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
