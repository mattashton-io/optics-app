# Base image (e.g., python:3.13-slim)
FROM python:3.13-slim
RUN mkdir templates
COPY templates/index.html templates

RUN pwd
RUN ls
RUN ls templates

# # 1. Install system-level C compilers
# RUN apt-get update && apt-get install -y build-essential

# # 2. ---> ADD THIS LINE <---
# # Upgrade Python's own package building tools
# RUN pip install --upgrade pip setuptools wheel

# 3. Copy and install your app's requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of your app and define the run command
COPY app.py .
CMD ["python3", "app.py"]