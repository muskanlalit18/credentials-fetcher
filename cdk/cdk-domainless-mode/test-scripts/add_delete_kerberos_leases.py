import grpc
import credentialsfetcher_pb2
import credentialsfetcher_pb2_grpc
import os
import json
import time

'''
Use this script to create and delete N kerberos leases in a recurring loop 
(currently set to 100 times). This script is run to test that create/delete 
functionality has no leaks or unexpected failures when run over a long 
period of time. This script is run on a linux instance in stand-alone mode.
'''

with open('../data.json', 'r') as file:
    # Load the JSON data
    data = json.load(file)

def run():
    with grpc.insecure_channel('unix:///var/credentials-fetcher/socket/credentials_fetcher.sock') as channel:
        stub = credentialsfetcher_pb2_grpc.CredentialsFetcherServiceStub(channel)
        number_of_gmsa_accounts = data["number_of_gmsa_accounts"]
        directory_name = data["directory_name"]
        netbios_name = data["netbios_name"]
        username = data["username"]
        password = data["password"]

        for iter in range(100):  # Repeat the process 100 times
            lease_ids = []

            # Create cred-specs for users ending with multiples of 5
            for i in range(2, number_of_gmsa_accounts, 2):
                credspec_contents = f"""{{
                    "CmsPlugins": ["ActiveDirectory"],
                    "DomainJoinConfig": {{
                        "Sid": "S-1-5-21-2725122404-4129967127-2630707939",
                        "MachineAccountName": "WebApp0{i}",
                        "Guid": "e96e0e09-9305-462f-9e44-8a8179722897",
                        "DnsTreeName": "{directory_name}",
                        "DnsName": "{directory_name}",
                        "NetBiosName": "{netbios_name}"
                    }},
                    "ActiveDirectoryConfig": {{
                        "GroupManagedServiceAccounts": [
                            {{"Name": "WebApp0{i}", "Scope": "{directory_name}"}},
                            {{"Name": "WebApp0{i}", "Scope": "{netbios_name}"}}
                        ],
                        "HostAccountConfig": {{
                            "PortableCcgVersion": "1",
                            "PluginGUID": "{{GDMA0342-266A-4D1P-831J-20990E82944F}}",
                            "PluginInput": {{
                                "CredentialArn": "aws/directoryservice/contoso/gmsa"
                            }}
                        }}
                    }}
                }}"""

                contents = [credspec_contents]
                response = stub.AddNonDomainJoinedKerberosLease(
                    credentialsfetcher_pb2.CreateNonDomainJoinedKerberosLeaseRequest(
                        credspec_contents=contents,
                        username=username,
                        password=password,
                        domain=directory_name
                    )
                )
                print(f"Created lease for WebApp0{i}: {response.lease_id}")
                lease_path = (f"/var/credentials-fetcher/krbdir/"
                              f"{response.lease_id}/WebApp0{i}/krb5cc")
                assert os.path.exists(lease_path)
                lease_ids.append(response.lease_id)

            # Small delay to allow for processing
            time.sleep(1)

            # Delete the created cred-specs
            for lease_id in lease_ids:
                delete_response = stub.DeleteKerberosLease(
                    credentialsfetcher_pb2.DeleteKerberosLeaseRequest(
                        lease_id=lease_id
                    )
                )
                print(f"Deleted lease: {delete_response.lease_id}")
                lease_path = f"/var/credentials-fetcher/krbdir/{lease_id}"
                print(lease_path)
                assert not os.path.exists(lease_path)

            print(f"Completed {iter} cycle of creation and deletion")

if __name__ == '__main__':
    run()