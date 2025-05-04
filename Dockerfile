# Starta från en Python-baserad image
FROM python:3.12-slim

# Skapa en icke-root användare
RUN useradd -m flaskuser

# Ange arbetskatalog i containern
WORKDIR /app

# Kopiera kraven för Python-paket
COPY requirements.txt requirements.txt

# Ange versionen som har byggts
ARG BUILD_VERSION=0
ARG BUILD_DATE=0
ENV BUILD_VERSION=$BUILD_VERSION
ENV BUILD_DATE=$BUILD_DATE

RUN echo "BUILD_VERSION=$BUILD_VERSION"
RUN echo "BUILD_DATE=$BUILD_DATE"

# Installera Python-paket
RUN pip install --no-cache-dir -r requirements.txt

# Kopiera hela applikationen till containern
COPY src/ .
RUN mkdir -p /app/data

# Kopiera entrypoint-skriptet
COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

# Ändra ägare av applikationsfiler till den icke-root användaren
RUN chown -R flaskuser:flaskuser /app

# Byt till icke-root användaren
USER flaskuser

# Exponera porten som Flask körs på
EXPOSE 8000

# Kör entrypoint-skriptet
CMD ["./entrypoint.sh"]

