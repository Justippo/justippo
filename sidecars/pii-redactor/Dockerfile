FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

COPY app ./app
COPY tests ./tests

EXPOSE 8760

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8760"]
