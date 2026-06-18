FROM python:3.12-alpine

# Install docker CLI (no daemon, just the client to talk to mounted socket)
RUN apk add --no-cache docker-cli curl

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

EXPOSE 9999

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:9999", "--timeout", "30", "agent:app"]
