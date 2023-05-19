FROM continuumio/miniconda3:23.3.1-0

# Install tini
ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

# Copy over requirements
COPY requirements.txt setup.py /chakra/

# Install chakra and requirements
RUN pip install -r /chakra/requirements.txt

# Copy over the rest of the code and install
COPY chakra /chakra/chakra
RUN pip install -e /chakra

ENTRYPOINT ["/tini", "--"]