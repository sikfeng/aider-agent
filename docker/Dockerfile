FROM python:3.10-slim AS base

RUN apt-get update && \
    apt-get install --no-install-recommends -y build-essential git libportaudio2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Permission kludges to support `docker run --user xxx`
RUN chmod a+rwx /venv /venv/bin /venv/include /venv/lib /venv/lib/python3.10/site-packages

RUN mkdir       /.aider /.cache
RUN chmod a+rwx /.aider /.cache

# So git doesn't complain about unusual permissions
RUN git config --system --add safe.directory /workspace

FROM base AS aider-full

RUN /venv/bin/python -m pip install --upgrade --no-cache-dir pip
#RUN /venv/bin/python -m pip install --no-cache-dir aider-chat[help,browser,playwright]==0.51.1 --extra-index-url https://download.pytorch.org/whl/cpu
RUN /venv/bin/python -m pip install --no-cache-dir aider-chat==0.51.1

#RUN playwright install --with-deps chromium

FROM aider-full AS aider-agent

#COPY . /tmp/aider-agent
#RUN /venv/bin/python -m pip install --no-cache-dir /tmp/aider-agent

ENTRYPOINT ["/bin/bash"]
