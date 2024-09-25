FROM python:3.10-bookworm AS base

RUN apt-get update && \
    apt-get install --no-install-recommends -y build-essential git libportaudio2 gnupg2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Permission kludges to support `docker run --user xxx`
RUN chmod a+rwx /venv /venv/bin /venv/include /venv/lib /venv/lib/python3.10/site-packages

RUN mkdir       /.aider /.cache
RUN chmod a+rwx /.aider /.cache

# So git doesn't complain about unusual permissions
#RUN git config --system --add safe.directory /workspace
RUN git config --system --add safe.directory "*"

ARG AIDER_VERSION=0.57.0

FROM base AS aider

RUN /venv/bin/python -m pip install --upgrade --no-cache-dir pip
RUN /venv/bin/python -m pip install --no-cache-dir aider-chat==${AIDER_VERSION}

FROM base AS aider-full

RUN /venv/bin/python -m pip install --upgrade --no-cache-dir pip
RUN /venv/bin/python -m pip install --no-cache-dir aider-chat[help,browser,playwright]==${AIDER_VERSION} --extra-index-url https://download.pytorch.org/whl/cpu
RUN playwright install --with-deps chromium

FROM aider AS raider-backend

COPY requirements.txt /tmp
RUN /venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt
RUN rm /tmp/requirements.txt
