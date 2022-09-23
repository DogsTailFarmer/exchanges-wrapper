# syntax=docker/dockerfile:1
FROM python:3.10.6-slim

RUN useradd -ms /bin/bash appuser
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"
ENV PATH="/home/appuser/.local/lib/python3.10/site-packages:${PATH}"
ENV PYTHONUNBUFFERED = 1

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY ./exchanges_wrapper/* /home/appuser/.local/lib/python3.10/site-packages/exchanges_wrapper/

WORKDIR "/home/appuser/.local/lib/python3.10/site-packages"

LABEL org.opencontainers.image.description = "See README.md 'Get started' for setup and run package"

EXPOSE 50051

CMD ["python3","exchanges_wrapper/exch_srv.py"]
