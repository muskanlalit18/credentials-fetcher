#!/bin/bash

# Run as root
if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

# Set timezone
TIME_ZONE="UTC"


USER_DIR="/home/ubuntu"  # Default directory

echo "Do you want to use a different directory instead of /home/ubuntu? (y/n)"
read response

if [[ $response =~ ^[Yy]$ ]]; then
    echo "Please enter the directory path:"
    read user_input
    
    if [ -d "$user_input" ]; then
        USER_DIR="$user_input"
    else
        echo "Warning: The directory $user_input does not exist. Using default: $USER_DIR"
    fi
fi

cd "$USER_DIR"

echo "Installing dependencies for credentials-fetcher"
apt-get update \
    && DEBIAN_FRONTEND="noninteractive" TZ="${TIME_ZONE}" \
        apt install -y git clang wget curl autoconf \
        libglib2.0-dev libboost-dev libkrb5-dev libsystemd-dev libssl-dev \
        libboost-program-options-dev libboost-filesystem-dev byacc make \
        libjsoncpp-dev libgtest-dev pip python3.10-venv \
        libsasl2-modules-gssapi-mit:amd64 ldap-utils krb5-config awscli


git clone https://github.com/Kitware/CMake.git -b release \
    && cd CMake && ./configure && make -j4 &&  pwd && make install

if [ $? -ne 0 ]; then
    echo "error: Cmake installation failed"
    exit 1
else
    echo "CMake successfully installed, now installing krb5"
fi

cd "$USER_DIR"


git clone https://github.com/krb5/krb5.git -b krb5-1.21.2-final \
     && cd krb5/src && autoconf && autoreconf && ./configure && make -j4 && make install

if [ $? -ne 0 ]; then
    echo "error: krb5 installation failed"
    exit 1
else
    echo "krb5 successfully installed, now installing grpc"
fi

cd "$USER_DIR"

git clone --recurse-submodules -b v1.58.0 https://github.com/grpc/grpc && mkdir -p grpc/build && cd grpc/build && cmake -DgRPC_INSTALL=ON -DgRPC_BUILD_TESTS=OFF -DCMAKE_CXX_STANDARD=17 ../  && make -j4 && make install

cd "$USER_DIR"

mkdir -p grpc/cmake/build && cd grpc/cmake/build \
    && cmake -DgRPC_BUILD_TESTS=ON ../.. && make grpc_cli \
    && cp grpc_cli /usr/local/bin

if [ $? -ne 0 ]; then
    echo "error: grpc installation failed"
    exit 1
else
    echo "grpc successfully installed, now installing Microsoft packages"
fi
    
cd "$USER_DIR"

wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb \
    && DEBIAN_FRONTEND=noninteractive dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get remove -y 'dotnet*' 'aspnetcore*' 'netstandard*' \
    && rm /etc/apt/sources.list.d/microsoft-prod.list \
    && apt-get update -y \
    && apt-get install -y dotnet-sdk-8.0

mkdir -p /usr/lib64/glib-2.0/ && ln -s '/usr/lib/x86_64-linux-gnu/glib-2.0/include/' '/usr/lib64/glib-2.0/include' && ln -s '/usr/include/jsoncpp/json/' '/usr/include/json'

mkdir -p /var/credentials-fetcher/logging
mkdir -p /var/credentials-fetcher/socket
mkdir -p /var/credentials-fetcher/krbdir

if [ $? -ne 0 ]; then
    echo "error: Microsoft packages installation failed"
    exit 1
else
    echo "Microsoft packages successfully installed. Please follow the instructions in the setup doc to clone the repo and build it"
fi

export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib

cd "$USER_DIR"
git clone -b dev https://github.com/aws/credentials-fetcher.git # update branch as needed
mkdir -p credentials-fetcher/build 
cd credentials-fetcher/build
cmake ../ && make -j4 && make install

