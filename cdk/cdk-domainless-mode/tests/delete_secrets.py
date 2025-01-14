import boto3
from parse_data_from_json import number_of_gmsa_accounts
def delete_secrets():
    # Initialize the AWS Secrets Manager client
    client = boto3.client('secretsmanager')

    # Base path for the secrets
    base_path = "aws/directoryservice/contoso/gmsa"

    for i in range(1, number_of_gmsa_accounts + 1):
        # Create the secret name
        secret_name = f"{base_path}/WebApp0{i}"

        try:
            # Delete the secret
            response = client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True
            )
            print(f"Deleted secret: {secret_name}")
        except client.exceptions.ResourceNotFoundException:
            print(f"Secret not found: {secret_name}")
        except Exception as e:
            print(f"Error deleting secret {secret_name}: {str(e)}")

# Usage
delete_secrets()