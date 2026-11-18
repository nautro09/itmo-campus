FROM mcr.microsoft.com/playwright/python:v1.60.0-noble
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py connect.py extras.py grades.py inbox.py itmo.py mailbox_sync.py menu.py miniapp.py monitor.py planner.py store.py wake.py ./
COPY web/ ./web/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER pwuser
CMD ["python", "bot.py"]
