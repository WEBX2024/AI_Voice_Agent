FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libportaudio2 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY agent/ agent/
COPY voice/ voice/
COPY tools/ tools/
COPY storage/ storage/
COPY prompts/ prompts/
COPY main.py diagnose.py ./

CMD ["python", "main.py"]