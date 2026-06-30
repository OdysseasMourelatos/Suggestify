# 1. Βήμα: Εγκαθιστούμε τη Java 23 από τα επίσημα repositories της Eclipse Temurin
FROM eclipse-temurin:23-jre-jammy AS java_runtime

# 2. Βήμα: Συνδυάζουμε την Python για να τρέξει παράλληλα το Streamlit
FROM python:3.11-slim

# Αντιγράφουμε τα εκτελέσιμα της Java 23 από το πρώτο image στο python image
COPY --from=java_runtime /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["streamlit", "run", "Suggestify/upload.py", "--server.port", "10000", "--server.address", "0.0.0.0"]