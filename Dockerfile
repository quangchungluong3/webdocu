FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=chodocus123
EXPOSE 7860
CMD ["python", "main.py"]
