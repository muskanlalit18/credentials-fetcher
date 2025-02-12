# Credentials Fetcher

`credentials-fetcher` is a Linux daemon that retrieves gMSA credentials from Active Directory over LDAP. It creates and refreshes kerberos tickets from gMSA credentials. Kerberos tickets can be used by containers to run apps/services that authenticate using Active Directory.

This daemon works in a similar way as ccg.exe and the gMSA plugin in Windows as described in - https://docs.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/manage-serviceaccounts#gmsa-architecture-and-improvements

### How to install and run

- To use the custom credentials-fetcher rpm in ECS domainless mode, modify the user data script as follows
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/linux-gmsa.html#linux-gmsa-setup

    ```
    #!/bin/bash

    # prerequisites
    dnf install -y dotnet
    dnf install -y realmd
    dnf install -y oddjob
    dnf install -y oddjob-mkhomedir
    dnf install -y sssd
    dnf install -y adcli
    dnf install -y krb5-workstation
    dnf install -y samba-common-tools
    dnf install -y credentials-fetcher

    # start credentials-fetcher
    systemctl enable credentials-fetcher
    systemctl start credentials-fetcher

    echo "ECS_GMSA_SUPPORTED=true" >> /etc/ecs/ecs.config       
    echo ECS_CLUSTER=MyCluster >> /etc/ecs/ecs.config
    ```


    Add an additional optional field in the secret in AWS Secrets Manager along with the standard user's username, password, and the domain. Enter the service account's Distinguished Name (DN) into JSON key-value pairs called `distinguishedName`

    ```
    {"username":"username","password":"passw0rd", "domainName":"example.com", "distinguishedName":"CN=WebApp01,OU=DemoOU,OU=Users,OU=example,DC=example,DC=com"}
    ```

