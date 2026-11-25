FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8776

CMD ["python", "-m", "xingji", "serve", "--host", "0.0.0.0"]
