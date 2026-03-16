FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn python-multipart aiofiles
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=chodocus123
EXPOSE 7860
CMD ["python", "main.py"]
