#!/bin/sh

# Ensure .NET CLI doesn't send telemetry data
DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_CLI_TELEMETRY_OPTOUT

# Get the .NET SDK version
sdkver=$(dotnet --version)

project_file="utf16_decode.csproj"

dotnet publish "$project_file" \
    -c Release \
    -r linux-x64 \
    --self-contained true \
    -p:PublishAot=true \
    -p:InvariantGlobalization=true
    
echo "NativeAOT compilation complete. Check the publish directory for the output."