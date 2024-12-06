FROM mcr.microsoft.com/mssql-tools
RUN cat /etc/os-release
RUN apt-get update -y
RUN apt-get install krb5-user unzip inetutils-ping dnsutils -y
ENV KRB5CCNAME=/var/credentials-fetcher/krbdir/krb5cc
CMD ["sleep", "infinity"]