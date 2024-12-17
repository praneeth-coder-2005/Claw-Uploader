FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Install libmagic
RUN apt-get update && apt-get install -y libmagic1

COPY . .

CMD ["python", "your_bot_script.py"]
