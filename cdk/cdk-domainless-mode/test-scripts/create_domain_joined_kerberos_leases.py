import grpc
import credentialsfetcher_pb2
import credentialsfetcher_pb2_grpc
import json
import os
'''
Use this script to create and test N leases for N domain-joined gMSA 
accounts. This script is run on a linux instance in stand-alone mode.
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
        for i in range(1, number_of_gmsa_accounts):
            credspec_contents = f"""{{
                "CmsPlugins": ["ActiveDirectory"],
                "DomainJoinConfig": {{
                    "Sid": "S-1-5-21-2725122404-4129967127-2630707939",
                    "MachineAccountName": "DJ_WebApp0{i}",
                    "Guid": "e96e0e09-9305-462f-9e44-8a8179722897",
                    "DnsTreeName": "{directory_name}",
                    "DnsName": "{directory_name}",
                    "NetBiosName": "{netbios_name}"
                }},
                "ActiveDirectoryConfig": {{
                    "GroupManagedServiceAccounts": [
                        {{"Name": "DJ_WebApp0{i}", "Scope": "{directory_name}"}},
                        {{"Name": "DJ_WebApp0{i}", "Scope": "{netbios_name}"}}
                    ]
                }}
            }}"""

            contents = [credspec_contents]
            response = stub.AddKerberosLease(
                credentialsfetcher_pb2.CreateKerberosLeaseRequest(
                    credspec_contents=contents
                )
            )
            lease_path = (f"/var/credentials-fetcher/krbdir/"
                          f"{response.lease_id}/DJ_WebApp0{i}/krb5cc")
            assert os.path.exists(lease_path)
            print(f"Server response: {response}")

if __name__ == '__main__':
    run()