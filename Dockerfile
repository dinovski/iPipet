FROM ubuntu:16.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies for building Python
RUN apt-get update && apt-get install -y \
    sudo \
    curl \
    wget \
    build-essential \
    libssl-dev \
    libffi-dev \
    zlib1g-dev \
    libbz2-dev \
    libsqlite3-dev \
    ca-certificates \
    && apt-get clean

RUN update-ca-certificates

# Download and compile Python 3.4 from source
RUN wget https://www.python.org/ftp/python/3.4.10/Python-3.4.10.tgz && \
    tar xvf Python-3.4.10.tgz && \
    cd Python-3.4.10 && \
    ./configure --enable-optimizations && \
    make -j$(nproc) && \
    make altinstall && \
    cd .. && \
    rm -rf Python-3.4.10*

RUN wget https://bootstrap.pypa.io/pip/3.4/get-pip.py && python3.4 get-pip.py

    # Create the 'ipipet' system user BEFORE changing permissions
RUN adduser --system --group --no-create-home ipipet

# Create required directories and assign permissions
RUN mkdir -p /var/run/ipipet /var/log/ipipet \
    && chown ipipet:ipipet /var/run/ipipet /var/log/ipipet \
    && chmod 0755 /var/run/ipipet /var/log/ipipet

# Set the working directory
WORKDIR /app

# Copy the Flask app
COPY . /app

# Install dependencies using pip
RUN python3.4 -m ensurepip && python3.4 -m pip install -r requirements.txt

# Expose Flask port
EXPOSE 5000

EXPOSE 5106

EXPOSE 5105

# Run the Flask app
CMD ["bash", "-c", "./pooling.sh start && tail -f /dev/null"]
