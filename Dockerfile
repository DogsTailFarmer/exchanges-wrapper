# syntax=docker/dockerfile:1
FROM python:3.10.6-slim

RUN useradd -ms /bin/bash appuser
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"
ENV PATH="/home/appuser/.local/lib/python3.10/site-packages:${PATH}"
ENV PYTHONUNBUFFERED = 1

# RUN pip3 install --no-cache-dir exchanges-wrapper
RUN pip3 install --no-cache-dir -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple exchanges-wrapper

WORKDIR "/home/appuser/.local/lib/python3.10/site-packages"

EXPOSE 50051

CMD ["python3","exchanges_wrapper/exch_srv.py"]
