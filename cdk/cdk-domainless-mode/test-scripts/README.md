### Test Scripts 

#### Pre Requisites
- Ensure cdk stack is deployed to your personal account
- Create a new AL2023/Ubuntu instance in the ADStack VPC
- Install credentials-fetcher dependencies using dnf
```aiignore
dnf install -y realmd
dnf install -y oddjob
dnf install -y oddjob-mkhomedir
dnf install -y sssd
dnf install -y adcli
dnf install -y krb5-workstation
dnf install -y samba-common-tools
```
- Install the latest credentials-fetcher rpm in this instance
- Run credentials-fetcher rpm as a systemd process
```aiignore
systemctl start credentials-fetcher
systemctl status credentials-fetcher
```
- Clone credentials-fetcher repo and create a python proto file
```aiignore
git clone -b dev https://github.com/aws/credentials-fetcher.git
cd credentials-fetcher/protos
python3 -m venv .venv
source .venv/bin/activate
pip install grpcio-tools
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. 
credentialsfetcher.proto
cp *.py /home/ec2-user/credentials-fetcher/cdk/test-scripts
```

#### 1. Create Domain Joined Kerberos Leases

Use this script to create and test N leases for N domain-joined gMSA 
accounts. This script is run on a linux instance in stand-alone mode.

#### 2. Create Non Domain Joined Kerberos Leases

Use this script to create and test N leases for N non domain-joined gMSA
accounts. This script is run on a linux instance in stand-alone mode.

#### 3. Add Delete Kerberos Leases

Use this script to create and delete N kerberos leases in a recurring loop 
(currently set to 100 times). This script is run to test that create/delete 
functionality has no leaks or unexpected failures when run over a long 
period of time. This script is run on a linux instance in stand-alone mode.

#### 4. Create Domain Joined AD accounts

Use this script to create new Domain Joined gMSA accounts and add them to 
the AD. This script is run on the Windows Instance with access to Managed AD.

#### 5. Create Non Domain Joined AD accounts

Use this script to create new Non Domain Joined gMSA accounts and add them to
the AD. This script is run on the Windows Instance with access to Managed AD.