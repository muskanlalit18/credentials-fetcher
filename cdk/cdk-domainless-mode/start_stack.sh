#!/bin/sh

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Please install and setup docker daemon and ensure it's running."
    exit
fi

echo "Please edit the file to add your AWS account number below"
cdk bootstrap aws://XXXXXXXXXXXX/us-west-1 --trust=XXXXXXXXXXXX --cloudformation-execution-policies=arn:aws:iam::aws:policy/AdministratorAccess --verbose && cdk synth && cdk deploy
