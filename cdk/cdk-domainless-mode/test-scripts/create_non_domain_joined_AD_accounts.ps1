$username = "admin@CONTOSO.COM"
$password = "Qn:51eJsORJNL@~{HY@?" | ConvertTo-SecureString -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($username, $password)

$groupAllowedToRetrievePassword = "WebAppAccounts_OU"
$path = "OU=MYOU,OU=Users,OU=contoso,DC=contoso,DC=com"

for (($i = 11); $i -le 200; $i++)
{
    # Create the gMSA account
    $gmsa_account_name = "WebApp0" + $i
    $gmsa_account_with_domain = $gmsa_account_name + ".contoso.com"
    $gmsa_account_with_host = "host/" + $gmsa_account_name
    $gmsa_account_with_host_and_domain = $gmsa_account_with_host + ".contoso.com"

    try {
        #New-ADServiceAccount -Name serviceuser1 -Path "OU=MYOU1,OU=Users,OU=ActiveDirectory,DC=contoso,DC=com" -Credential $credential -DNSHostname "contoso.com"
        New-ADServiceAccount -Name $gmsa_account_name -DnsHostName $gmsa_account_with_domain -ServicePrincipalNames $gmsa_account_with_host, $gmsa_account_with_host_and_domain -PrincipalsAllowedToRetrieveManagedPassword $groupAllowedToRetrievePassword -Path $path -Credential $credential -Server contoso.com
        Write-Output "New-ADServiceAccount -Name $gmsa_account_name -DnsHostName $gmsa_account_with_domain -ServicePrincipalNames $gmsa_account_with_host, $gmsa_account_with_host_and_domain -PrincipalsAllowedToRetrieveManagedPassword $groupAllowedToRetrievePassword -Path $path -Credential $credential -Server contoso.com"
    } catch {
        $string_err = $_ | Out-String
        Write-Output "Error while gMSA account creation and copy credspec to S3 bucket: " + $string_err
    }
}