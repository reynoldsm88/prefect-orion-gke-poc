FROM prefecthq/prefect:2.0b4-python3.8
COPY requirements.txt .
RUN pip install -r requirements.txt
