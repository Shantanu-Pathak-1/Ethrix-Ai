# Use Python 3.10 image
FROM python:3.11

# Working directory set karo
WORKDIR /code

# Requirements copy karo aur install karo
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Permissions Setup (Zaruri hai HF Spaces ke liye)
# Cache folders aur static folders ko write permission do
RUN mkdir -p /code/static && chmod 777 /code/static
RUN mkdir -p /.cache && chmod 777 /.cache

# Copy all files
COPY . .

# Hugging Face Spaces Port 7860 par chalta hai
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
