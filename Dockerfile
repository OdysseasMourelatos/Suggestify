# Χρησιμοποιούμε Linux με Python 3.11
FROM python:3.11-slim

# Εγκαθιστούμε τη Java (JRE)
RUN apt-get update && apt-get install -y default-jre

# Φτιάχνουμε τον φάκελο εργασίας
WORKDIR /app

# Αντιγράφουμε και εγκαθιστούμε τα requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Αντιγράφουμε όλο τον κώδικα στο Render
COPY . .

# Εντολή εκκίνησης του Streamlit
CMD ["streamlit", "run", "Suggestify/upload.py", "--server.port", "10000", "--server.address", "0.0.0.0"]