- On [Fedora 41](_https://alt.fedoraproject.org/cloud/_) and similar distributions, the binary RPM can be installed as
`sudo dnf install credentials-fetcher`.
You can also use yum if dnf is not present.
The daemon can be started using `sudo systemctl start credentials-fetcher`.

- On Enterprise Linux 9 ( RHEL | CentOS | AlmaLinux ), the binary can be installed from EPEL. To add EPEL, see the [EPEL Quickstart](_https://docs.fedoraproject.org/en-US/epel/#_quickstart_).
Once EPEL is enabled, install credentials-fetcher with
`sudo dnf install credentials-fetcher`.

- For other linux distributions, the daemon binary needs to be built from source code.

## Development

### Prerequisites

- Active Directory server ( Windows Server )
- Linux instances or hosts that are domain-joined to Active Directory
  - [EC2 Linux containers on Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/linux-gmsa.html#linux-gmsa-considerations) provides the option of domainless gMSA and joining each instance to a single domain
  - [Linux containers on Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-linux-gmsa.html#fargate-linux-gmsa-considerations) must use domainless gMSA
- gMSA account(s) in Active Directory - Follow instructions provided to create service accounts - https://docs.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/manage-serviceaccounts
- Required packages as mentioned in RPM spec file.
- Create username ec2-user or modify the systemd unit file.

#### Create credentialspec associated with gMSA account:

- Create a domain joined windows instance
- Install powershell module - "Install-Module CredentialSpec"
- New-CredentialSpec -AccountName WebApp01 // Replace 'WebApp01' with your own gMSA
- You will find the credentialspec in the directory
  'C:\\Program Data\\Docker\\Credentialspecs\\WebApp01_CredSpec.json'

#### Standalone mode

To start a local dev environment from scratch:

```
* Clone the Git repository.
* cd credentials-fetcher && mkdir build
* cd build && cmake ../ && make -j && make install 
* ./credentials-fetcherd to start the program in non-daemon mode.
```

## Logging

Logs about request/response to the daemon and any failures.

```
journalctl -u credentials-fetcher
```

### Default environment variables

| Environment Key             | Examples values                    | Description                                                                                  |
| :-------------------------- | ---------------------------------- | :------------------------------------------------------------------------------------------- |
| `CF_KRB_DIR`                | '/var/credentials-fetcher/krbdir'  | _(Default)_ Dir path for storing the kerberos tickets                                        |
| `CF_UNIX_DOMAIN_SOCKET_DIR` | '/var/credentials-fetcher/socket'  | _(Default)_ Dir path for the domain socker for gRPC communication 'credentials_fetcher.sock' |
| `CF_LOGGING_DIR`            | '/var/credentials-fetcher/logging' | _(Default)_ Dir Path for log                                                                 |
| `CF_TEST_DOMAIN_NAME`       | 'contoso.com'                      | Test domain name                                                                             |
| `CF_TEST_GMSA_ACCOUNT`      | 'webapp01'                         | Test gMSA account name                                                                       |

### Runtime environment variables

| Environment Variable | Examples values                                       | Description                                                                |
| :------------------- | ----------------------------------------------------- | :------------------------------------------------------------------------- |
| `CF_CRED_SPEC_FILE`  | '/var/credentials-fetcher/my-credspec.json'           | Path to a credential spec file used as input. (Lease id default: credspec) |
|                      | '/var/credentials-fetcher/my-credspec.json:myLeaseId' | An optional lease id specified after a colon                               |
| `CF_GMSA_OU`         | 'CN=Managed Service Accounts'                         | Component of GMSA distinguished name (see docs/cf_gmsa_ou.md)              |


## Testing

### Test using Personal CDK Stack

Use the AWS CDK to create 
- Active Directory Server
- Windows EC2 instance to manage AD
- EC2 Linux Containers on Amazon ECS
- gMSA Account(s) in Active Directory  
The CDK will create all necessary infrastructure and install the necessary dependencies to run credentials-fetcher on non-domain-joined ECS hosts. Detailed steps to deploy and test using the CDK stack are present [here](https://github.com/aws/credentials-fetcher/blob/mainline/cdk/cdk-domainless-mode/README.md).

### Test APIs using Integration Test Script

`/api/tests/gmsa_api_integration_test.cpp` contains integration tests for the of the gMSA APIs.

#### Prerequisites
Follow the instructions in the [Domainless Mode README](cdk/cdk-domainless-mode/README.md) to set up the required infrastructure for testing gMSA on Linux containers.

#### Setup
Set AWS environment variables
```
export AWS_ACCESS_KEY_ID=XXXX
export AWS_SECRET_ACCESS_KEY=XXXX
export AWS_SESSION_TOKEN=XXXX
export AWS_REGION=XXXX
```

Set Amazon S3 ARN containing the credential spec file. 
```
export CF_TEST_CREDSPEC_ARN=XXX
```

Set standard username, password and domain used for testing
```
export CF_TEST_STANDARD_USERNAME=XXXX
export CF_TEST_STANDARD_USER_PASSWORD=XXXX
export CF_TEST_DOMAIN=XXXX
``` 

#### Build && Test
Follow the instructions from [Standalone mode](#standalone-mode) sections to build the code with the integration test flag enabled, generate binaries and start the server. Once the server has started, run integration tests

```
cd credentials-fetcher/build/
cmake -DBUILD_INTEGRATION_TESTS=ON .. && make -j
# Start the server from another terminal and run `sudo ./credentials-fetcherd`
sudo -E api/tests/gmsa_api_integration_test 
```

#### Sample output
```
> sudo api/tests/gmsa_api_integration_test 
[==========] Running 6 tests from 1 test suite.
[----------] Global test environment set-up.
[----------] 6 tests from GmsaIntegrationTest
[ RUN      ] GmsaIntegrationTest.HealthCheck_Test
[       OK ] GmsaIntegrationTest.HealthCheck_Test (4 ms)
[ RUN      ] GmsaIntegrationTest.A_AddNonDomainJoinedKerberosLeaseMethod_Test
[       OK ] GmsaIntegrationTest.A_AddNonDomainJoinedKerberosLeaseMethod_Test (1028 ms)
[ RUN      ] GmsaIntegrationTest.B_RenewNonDomainJoinedKerberosLeaseMethod_Test
[       OK ] GmsaIntegrationTest.B_RenewNonDomainJoinedKerberosLeaseMethod_Test (553 ms)
[ RUN      ] GmsaIntegrationTest.C_DeleteKerberosLeaseMethod_Test
[       OK ] GmsaIntegrationTest.C_DeleteKerberosLeaseMethod_Test (7 ms)
[ RUN      ] GmsaIntegrationTest.A_AddKerberosArnLeaseMethod_Test
[       OK ] GmsaIntegrationTest.A_AddKerberosArnLeaseMethod_Test (768 ms)
[ RUN      ] GmsaIntegrationTest.B_RenewKerberosArnLeaseMethod_Test
[       OK ] GmsaIntegrationTest.B_RenewKerberosArnLeaseMethod_Test (691 ms)
[----------] 6 tests from GmsaIntegrationTest (3054 ms total)

[----------] Global test environment tear-down
[==========] 6 tests from 1 test suite ran. (3054 ms total)
[  PASSED  ] 6 tests.
```

### Testing Tips without using CDK stack or Test Scripts

To communicate with the daemon over gRPC, install grpc-cli. For example
`sudo yum install grpc-cli`

##### AddKerberosLease API:

Note: APIs use unix domain socket

```
Invoke the AddkerberosLease API with the credentialsspec input as shown:
grpc_cli call {unix_domain_socket} AddKerberosLease "credspec_contents: '{credentialspec}'"

Sample:
grpc_cli call unix:/var/credentials-fetcher/socket/credentials_fetcher.sock
AddKerberosLease "credspec_contents: '{\"CmsPlugins\":[\"ActiveDirectory\"],\"DomainJoinConfig\":{\"Sid\":\"S-1-5-21-4217655605-3681839426-3493040985\",
\"MachineAccountName\":\"WebApp01\",\"Guid\":\"af602f85-d754-4eea-9fa8-fd76810485f1\",\"DnsTreeName\":\"contoso.com\",
\"DnsName\":\"contoso.com\",\"NetBiosName\":\"contoso\"},\"ActiveDirectoryConfig\":{\"GroupManagedServiceAccounts\":[{\"Name\":\"WebApp01\",\"Scope\":\"contoso.com\"}
,{\"Name\":\"WebApp01\",\"Scope\":\"contoso\"}]}}'"

* Response:
  lease_id - unique identifier associated to the request
  created_kerberos_file_paths - Paths associated to the Kerberos tickets created corresponding to the gMSA accounts
```

##### DeleteKerberosLease API:

```
Invoke the Delete kerberosLease API with lease id input as shown:
grpc_cli call {unix_domain_socket} DeleteKerberosLease "lease_id: '{lease_id}'"

Sample:
grpc_cli call unix:/var/credentials-fetcher/socket/credentials_fetcher.sock DeleteKerberosLease "lease_id: '${response_lease_id_from_add_kerberos_lease}'"

* Response:
    lease_id - unique identifier associated to the request
    deleted_kerberos_file_paths - Paths associated to the Kerberos tickets deleted corresponding to the gMSA accounts

```

### Examples

#### Testing with Active Directory domain-joined mode (opensource)
 Credentials-fetcher in domainless mode assuming gMSA account 'WebApp01' has been setup as per https://learn.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/manage-serviceaccounts#use-case-for-creating-gmsa-account-for-domain-joined-container-hosts

 * Either launch Amazon-Linux 2023 instance or build from source and run.
 * Make sure the instance/server is domain-joined using the `realm list` command in Linux.
 * Make sure Credentials-fetcher is running using:
 
        journalctl -u credentials-fetcher
 
* Install grpc for python as per https://grpc.io/docs/languages/python/quickstart/
*  Create the grpc pb2 files using [credentialsfetcher.proto](https://github.com/aws/credentials-fetcher/blob/mainline/protos/credentialsfetcher.proto):

       # python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. credentialsfetcher.proto

*    Copy this code ([Create the credspec](https://learn.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/manage-serviceaccounts#create-a-credential-spec) and add it to the script as below ) (Alternatively, configure using the managed services at [AWS ECS mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/linux-gmsa.html) and [AWS Fargate mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-linux-gmsa.html)
)

            # cat credentials_fetcher_client.py
            import grpc
            import credentialsfetcher_pb2
            import credentialsfetcher_pb2_grpc

            def run():
            with grpc.insecure_channel('unix:///var/credentials-fetcher/socket/credentials_fetcher.sock') as channel:
                stub = credentialsfetcher_pb2_grpc.CredentialsFetcherServiceStub(channel)
                credspec_contents="{\"CmsPlugins\":[\"ActiveDirectory\"],\"DomainJoinConfig\":{\"Sid\":\"S-1-5-21-2725122404-4129967127-2630707939\",\"MachineAccountName\":\"WebApp01\",\"Guid\":\"e96e0e09-9305-462f-9e44-8a8179722897\",\"DnsTreeName\":\"contoso.com\",\"DnsName\":\"contoso.com\",\"NetBiosName\":\"contoso\"},\"ActiveDirectoryConfig\":{\"GroupManagedServiceAccounts\":[{\"Name\":\"WebApp01\",\"Scope\":\"contoso.com\"},{\"Name\":\"WebApp01\",\"Scope\":\"contoso\"}]}}"
                contents = []
                contents += [credspec_contents]
                response = stub.AddKerberosLease(credentialsfetcher_pb2.CreateKerberosLeaseRequest(credspec_contents = contents))
                print(f"Server response: {response}")

            if __name__ == '__main__':
                run()

*   Configure Credentials-fetcher to create tickets for the 'WebApp01' gMSA account.

        # python3 credentials_fetcher_client.py
            Server response: lease_id: "94efba947d75728bbf70"
            created_kerberos_file_paths: "/var/credentials-fetcher/krbdir/94efba947d75728bbf70/WebApp01"

* Here is the resulting kerberos ticket that can be shared

        # klist  /var/credentials-fetcher/krbdir/94efba947d75728bbf70/WebApp01/krb5cc
            Ticket cache: FILE:/var/credentials-fetcher/krbdir/94efba947d75728bbf70/WebApp01/krb5cc
            Default principal: WebApp01$@CONTOSO.COM

      Valid starting     Expires            Service principal
      07/17/24 22:42:42  07/18/24 08:42:42  krbtgt/CONTOSO.COM@CONTOSO.COM
	    renew until 07/24/24 22:42:42

#### Testing with Active Directory domainless mode (opensource )

 Credentials-fetcher in domainless mode assuming gMSA account 'WebApp01' has been setup as per https://learn.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/manage-serviceaccounts#use-case-for-creating-gmsa-account-for-non-domain-joined-container-hosts 
( Please substitute username, secret and password as needed)

* Run credentials-fetcher as follows:

        # credentials-fetcherd --aws_sm_secret_name aws/directoryservices/d-xxxxxx/gmsa // Substitute your secret name in AWS secrets manager

* Install grpc for python as per https://grpc.io/docs/languages/python/quickstart/

* Create the grpc pb2 files using [credentialsfetcher.proto](https://github.com/aws/credentials-fetcher/blob/mainline/protos/credentialsfetcher.proto):

       # python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. credentialsfetcher.proto

*    Copy this code ([Create the credspec](https://learn.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/manage-serviceaccounts#create-a-credential-spec) and add it to the script as below ) (Alternatively, configure using the managed services at [AWS ECS mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/linux-gmsa.html) and [AWS Fargate mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-linux-gmsa.html)
)

    #  cat credentials_fetcher_client.py

        import grpc
        import credentialsfetcher_pb2
        import credentialsfetcher_pb2_grpc

        def run():
            with grpc.insecure_channel('unix:///var/credentials-fetcher/socket/credentials_fetcher.sock') as channel:
                stub = credentialsfetcher_pb2_grpc.CredentialsFetcherServiceStub(channel)
                credspec_contents="{\"CmsPlugins\":[\"ActiveDirectory\"],\"DomainJoinConfig\":{\"Sid\":\"S-1-5-21-2725122404-4129967127-2630707939\",\"MachineAccountName\":\"WebApp01\",\"Guid\":\"e96e0e09-9305-462f-9e44-8a8179722897\",\"DnsTreeName\":\"contoso.com\",\"DnsName\":\"contoso.com\",\"NetBiosName\":\"contoso\"},\"ActiveDirectoryConfig\":{\"GroupManagedServiceAccounts\":[{\"Name\":\"WebApp01\",\"Scope\":\"contoso.com\"},{\"Name\":\"WebApp01\",\"Scope\":\"contoso\"}]}}"
                contents = []
                contents += [credspec_contents]
                response = stub.AddNonDomainJoinedKerberosLease(credentialsfetcher_pb2.CreateNonDomainJoinedKerberosLeaseRequest(credspec_contents = contents, username="admin", password="mypassword", domain="contoso.com"))
                print(f"Server response: {response}")

        if __name__ == '__main__':
            run()


*   Configure Credentials-fetcher (in opensource mode) to create tickets for the 'WebApp01' gMSA account ( Alternatively, configure using the managed services at [AWS ECS mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/linux-gmsa.html) and [AWS Fargate mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-linux-gmsa.html))

        # python3 credentials_fetcher_client.py

            Server response: lease_id: "34e2b89e3fd8a9bcb297"
            created_kerberos_file_paths: "/var/credentials-fetcher/krbdir/34e2b89e3fd8a9bcb297/WebApp01"

*   Here is the resulting kerberos ticket that can be shared

        # klist  /var/credentials-fetcher/krbdir/34e2b89e3fd8a9bcb297/WebApp01/krb5cc

            Ticket cache: FILE:/var/credentials-fetcher/krbdir/34e2b89e3fd8a9bcb297/WebApp01/krb5cc
            Default principal: WebApp01$@CONTOSO.COM

            Valid starting     Expires            Service principal
            07/17/24 22:10:29  07/18/24 08:10:29  krbtgt/CONTOSO.COM@CONTOSO.COM
                renew until 07/18/24 22:10:29


## Compatibility

On Amazon Linux 2023, only Linux x86_64 architecture is supported. Running the Credentials-fetcher outside of Linux distributions is not
supported.

## Contributing

Contributions and feedback are welcome! Proposals and pull requests will be considered and responded to. For more
information, see the [CONTRIBUTING.md](https://github.com/aws/credentials-fetcher/blob/master/CONTRIBUTING.md) file.
If you have a bug/and issue around the behavior of the credentials-fetcher,
please open it here.

Amazon Web Services does not currently provide support for modified copies of this software.

## Security disclosures

If you think you’ve found a potential security issue, please do not post it in the Issues. Instead, please follow the instructions [here](https://aws.amazon.com/security/vulnerability-reporting/) or [email AWS security directly](mailto:aws-security@amazon.com).

## License

The Credentials Fetcher is licensed under the Apache 2.0 License.
See [LICENSE](LICENSE) and [NOTICE](NOTICE) for more information.
