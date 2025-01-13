import grpc
import credentialsfetcher_pb2
import credentialsfetcher_pb2_grpc

with open('data.json', 'r') as file:
    # Load the JSON data
    data = json.load(file)

def run():
    with grpc.insecure_channel('unix:///var/credentials-fetcher/socket/credentials_fetcher.sock') as channel:
        number_of_gmsa_accounts = data["number_of_gmsa_accounts"]
        directory_name = data["directory_name"]
        netbios_name = data["netbios_name"]
        username = data["username"]
        password = data["password"]
        stub = credentialsfetcher_pb2_grpc.CredentialsFetcherServiceStub(channel)
        for i in range(1, number_of_gmsa_accounts):
            credspec_contents = f"""{{
                "CmsPlugins": ["ActiveDirectory"],
                "DomainJoinConfig": {{
                    "Sid": "S-1-5-21-2725122404-4129967127-2630707939",
                    "MachineAccountName": "WebApp0{i}",
                    "Guid": "e96e0e09-9305-462f-9e44-8a8179722897",
                    "DnsTreeName": {directory_name},
                    "DnsName": {directory_name},
                    "NetBiosName": {netbios_name}
                }},
                "ActiveDirectoryConfig": {{
                    "GroupManagedServiceAccounts": [
                        {{"Name": "WebApp0{i}", "Scope": {directory_name}}},
                        {{"Name": "WebApp0{i}", "Scope": {netbios_name}}}
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
                    username={username},
                    password={password},
                    domain={directory_name}
                )
            )
            print(f"Server response: {response}")

if __name__ == '__main__':
    run()