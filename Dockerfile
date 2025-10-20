FROM python:3.13-slim
COPY . .
RUN apt-get update && apt-get install -y build-essential
RUN pip install -r requirements.txt
CMD ["python3", "app.py"]