import os
from flask import Flask, request, render_template, redirect, url_for
from google.cloud import storage, vision
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

@app.route('/', methods=['GET', 'POST'])
def index():
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
                stylized_text = stylize_text_with_gemini(extracted_text)
                return render_template('index.html', extracted_text=stylized_text)
            else:
                return "Error uploading file to GCS", 500
    return render_template('index.html', extracted_text=None)

def upload_to_gcs(file):
    """Uploads a file to Google Cloud Storage."""
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
    try:
        prompt = f"Reformat and stylize the following text into well-structured paragraphs:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error stylizing text with Gemini: {e}")
        return text # Return original text if Gemini fails

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
